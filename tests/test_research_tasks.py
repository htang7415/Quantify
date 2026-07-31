from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from quantify.policy_control import (
    ArtifactKind,
    HmacPolicySigner,
    PolicyControlPlane,
    PolicyControlPointers,
    ReleaseGatePolicy,
    RuntimePolicyBundle,
)
from quantify.research_tasks import (
    DeterministicShardedAdmission,
    DynamoDbResearchTaskStore,
    IdempotencyConflictError,
    InMemoryResearchTaskQueue,
    InMemoryResearchTaskStore,
    ResearchTaskRequest,
    ResearchTaskService,
    ResearchTaskWorker,
    ProviderReconciliation,
    ProviderReconciliationState,
    SqsResearchTaskQueue,
    TaskCapacityExceededError,
    TaskCapacityPolicy,
    TaskState,
    _TaskRecord,
)
from quantify.runtime import ModelUnavailableError
from quantify.indexed_release import IndexedSnapshotProvider
from quantify.service import ApplicationService
from tests.test_indexed_release import _MicrosoftGrowthExtractor, _compiled_msft_release


EVIDENCE_HASH = "e" * 64
AUDIT_HASH = "a" * 64


def _runtime(*, disabled: bool = False) -> RuntimePolicyBundle:
    return RuntimePolicyBundle(
        schema_version="1.0.0",
        policy_id="research-task-runtime-v1" if not disabled else "research-task-runtime-stop-v1",
        planner_provider="google",
        planner_model="gemini-3.1-flash-lite",
        planner_model_version="2026-07",
        secret_version="test-secret-version",
        prompt_hash="a" * 64,
        maximum_model_calls=1,
        maximum_input_tokens=4_000,
        maximum_output_tokens=500,
        allowed_tools=("verify_claims",),
        disabled_tools=("verify_claims",) if disabled else (),
        allowed_sources=("structured_fact",),
        prohibited_actions=(
            "arbitrary_url_fetch",
            "live_sec_retrieval",
            "private_document_access",
            "policy_mutation",
            "verdict_composition",
            "trade_execution",
        ),
        admission_policy_version="admission-v1",
        cache_policy_version="cache-v1",
    )


def _gate() -> ReleaseGatePolicy:
    return ReleaseGatePolicy(
        schema_version="1.0.0",
        policy_id="research-task-gate-v1",
        minimum_automated_pass_rate_basis_points=9_900,
        maximum_review_exception_rate_basis_points=100,
        maximum_correction_rate_basis_points=25,
        maximum_source_age_days=30,
        lane_a_spot_review_required=True,
        lane_b_reviewer_approval_required=True,
    )


def _control_plane(
    *, evidence_release_hash: str = EVIDENCE_HASH
) -> tuple[PolicyControlPlane, HmacPolicySigner, RuntimePolicyBundle]:
    signer = HmacPolicySigner(key_id="research-task-test-key", key=b"k" * 32)
    plane = PolicyControlPlane(signer=signer)
    runtime = _runtime()
    gate = _gate()
    plane.publish(signer.sign(kind=ArtifactKind.RUNTIME_POLICY, artifact=runtime))
    plane.publish(signer.sign(kind=ArtifactKind.RELEASE_GATE_POLICY, artifact=gate))
    plane.register_evidence_release(manifest_hash=evidence_release_hash)
    plane.set_pointers(
        PolicyControlPointers(
            evidence_release_manifest_hash=evidence_release_hash,
            runtime_policy_bundle_hash=runtime.content_hash,
            release_gate_policy_hash=gate.content_hash,
        )
    )
    return plane, signer, runtime


class _Verifier:
    def __init__(self, *, pointers: PolicyControlPointers, review: bool = False) -> None:
        self.pointers = pointers
        self.review = review
        self.calls = 0

    def verify(self, *, cik: str, request: object) -> dict[str, object]:
        self.calls += 1
        del cik, request
        verdict = "requires_agent_resolution" if self.review else "verified"
        return {
            "claim_results": [{"claim_id": "claim-1", "verdict": verdict}],
            "review_items": [{}] if self.review else [],
            "evidence_scope": {
                "source": "SEC EDGAR",
                "entity_level_only": True,
                "forms": ["10-K"],
                "snapshot_manifest_hash": "b" * 64,
            },
            "audit_manifest": {
                "manifest_hash": AUDIT_HASH,
                "evidence_release_manifest_hash": self.pointers.evidence_release_manifest_hash,
                "runtime_policy_bundle_hash": self.pointers.runtime_policy_bundle_hash,
                "release_gate_policy_hash": self.pointers.release_gate_policy_hash,
            },
        }


def _request(*, analysis: str = "Microsoft revenue increased.") -> ResearchTaskRequest:
    return ResearchTaskRequest(
        cik="789019", analysis=analysis, as_of_date=date(2024, 7, 30), forms=("10-K",)
    )


def _task_service(*, capacity: TaskCapacityPolicy | None = None, reconciler=None):
    plane, signer, runtime = _control_plane()
    queue = InMemoryResearchTaskQueue()
    store = InMemoryResearchTaskStore()
    service = ResearchTaskService(
        policy_control=plane,
        admission=DeterministicShardedAdmission(
            policy=capacity
            or TaskCapacityPolicy(
                shard_count=2,
                daily_task_limit=10,
                monthly_reservation_limit_micro_usd=10_000,
                reservation_micro_usd=500,
            )
        ),
        store=store,
        queue=queue,
        reconciler=reconciler,
        clock=lambda: datetime(2026, 7, 30, tzinfo=timezone.utc),
        task_id_factory=iter(("task-1", "task-2", "task-3")).__next__,
    )
    return service, store, queue, plane, signer, runtime


def test_submit_canonicalizes_idempotency_and_records_three_pinned_hashes() -> None:
    service, store, _, _, _, _ = _task_service()
    first = service.submit(request=_request(), idempotency_key="same-request")
    replay = service.submit(request=_request(), idempotency_key="same-request")

    assert first == replay
    assert first["state"] == "queued"
    assert set(first) == {
        "task_id",
        "state",
        "evidence_release_manifest_hash",
        "runtime_policy_bundle_hash",
        "release_gate_policy_hash",
        "retry_of_task_id",
    }
    assert [state.value for state in store.get(task_id="task-1").state_history] == [
        "accepted",
        "admitted",
        "queued",
    ]


def test_idempotency_collision_rejects_work_and_reserves_no_second_task() -> None:
    service, _, _, _, _, _ = _task_service()
    service.submit(request=_request(), idempotency_key="key")

    with pytest.raises(IdempotencyConflictError, match="different request"):
        service.submit(request=_request(analysis="Microsoft revenue declined."), idempotency_key="key")


def test_sharded_admission_enforces_a_hard_capacity_cap() -> None:
    service, _, _, _, _, _ = _task_service(
        capacity=TaskCapacityPolicy(
            shard_count=1,
            daily_task_limit=1,
            monthly_reservation_limit_micro_usd=1_000,
            reservation_micro_usd=500,
        )
    )
    service.submit(request=_request(), idempotency_key="one")

    with pytest.raises(TaskCapacityExceededError, match="daily"):
        service.submit(request=_request(analysis="A different claim."), idempotency_key="two")


def test_worker_runs_one_bounded_verify_claims_tool_and_serves_only_safe_result() -> None:
    service, store, queue, plane, _, _ = _task_service()
    accepted = service.submit(request=_request(), idempotency_key="work")
    verifier = _Verifier(pointers=plane.current_pointers())
    worker = ResearchTaskWorker(
        service=service,
        store=store,
        queue=queue,
        policy_control=plane,
        verifier=verifier,  # type: ignore[arg-type]
    )

    completed = worker.run_once()

    assert verifier.calls == 1
    assert completed is not None
    assert completed["task_id"] == accepted["task_id"]
    assert completed["state"] == TaskState.COMPLETED.value
    assert completed["result"] == {
        "verdicts": [{"claim_id": "claim-1", "verdict": "verified"}],
        "requires_agent_resolution": False,
        "evidence_scope": {
            "source": "SEC EDGAR",
            "forms": ["10-K"],
            "snapshot_manifest_hash": "b" * 64,
        },
        "audit_manifest_hash": AUDIT_HASH,
        "limitation": "Verdicts apply only to the declared frozen SEC evidence snapshot; they are not investment advice.",
    }
    assert "Microsoft" not in str(completed)
    assert service.status(task_id=accepted["task_id"]) == completed


def test_worker_uses_the_indexed_snapshot_adapter_and_existing_deterministic_engine() -> None:
    indexed_release, _, compiled_request = _compiled_msft_release()
    plane, _, _ = _control_plane(
        evidence_release_hash=indexed_release.evidence_release.manifest_hash
    )
    queue = InMemoryResearchTaskQueue()
    store = InMemoryResearchTaskStore()
    service = ResearchTaskService(
        policy_control=plane,
        admission=DeterministicShardedAdmission(
            policy=TaskCapacityPolicy(
                shard_count=1,
                daily_task_limit=2,
                monthly_reservation_limit_micro_usd=1_000,
                reservation_micro_usd=500,
            )
        ),
        store=store,
        queue=queue,
        clock=lambda: datetime(2026, 7, 30, tzinfo=timezone.utc),
        task_id_factory=lambda: "indexed-task",
    )
    pointers = plane.current_pointers()
    verifier = ApplicationService(
        snapshot_provider=IndexedSnapshotProvider(indexed_release=indexed_release),
        extractor=_MicrosoftGrowthExtractor(),
        evidence_release_manifest_hash=pointers.evidence_release_manifest_hash,
        runtime_policy_bundle_hash=pointers.runtime_policy_bundle_hash,
        release_gate_policy_hash=pointers.release_gate_policy_hash,
    )
    service.submit(
        request=ResearchTaskRequest(
            cik=compiled_request.cik,
            analysis="Microsoft revenue increased from fiscal 2023 to fiscal 2024",
            as_of_date=compiled_request.as_of_date,
            forms=compiled_request.forms,
        ),
        idempotency_key="indexed-engine",
    )

    result = ResearchTaskWorker(
        service=service,
        store=store,
        queue=queue,
        policy_control=plane,
        verifier=verifier,
    ).run_once()

    assert result is not None
    assert result["state"] == TaskState.COMPLETED.value
    assert result["result"]["verdicts"] == [  # type: ignore[index]
        {"claim_id": "msft-revenue-growth", "verdict": "verified"}
    ]


def test_worker_routes_review_required_verdicts_without_changing_verifier_output() -> None:
    service, store, queue, plane, _, _ = _task_service()
    service.submit(request=_request(), idempotency_key="review")
    worker = ResearchTaskWorker(
        service=service,
        store=store,
        queue=queue,
        policy_control=plane,
        verifier=_Verifier(pointers=plane.current_pointers(), review=True),  # type: ignore[arg-type]
    )

    result = worker.run_once()

    assert result is not None
    assert result["state"] == TaskState.REQUIRES_REVIEW.value
    assert result["result"]["requires_agent_resolution"] is True  # type: ignore[index]


def test_runtime_policy_disable_stops_queued_work_before_the_verifier_runs() -> None:
    service, store, queue, plane, signer, _ = _task_service()
    service.submit(request=_request(), idempotency_key="disable")
    disabled = _runtime(disabled=True)
    plane.publish(signer.sign(kind=ArtifactKind.RUNTIME_POLICY, artifact=disabled))
    plane.set_runtime_policy_pointer(artifact_hash=disabled.content_hash)
    verifier = _Verifier(pointers=plane.current_pointers())
    worker = ResearchTaskWorker(
        service=service,
        store=store,
        queue=queue,
        policy_control=plane,
        verifier=verifier,  # type: ignore[arg-type]
    )

    result = worker.run_once()

    assert verifier.calls == 0
    assert result is not None
    assert result["state"] == TaskState.UNAVAILABLE.value


class _UnavailableVerifier:
    def __init__(self) -> None:
        self.calls = 0

    def verify(self, *, cik: str, request: object) -> dict[str, object]:
        self.calls += 1
        del cik, request
        raise ModelUnavailableError("provider start state is ambiguous")


class _Reconciler:
    def __init__(self, outcome: ProviderReconciliation) -> None:
        self.outcome = outcome
        self.calls = 0

    def reconcile(self, *, task_id: str) -> ProviderReconciliation:
        self.calls += 1
        assert task_id
        return self.outcome


def _worker(*, service, store, queue, plane, verifier):
    return ResearchTaskWorker(
        service=service,
        store=store,
        queue=queue,
        policy_control=plane,
        verifier=verifier,  # type: ignore[arg-type]
    )


def test_ambiguous_provider_failure_waits_for_explicit_reconciliation() -> None:
    reconciler = _Reconciler(
        ProviderReconciliation(state=ProviderReconciliationState.UNAVAILABLE)
    )
    service, store, queue, plane, _, _ = _task_service(reconciler=reconciler)
    service.submit(request=_request(), idempotency_key="ambiguous")

    first = _worker(
        service=service,
        store=store,
        queue=queue,
        plane=plane,
        verifier=_UnavailableVerifier(),
    ).run_once()

    assert first is not None
    assert first["state"] == TaskState.RECONCILING.value
    assert reconciler.calls == 0
    assert queue.receive() is None

    final = service.reconcile(task_id="task-1")
    assert reconciler.calls == 1
    assert final["state"] == TaskState.FAILED_UNRESOLVED.value


def test_not_started_reconciliation_releases_reservation_and_permits_one_manual_retry() -> None:
    reconciler = _Reconciler(
        ProviderReconciliation(state=ProviderReconciliationState.NOT_STARTED)
    )
    service, store, queue, plane, _, _ = _task_service(
        capacity=TaskCapacityPolicy(
            shard_count=1,
            daily_task_limit=1,
            monthly_reservation_limit_micro_usd=1_000,
            reservation_micro_usd=500,
        ),
        reconciler=reconciler,
    )
    service.submit(request=_request(), idempotency_key="not-started")
    _worker(
        service=service,
        store=store,
        queue=queue,
        plane=plane,
        verifier=_UnavailableVerifier(),
    ).run_once()

    assert service.reconcile(task_id="task-1")["state"] == TaskState.UNAVAILABLE.value
    retry = service.retry(task_id="task-1", idempotency_key="manual-retry")

    assert retry["task_id"] == "task-2"
    assert retry["retry_of_task_id"] == "task-1"
    assert store.get(task_id="task-1").manual_retry_task_id == "task-2"
    with pytest.raises(Exception, match="one controlled retry"):
        service.retry(task_id="task-1", idempotency_key="second-retry")


def test_completed_reconciliation_recovers_only_a_matching_safe_result_and_settles_cost() -> None:
    service, store, queue, plane, _, _ = _task_service()
    response = _Verifier(pointers=plane.current_pointers()).verify(cik="789019", request={})
    reconciler = _Reconciler(
        ProviderReconciliation(
            state=ProviderReconciliationState.COMPLETED,
            response=response,
            actual_cost_micro_usd=100,
        )
    )
    service._reconciler = reconciler  # type: ignore[attr-defined]
    service.submit(request=_request(), idempotency_key="completed-reconcile")
    _worker(
        service=service,
        store=store,
        queue=queue,
        plane=plane,
        verifier=_UnavailableVerifier(),
    ).run_once()

    recovered = service.reconcile(task_id="task-1")
    assert recovered["state"] == TaskState.COMPLETED.value
    assert recovered["result"]["audit_manifest_hash"] == AUDIT_HASH  # type: ignore[index]


def test_queued_cancellation_releases_unstarted_capacity_and_prevents_verification() -> None:
    service, store, queue, plane, _, _ = _task_service(
        capacity=TaskCapacityPolicy(
            shard_count=1,
            daily_task_limit=1,
            monthly_reservation_limit_micro_usd=1_000,
            reservation_micro_usd=500,
        )
    )
    submitted = service.submit(request=_request(), idempotency_key="cancel")
    canceled = service.cancel(task_id=str(submitted["task_id"]))
    verifier = _Verifier(pointers=plane.current_pointers())

    worker_result = _worker(
        service=service, store=store, queue=queue, plane=plane, verifier=verifier
    ).run_once()

    assert canceled["state"] == TaskState.CANCELED.value
    assert worker_result is not None and worker_result["state"] == TaskState.CANCELED.value
    assert verifier.calls == 0
    assert service.submit(
        request=_request(analysis="A replacement claim."), idempotency_key="after-cancel"
    )["state"] == TaskState.QUEUED.value


def test_queue_retries_unknown_messages_then_moves_them_to_the_dlq() -> None:
    queue = InMemoryResearchTaskQueue(maximum_receives=2)
    queue.enqueue(task_id="unknown-task")
    first = queue.receive()
    assert first is not None
    queue.fail(message=first)
    second = queue.receive()
    assert second is not None
    queue.fail(message=second)

    assert [message.task_id for message in queue.dead_letter] == ["unknown-task"]


class _SqsClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.messages: list[dict[str, object]] = []

    def send_message(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("send", kwargs))
        return {}

    def receive_message(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("receive", kwargs))
        return {"Messages": self.messages}

    def delete_message(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("delete", kwargs))
        return {}

    def change_message_visibility(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("visibility", kwargs))
        return {}


def test_sqs_queue_adapter_bounds_failures_and_hands_exhausted_messages_to_its_dlq() -> None:
    client = _SqsClient()
    queue = SqsResearchTaskQueue(
        queue_url="queue", dead_letter_queue_url="dlq", client=client, maximum_receives=2
    )
    queue.enqueue(task_id="task-1")
    client.messages = [
        {
            "Body": '{"task_id":"task-1"}',
            "ReceiptHandle": "receipt-1",
            "Attributes": {"ApproximateReceiveCount": "1"},
        }
    ]
    message = queue.receive()
    assert message is not None
    queue.fail(message=message)
    assert client.calls[-1] == (
        "visibility",
        {"QueueUrl": "queue", "ReceiptHandle": "receipt-1", "VisibilityTimeout": 0},
    )

    exhausted = message.__class__(
        task_id=message.task_id, receipt_handle=message.receipt_handle, receive_count=2
    )
    queue.fail(message=exhausted)
    assert client.calls[-2:] == [
        ("send", {"QueueUrl": "dlq", "MessageBody": '{"task_id":"task-1"}'}),
        ("delete", {"QueueUrl": "queue", "ReceiptHandle": "receipt-1"}),
    ]


def test_dynamodb_task_store_admits_task_idempotency_and_capacity_in_one_transaction() -> None:
    class _DynamoClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def transact_write_items(self, **kwargs: object) -> dict[str, object]:
            self.calls.append(kwargs)
            return {}

    policy = TaskCapacityPolicy(
        shard_count=2,
        daily_task_limit=10,
        monthly_reservation_limit_micro_usd=10_000,
        reservation_micro_usd=500,
    )
    client = _DynamoClient()
    store = DynamoDbResearchTaskStore(table_name="tasks", client=client, policy=policy)
    plane, _, _ = _control_plane()
    request = _request()
    reservation = store.reservation_for(
        reservation_id="durable-task",
        canonical_request_hash=request.canonical_request_hash,
        now=datetime(2026, 7, 30, tzinfo=timezone.utc),
    )
    record = _TaskRecord(
        task_id="durable-task",
        request=request,
        idempotency_key="idem-durable-task",
        canonical_request_hash=request.canonical_request_hash,
        policy_pointers=plane.current_pointers(),
        reservation=reservation,
        state=TaskState.ACCEPTED,
        state_history=[TaskState.ACCEPTED],
    )

    store.create_with_reservation(record=record)

    transaction = client.calls[0]["TransactItems"]
    assert len(transaction) == 4
    assert transaction[0]["Put"]["ConditionExpression"] == "attribute_not_exists(pk)"
    assert transaction[1]["Put"]["Item"]["canonical_request_hash"]["S"] == request.canonical_request_hash
    assert "#used < :limit" in transaction[2]["Update"]["ConditionExpression"]
    assert "#used <= :remaining" in transaction[3]["Update"]["ConditionExpression"]


def test_dynamodb_task_store_fails_closed_when_admission_transaction_is_canceled() -> None:
    class _RejectedClient:
        def transact_write_items(self, **kwargs: object) -> dict[str, object]:
            error = RuntimeError("transaction canceled")
            error.response = {"Error": {"Code": "TransactionCanceledException"}}  # type: ignore[attr-defined]
            raise error

    policy = TaskCapacityPolicy(
        shard_count=1,
        daily_task_limit=1,
        monthly_reservation_limit_micro_usd=500,
        reservation_micro_usd=500,
    )
    store = DynamoDbResearchTaskStore(table_name="tasks", client=_RejectedClient(), policy=policy)
    plane, _, _ = _control_plane()
    request = _request()
    record = _TaskRecord(
        task_id="rejected-task",
        request=request,
        idempotency_key="idem-rejected-task",
        canonical_request_hash=request.canonical_request_hash,
        policy_pointers=plane.current_pointers(),
        reservation=store.reservation_for(
            reservation_id="rejected-task",
            canonical_request_hash=request.canonical_request_hash,
            now=datetime(2026, 7, 30, tzinfo=timezone.utc),
        ),
        state=TaskState.ACCEPTED,
        state_history=[TaskState.ACCEPTED],
    )

    with pytest.raises(TaskCapacityExceededError, match="admission transaction was rejected"):
        store.create_with_reservation(record=record)


def test_task_service_uses_durable_transactional_admission_when_configured() -> None:
    class _StatefulDynamoClient:
        def __init__(self) -> None:
            self.items: dict[tuple[str, str], dict[str, object]] = {}
            self.transactions = 0

        @staticmethod
        def _identity(key: dict[str, dict[str, str]]) -> tuple[str, str]:
            return key["pk"]["S"], key["sk"]["S"]

        def get_item(self, **kwargs: object) -> dict[str, object]:
            item = self.items.get(self._identity(kwargs["Key"]))
            return {} if item is None else {"Item": item}

        def transact_write_items(self, **kwargs: object) -> dict[str, object]:
            self.transactions += 1
            for entry in kwargs["TransactItems"]:
                put = entry.get("Put")
                if put is not None:
                    self.items[self._identity(put["Item"])] = put["Item"]
            return {}

        def update_item(self, **kwargs: object) -> dict[str, object]:
            key = self._identity(kwargs["Key"])
            self.items[key]["record_json"] = kwargs["ExpressionAttributeValues"][":updated"]
            return {}

    policy = TaskCapacityPolicy(
        shard_count=2,
        daily_task_limit=10,
        monthly_reservation_limit_micro_usd=10_000,
        reservation_micro_usd=500,
    )
    client = _StatefulDynamoClient()
    store = DynamoDbResearchTaskStore(table_name="tasks", client=client, policy=policy)
    plane, _, _ = _control_plane()
    service = ResearchTaskService(
        policy_control=plane,
        admission=DeterministicShardedAdmission(policy=policy),
        store=store,
        queue=InMemoryResearchTaskQueue(),
        clock=lambda: datetime(2026, 7, 30, tzinfo=timezone.utc),
        task_id_factory=lambda: "durable-service-task",
    )

    first = service.submit(request=_request(), idempotency_key="durable-service-key")
    second = service.submit(request=_request(), idempotency_key="durable-service-key")

    assert first["state"] == TaskState.QUEUED.value
    assert second == first
    assert client.transactions == 1
