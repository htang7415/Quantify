from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "smoke_research_task_worker.py"
spec = importlib.util.spec_from_file_location("smoke_research_task_worker", SCRIPT)
smoke_research_task_worker = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(smoke_research_task_worker)


def _stack() -> dict[str, object]:
    return {"Stacks": [{"StackStatus": "UPDATE_COMPLETE", "Parameters": [
        {"ParameterKey": "WorkerReservedConcurrency", "ParameterValue": "0"},
        {"ParameterKey": "EnableTaskConsumption", "ParameterValue": "false"},
    ]}]}


class _CloudFormation:
    def describe_stacks(self, **kwargs): return _stack()
    def describe_stack_resources(self, **kwargs):
        return {"StackResources": [{"LogicalResourceId": "Worker", "PhysicalResourceId": "worker"}]}


def test_empty_event_smoke_restores_zero_concurrency_without_an_event_mapping() -> None:
    class _Lambda:
        def __init__(self): self.calls = []; self.concurrency = []
        def get_account_settings(self): return {"AccountLimit": {"UnreservedConcurrentExecutions": 12}}
        def list_event_source_mappings(self, **kwargs): return {"EventSourceMappings": []}
        def invoke(self, **kwargs): self.calls.append(kwargs); return {"StatusCode": 200}
        def put_function_concurrency(self, **kwargs): self.concurrency.append(kwargs)
        def get_function_concurrency(self, **kwargs): return {"ReservedConcurrentExecutions": 0}

    lambda_client = _Lambda()
    result = smoke_research_task_worker.bootstrap_smoke(
        cf_client=_CloudFormation(), lambda_client=lambda_client, stack_name="pilot"
    )

    assert result == {"bootstrap_smoke": "passed", "invoke_status": 200, "restored_mode": "inactive"}
    assert lambda_client.calls == [{"FunctionName": "worker", "InvocationType": "RequestResponse", "Payload": b'{"Records":[]}'}]
    assert lambda_client.concurrency == [
        {"FunctionName": "worker", "ReservedConcurrentExecutions": 2},
        {"FunctionName": "worker", "ReservedConcurrentExecutions": 0},
    ]


def test_empty_event_smoke_restores_when_invocation_fails() -> None:
    class _Lambda:
        def __init__(self): self.concurrency = []
        def get_account_settings(self): return {"AccountLimit": {"UnreservedConcurrentExecutions": 12}}
        def list_event_source_mappings(self, **kwargs): return {"EventSourceMappings": []}
        def invoke(self, **kwargs): return {"StatusCode": 200, "FunctionError": "Unhandled"}
        def put_function_concurrency(self, **kwargs): self.concurrency.append(kwargs)
        def get_function_concurrency(self, **kwargs): return {"ReservedConcurrentExecutions": 0}

    lambda_client = _Lambda()
    try:
        smoke_research_task_worker.bootstrap_smoke(
            cf_client=_CloudFormation(), lambda_client=lambda_client, stack_name="pilot"
        )
    except RuntimeError as error:
        assert "bootstrap invocation failed" in str(error)
    else:
        raise AssertionError("failed invocation must fail the smoke")
    assert lambda_client.concurrency[-1] == {"FunctionName": "worker", "ReservedConcurrentExecutions": 0}


def test_empty_event_smoke_refuses_insufficient_unreserved_account_capacity() -> None:
    class _Lambda:
        def get_account_settings(self): return {"AccountLimit": {"UnreservedConcurrentExecutions": 10}}
        def list_event_source_mappings(self, **kwargs): return {"EventSourceMappings": []}

    try:
        smoke_research_task_worker.bootstrap_smoke(
            cf_client=_CloudFormation(), lambda_client=_Lambda(), stack_name="pilot"
        )
    except RuntimeError as error:
        assert "at least 12 unreserved" in str(error)
    else:
        raise AssertionError("insufficient capacity must fail before mutation")
