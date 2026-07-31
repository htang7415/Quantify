from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "deactivate_research_task_pilot.py"
spec = importlib.util.spec_from_file_location("deactivate_research_task_pilot", SCRIPT)
deactivate_research_task_pilot = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(deactivate_research_task_pilot)


def test_deactivation_only_removes_consumer_after_active_preflight() -> None:
    class _Waiter:
        def wait(self, **kwargs): pass
    class _CloudFormation:
        def __init__(self): self.update = None
        def describe_stacks(self, **kwargs): return {"Stacks": [{"StackStatus": "UPDATE_COMPLETE", "Parameters": [
            {"ParameterKey": "WorkerReservedConcurrency", "ParameterValue": "2"},
            {"ParameterKey": "EnableTaskConsumption", "ParameterValue": "true"},
            {"ParameterKey": "TaskMaximumConcurrency", "ParameterValue": "2"},
            {"ParameterKey": "ImageUri", "ParameterValue": "repo@sha256:" + "a" * 64},
        ]}]}
        def describe_stack_resources(self, **kwargs): return {"StackResources": [{"LogicalResourceId": "Worker", "PhysicalResourceId": "worker"}]}
        def update_stack(self, **kwargs): self.update = kwargs
        def get_waiter(self, name): assert name == "stack_update_complete"; return _Waiter()
    class _Lambda:
        def __init__(self): self.calls = 0
        def list_event_source_mappings(self, **kwargs):
            self.calls += 1
            return {"EventSourceMappings": [{"State": "Enabled"}] if self.calls == 1 else []}
        def get_function_concurrency(self, **kwargs): return {"ReservedConcurrentExecutions": 0}

    cloudformation = _CloudFormation()
    result = deactivate_research_task_pilot.deactivate(
        cf_client=cloudformation, lambda_client=_Lambda(), stack_name="pilot"
    )

    assert result == {"mode": "inactive", "maximum_task_concurrency": 0, "worker_reserved_concurrency": 0}
    parameters = {item["ParameterKey"]: item for item in cloudformation.update["Parameters"]}
    assert parameters["WorkerReservedConcurrency"]["ParameterValue"] == "0"
    assert parameters["EnableTaskConsumption"]["ParameterValue"] == "false"
    assert parameters["TaskMaximumConcurrency"] == {"ParameterKey": "TaskMaximumConcurrency", "UsePreviousValue": True}


def test_deactivation_refuses_an_inactive_stack() -> None:
    class _CloudFormation:
        def describe_stacks(self, **kwargs): return {"Stacks": [{"StackStatus": "UPDATE_COMPLETE", "Parameters": [
            {"ParameterKey": "WorkerReservedConcurrency", "ParameterValue": "0"},
            {"ParameterKey": "EnableTaskConsumption", "ParameterValue": "false"},
        ]}]}

    with pytest.raises(RuntimeError, match="requires an active stack"):
        deactivate_research_task_pilot.deactivate(
            cf_client=_CloudFormation(), lambda_client=object(), stack_name="pilot"
        )
