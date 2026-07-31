from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "activate_research_task_pilot.py"
spec = importlib.util.spec_from_file_location("activate_research_task_pilot", SCRIPT)
activate_research_task_pilot = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(activate_research_task_pilot)


def test_activation_changes_only_the_bounded_consumer_parameters_after_inactive_preflight() -> None:
    class _Waiter:
        def wait(self, **kwargs): pass
    class _CloudFormation:
        def __init__(self): self.update = None
        def describe_stacks(self, **kwargs): return {"Stacks": [{"StackStatus": "UPDATE_COMPLETE", "Parameters": [
            {"ParameterKey": "WorkerReservedConcurrency", "ParameterValue": "0"},
            {"ParameterKey": "EnableTaskConsumption", "ParameterValue": "false"},
            {"ParameterKey": "TaskMaximumConcurrency", "ParameterValue": "1"},
            {"ParameterKey": "ImageUri", "ParameterValue": "repo@sha256:" + "a" * 64},
        ]}]}
        def describe_stack_resources(self, **kwargs): return {"StackResources": [{"LogicalResourceId": "Worker", "PhysicalResourceId": "worker"}]}
        def update_stack(self, **kwargs): self.update = kwargs
        def get_waiter(self, name): assert name == "stack_update_complete"; return _Waiter()
    class _Lambda:
        def __init__(self): self.calls = 0
        def list_event_source_mappings(self, **kwargs):
            self.calls += 1
            return {"EventSourceMappings": [] if self.calls == 1 else [{"State": "Enabled", "ScalingConfig": {"MaximumConcurrency": 2}}]}
        def get_function_concurrency(self, **kwargs): return {"ReservedConcurrentExecutions": 2}

    cloudformation = _CloudFormation()
    result = activate_research_task_pilot.activate(
        cf_client=cloudformation, lambda_client=_Lambda(), stack_name="pilot"
    )

    assert result == {"mode": "active", "maximum_task_concurrency": 2, "worker_reserved_concurrency": 2}
    parameters = {item["ParameterKey"]: item for item in cloudformation.update["Parameters"]}
    assert parameters["WorkerReservedConcurrency"]["ParameterValue"] == "2"
    assert parameters["EnableTaskConsumption"]["ParameterValue"] == "true"
    assert parameters["TaskMaximumConcurrency"]["ParameterValue"] == "2"
    assert parameters["ImageUri"] == {"ParameterKey": "ImageUri", "UsePreviousValue": True}


def test_activation_refuses_a_nonempty_existing_event_source_mapping() -> None:
    class _CloudFormation:
        def describe_stacks(self, **kwargs): return {"Stacks": [{"StackStatus": "UPDATE_COMPLETE", "Parameters": [
            {"ParameterKey": "WorkerReservedConcurrency", "ParameterValue": "0"},
            {"ParameterKey": "EnableTaskConsumption", "ParameterValue": "false"},
            {"ParameterKey": "TaskMaximumConcurrency", "ParameterValue": "1"},
        ]}]}
        def describe_stack_resources(self, **kwargs): return {"StackResources": [{"LogicalResourceId": "Worker", "PhysicalResourceId": "worker"}]}
    class _Lambda:
        def list_event_source_mappings(self, **kwargs): return {"EventSourceMappings": [{"State": "Enabled"}]}

    with pytest.raises(RuntimeError, match="no existing event-source mapping"):
        activate_research_task_pilot.activate(
            cf_client=_CloudFormation(), lambda_client=_Lambda(), stack_name="pilot"
        )
