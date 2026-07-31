from __future__ import annotations

from datetime import date
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantify.policy_control import PolicyControlPointers
from quantify.research_tasks import ResearchTaskRequest, TaskCapacityPolicy


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "admit_research_task.py"
spec = importlib.util.spec_from_file_location("admit_research_task", SCRIPT)
admit_research_task = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(admit_research_task)


POINTERS = PolicyControlPointers("e" * 64, "a" * 64, "b" * 64)


def _request() -> ResearchTaskRequest:
    return ResearchTaskRequest(
        cik="0000789019", analysis="Microsoft revenue increased.",
        as_of_date=date(2024, 7, 30),
    )


def _policy() -> TaskCapacityPolicy:
    return TaskCapacityPolicy(2, 10, 10_000, 500)


def _patch_verified_release(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Control:
        def __init__(self, **kwargs): pass
        def current_pointers(self): return POINTERS
        def authorize_tool(self, **kwargs): return object()
    class _Archive:
        calls = []
        def __init__(self, **kwargs): pass
        def load(self, **kwargs): self.calls.append(kwargs); return self
        def build(self, **kwargs): return type("Build", (), {"snapshot": object()})()
    monkeypatch.setattr(admit_research_task, "DynamoDbReloadingPolicyControlPlane", _Control)
    monkeypatch.setattr(admit_research_task, "S3IndexedReleaseArchiveStore", _Archive)
    monkeypatch.setattr(admit_research_task, "approve_acquisition_requests", lambda **kwargs: ())


def test_dry_run_verifies_the_selected_controls_and_archive_without_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_verified_release(monkeypatch)
    monkeypatch.setattr(admit_research_task, "DynamoDbResearchTaskStore", lambda **kwargs: (_ for _ in ()).throw(AssertionError("no task write")))
    monkeypatch.setattr(admit_research_task, "SqsResearchTaskQueue", lambda **kwargs: (_ for _ in ()).throw(AssertionError("no queue write")))

    result = admit_research_task.admit(
        request=_request(), retry_task_id=None, idempotency_key="operator-key", dry_run=True,
        task_table="tasks", task_queue_url="queue", task_dlq_url="dlq",
        policy_bucket="artifacts", policy_table="controls", signing_key_arn="key",
        capacity_policy=_policy(), s3_client=object(), dynamodb_client=object(),
        sqs_client=object(), kms_client=object(),
    )

    assert result["mode"] == "validated_no_write"
    assert result["evidence_release_manifest_hash"] == POINTERS.evidence_release_manifest_hash
    assert result["runtime_policy_bundle_hash"] == POINTERS.runtime_policy_bundle_hash
    assert "analysis" not in result


def test_admission_uses_the_existing_durable_service_only_after_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_verified_release(monkeypatch)
    seen: dict[str, object] = {}
    class _Store:
        def __init__(self, **kwargs): seen["store"] = kwargs
    class _Queue:
        def __init__(self, **kwargs): seen["queue"] = kwargs
    class _Service:
        def __init__(self, **kwargs): seen["service"] = kwargs
        def submit(self, **kwargs):
            seen["submit"] = kwargs
            return {"task_id": "task-1", "state": "queued"}
    monkeypatch.setattr(admit_research_task, "DynamoDbResearchTaskStore", _Store)
    monkeypatch.setattr(admit_research_task, "SqsResearchTaskQueue", _Queue)
    monkeypatch.setattr(admit_research_task, "ResearchTaskService", _Service)

    result = admit_research_task.admit(
        request=_request(), retry_task_id=None, idempotency_key="operator-key", dry_run=False,
        task_table="tasks", task_queue_url="queue", task_dlq_url="dlq",
        policy_bucket="artifacts", policy_table="controls", signing_key_arn="key",
        capacity_policy=_policy(), s3_client=object(), dynamodb_client=object(),
        sqs_client=object(), kms_client=object(),
    )

    assert result == {"task_id": "task-1", "state": "queued"}
    assert seen["store"]["table_name"] == "tasks"
    assert seen["queue"]["queue_url"] == "queue"
    assert seen["submit"]["idempotency_key"] == "operator-key"


def test_admission_uses_the_existing_controlled_retry_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_verified_release(monkeypatch)
    class _Store:
        def get(self, **kwargs): return SimpleNamespace(request=_request())
    monkeypatch.setattr(admit_research_task, "DynamoDbResearchTaskStore", lambda **kwargs: _Store())
    monkeypatch.setattr(admit_research_task, "SqsResearchTaskQueue", lambda **kwargs: object())
    class _Service:
        def __init__(self, **kwargs): pass
        def retry(self, **kwargs): return {**kwargs, "task_id": "retry-1", "state": "queued"}
    monkeypatch.setattr(admit_research_task, "ResearchTaskService", _Service)

    result = admit_research_task.admit(
        request=None, retry_task_id="original-1", idempotency_key="retry-key", dry_run=False,
        task_table="tasks", task_queue_url="queue", task_dlq_url="dlq",
        policy_bucket="artifacts", policy_table="controls", signing_key_arn="key",
        capacity_policy=_policy(), s3_client=object(), dynamodb_client=object(),
        sqs_client=object(), kms_client=object(),
    )

    assert result["task_id"] == "retry-1"
    assert result["task_id"] != "original-1"
    assert result["idempotency_key"] == "retry-key"


def test_request_parser_rejects_unknown_fields_without_echoing_request_text(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    path.write_text(json.dumps({
        "cik": "0000789019", "analysis": "private text", "as_of_date": "2024-07-30",
        "unexpected": "field",
    }))
    with pytest.raises(ValueError, match="schema is invalid"):
        admit_research_task._request(path)


def test_admission_rejects_a_request_scope_missing_from_the_selected_release(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_verified_release(monkeypatch)
    class _UnavailableArchive:
        def __init__(self, **kwargs): pass
        def load(self, **kwargs): return self
        def build(self, **kwargs): raise RuntimeError("missing snapshot")
    monkeypatch.setattr(admit_research_task, "S3IndexedReleaseArchiveStore", _UnavailableArchive)

    with pytest.raises(ValueError, match="does not contain the requested scope"):
        admit_research_task.admit(
            request=_request(), retry_task_id=None, idempotency_key="operator-key", dry_run=True,
            task_table="tasks", task_queue_url="queue", task_dlq_url="dlq",
            policy_bucket="artifacts", policy_table="controls", signing_key_arn="key",
            capacity_policy=_policy(), s3_client=object(), dynamodb_client=object(),
            sqs_client=object(), kms_client=object(),
        )
