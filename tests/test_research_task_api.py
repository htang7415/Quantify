from __future__ import annotations

from fastapi.testclient import TestClient

from quantify.research_task_api import create_research_task_app
from quantify.research_tasks import TaskCapacityPolicy, TaskState
from tests.test_research_tasks import _task_service


def _payload() -> dict[str, object]:
    return {
        "cik": "789019",
        "analysis": "Microsoft revenue increased.",
        "as_of_date": "2024-07-30",
        "forms": ["10-K"],
    }


def test_task_api_returns_a_capability_once_and_requires_it_for_access() -> None:
    service, _, _, _, _, _ = _task_service()
    client = TestClient(create_research_task_app(service, capability_ttl_seconds=300))

    created = client.post(
        "/v1/research-tasks", json=_payload(), headers={"Idempotency-Key": "create"}
    )
    assert created.status_code == 202
    body = created.json()
    capability = body.pop("task_capability")
    assert isinstance(capability, str) and len(capability) >= 32
    assert body["state"] == "queued"

    status = client.get(
        f"/v1/research-tasks/{body['task_id']}",
        headers={"X-Quantify-Task-Capability": capability},
    )
    assert status.status_code == 200
    assert status.json() == body

    wrong = client.get(
        f"/v1/research-tasks/{body['task_id']}",
        headers={"X-Quantify-Task-Capability": "wrong"},
    )
    missing = client.get(f"/v1/research-tasks/{body['task_id']}")
    unknown = client.get(
        "/v1/research-tasks/not-a-task",
        headers={"X-Quantify-Task-Capability": capability},
    )
    assert wrong.status_code == missing.status_code == unknown.status_code == 404
    assert wrong.json() == missing.json() == unknown.json() == {"detail": {"error": "not_found"}}

    replay = client.post(
        "/v1/research-tasks", json=_payload(), headers={"Idempotency-Key": "create"}
    )
    assert replay.status_code == 202
    assert replay.json() == body


def test_task_api_rejects_missing_idempotency_and_exposes_only_the_task_routes() -> None:
    service, _, _, _, _, _ = _task_service()
    app = create_research_task_app(service, capability_ttl_seconds=300)
    client = TestClient(app)

    assert client.post("/v1/research-tasks", json=_payload()).json() == {
        "detail": {"error": "invalid_request"}
    }
    assert client.post("/v1/research-tasks/task-1/retry").json() == {
        "detail": {"error": "invalid_request"}
    }
    paths = {route.path for route in app.routes}
    assert paths == {
        "/v1/research-tasks",
        "/v1/research-tasks/{task_id}",
        "/v1/research-tasks/{task_id}/retry",
        "/v1/research-tasks/{task_id}/cancel",
    }


def test_task_api_maps_retry_capacity_rejection_without_exposing_internal_details() -> None:
    service, store, _, _, _, _ = _task_service(
        capacity=TaskCapacityPolicy(
            shard_count=1,
            daily_task_limit=1,
            monthly_reservation_limit_micro_usd=1_000,
            reservation_micro_usd=500,
        )
    )
    client = TestClient(create_research_task_app(service, capability_ttl_seconds=300))
    created = client.post(
        "/v1/research-tasks", json=_payload(), headers={"Idempotency-Key": "create"}
    ).json()
    store.transition(task_id="task-1", next_state=TaskState.RUNNING)
    store.transition(task_id="task-1", next_state=TaskState.FAILED_UNRESOLVED)

    response = client.post(
        "/v1/research-tasks/task-1/retry",
        headers={
            "Idempotency-Key": "retry",
            "X-Quantify-Task-Capability": str(created["task_capability"]),
        },
    )

    assert response.status_code == 429
    assert response.json() == {"detail": {"error": "capacity_exhausted"}}
