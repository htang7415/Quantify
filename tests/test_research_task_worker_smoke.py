from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "smoke_research_task_worker.py"
spec = importlib.util.spec_from_file_location("smoke_research_task_worker", SCRIPT)
smoke_research_task_worker = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(smoke_research_task_worker)


def test_empty_event_smoke_restores_zero_concurrency_without_an_event_mapping() -> None:
    class _Waiter:
        def __init__(self, client): self.client = client
        def wait(self, **kwargs): self.client.waits += 1

    class _CloudFormation:
        def __init__(self): self.updates = []; self.waits = 0
        def describe_stacks(self, **kwargs): return {"Stacks": [{"StackStatus": "UPDATE_COMPLETE", "Parameters": [
            {"ParameterKey": "WorkerReservedConcurrency", "ParameterValue": "0"},
            {"ParameterKey": "EnableTaskConsumption", "ParameterValue": "false"},
            {"ParameterKey": "ImageUri", "ParameterValue": "repo@sha256:" + "a" * 64},
        ]}]}
        def describe_stack_resources(self, **kwargs): return {"StackResources": [{"LogicalResourceId": "Worker", "PhysicalResourceId": "worker"}]}
        def update_stack(self, **kwargs): self.updates.append(kwargs); return {"StackId": "stack"}
        def get_waiter(self, name): assert name == "stack_update_complete"; return _Waiter(self)

    class _Lambda:
        def __init__(self): self.calls = []
        def get_account_settings(self): return {"AccountLimit": {"UnreservedConcurrentExecutions": 12}}
        def list_event_source_mappings(self, **kwargs): return {"EventSourceMappings": []}
        def invoke(self, **kwargs): self.calls.append(kwargs); return {"StatusCode": 200}
        def get_function_concurrency(self, **kwargs): return {"ReservedConcurrentExecutions": 0}

    cloudformation, lambda_client = _CloudFormation(), _Lambda()
    result = smoke_research_task_worker.bootstrap_smoke(
        cf_client=cloudformation, lambda_client=lambda_client, stack_name="pilot"
    )

    assert result == {"bootstrap_smoke": "passed", "invoke_status": 200, "restored_mode": "inactive"}
    assert cloudformation.waits == 2
    assert lambda_client.calls == [{"FunctionName": "worker", "InvocationType": "RequestResponse", "Payload": b'{"Records":[]}'}]
    assert cloudformation.updates[0]["Parameters"][0]["ParameterValue"] == "2"
    assert cloudformation.updates[1]["Parameters"][0]["ParameterValue"] == "0"


def test_empty_event_smoke_restores_when_invocation_fails() -> None:
    class _Waiter:
        def wait(self, **kwargs): pass
    class _CloudFormation:
        def __init__(self): self.updates = []
        def describe_stacks(self, **kwargs): return {"Stacks": [{"StackStatus": "UPDATE_COMPLETE", "Parameters": [
            {"ParameterKey": "WorkerReservedConcurrency", "ParameterValue": "0"},
            {"ParameterKey": "EnableTaskConsumption", "ParameterValue": "false"},
        ]}]}
        def describe_stack_resources(self, **kwargs): return {"StackResources": [{"LogicalResourceId": "Worker", "PhysicalResourceId": "worker"}]}
        def update_stack(self, **kwargs): self.updates.append(kwargs)
        def get_waiter(self, name): return _Waiter()
    class _Lambda:
        def get_account_settings(self): return {"AccountLimit": {"UnreservedConcurrentExecutions": 12}}
        def list_event_source_mappings(self, **kwargs): return {"EventSourceMappings": []}
        def invoke(self, **kwargs): return {"StatusCode": 200, "FunctionError": "Unhandled"}
        def get_function_concurrency(self, **kwargs): return {"ReservedConcurrentExecutions": 0}

    cloudformation = _CloudFormation()
    try:
        smoke_research_task_worker.bootstrap_smoke(
            cf_client=cloudformation, lambda_client=_Lambda(), stack_name="pilot"
        )
    except RuntimeError as error:
        assert "bootstrap invocation failed" in str(error)
    else:
        raise AssertionError("failed invocation must fail the smoke")
    assert len(cloudformation.updates) == 2
    assert cloudformation.updates[1]["Parameters"][0]["ParameterValue"] == "0"


def test_empty_event_smoke_refuses_insufficient_unreserved_account_capacity() -> None:
    class _CloudFormation:
        def describe_stacks(self, **kwargs): return {"Stacks": [{"StackStatus": "UPDATE_COMPLETE", "Parameters": [
            {"ParameterKey": "WorkerReservedConcurrency", "ParameterValue": "0"},
            {"ParameterKey": "EnableTaskConsumption", "ParameterValue": "false"},
        ]}]}
        def describe_stack_resources(self, **kwargs): return {"StackResources": [{"LogicalResourceId": "Worker", "PhysicalResourceId": "worker"}]}
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
        raise AssertionError("insufficient capacity must fail before an update")
