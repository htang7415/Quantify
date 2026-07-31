from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from quantify.policy_control import PolicyControlPointers
from quantify.research_tasks import TaskCapacityPolicy


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "operate_research_task.py"
spec = importlib.util.spec_from_file_location("operate_research_task", SCRIPT)
operate_research_task = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(operate_research_task)


def _policy() -> TaskCapacityPolicy:
    return TaskCapacityPolicy(2, 10, 10_000, 500)


def _patch_service(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    seen: dict[str, object] = {}
    class _Control:
        def __init__(self, **kwargs): seen["control"] = kwargs
    class _Store:
        def __init__(self, **kwargs): seen["store"] = kwargs
    class _Service:
        def __init__(self, **kwargs): seen["queue"] = kwargs["queue"]
        def status(self, **kwargs): return {"state": "requires_review", **kwargs}
        def cancel(self, **kwargs): return {"state": "canceled", **kwargs}
        def reconcile(self, **kwargs): return {"state": "failed_unresolved", **kwargs}
    monkeypatch.setattr(operate_research_task, "DynamoDbReloadingPolicyControlPlane", _Control)
    monkeypatch.setattr(operate_research_task, "DynamoDbResearchTaskStore", _Store)
    monkeypatch.setattr(operate_research_task, "ResearchTaskService", _Service)
    return seen


@pytest.mark.parametrize("operation,expected", [("status", "requires_review"), ("cancel", "canceled"), ("reconcile", "failed_unresolved")])
def test_operator_lifecycle_uses_no_submit_queue(monkeypatch: pytest.MonkeyPatch, operation: str, expected: str) -> None:
    seen = _patch_service(monkeypatch)
    task_id = "a" * 32
    result = operate_research_task.operate(
        operation=operation, task_id=task_id, task_table="tasks", policy_bucket="artifacts",
        policy_table="controls", signing_key_arn="key", capacity_policy=_policy(),
        s3_client=object(), dynamodb_client=object(), kms_client=object(),
    )
    assert result == {"state": expected, "task_id": task_id}
    with pytest.raises(Exception):
        seen["queue"].enqueue(task_id=task_id)


def test_operator_lifecycle_rejects_an_invalid_task_id() -> None:
    with pytest.raises(ValueError, match="task id is invalid"):
        operate_research_task.operate(
            operation="status", task_id="not-a-task", task_table="tasks", policy_bucket="artifacts",
            policy_table="controls", signing_key_arn="key", capacity_policy=_policy(),
            s3_client=object(), dynamodb_client=object(), kms_client=object(),
        )
