"""Internal, bounded asynchronous research-task vertical slice.

No HTTP route is defined here.  A future delivery adapter may expose these
operations only after separately authorized deployment work.  This module
keeps request canonicalization, idempotency, sharded admission, policy
reauthorization, queueing, and safe result composition outside the verifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
from threading import Lock, RLock
from typing import Callable, Mapping, Protocol
from uuid import uuid4

from quantify.agent_tool import agent_safe_result
from quantify.api import VerifyRequest
from quantify.harness.coverage import EvidenceRequestType
from quantify.policy_control import (
    PolicyControlPlane,
    PolicyControlPointers,
    PolicyControlError,
)
from quantify.runtime import ModelUnavailableError
from quantify.service import ApplicationService
from quantify.harness.sec.client import SecCompanyFactsClient


class ResearchTaskError(RuntimeError):
    """Base failure for the internal task capability."""


class IdempotencyConflictError(ResearchTaskError):
    """An idempotency key was reused for a different canonical request."""


class TaskCapacityExceededError(ResearchTaskError):
    """No deterministic shard has remaining reserved capacity."""


class TaskQueueUnavailableError(ResearchTaskError):
    """Queueing cannot be proven to have succeeded."""


class TaskStoreUnavailableError(ResearchTaskError):
    """Durable task state cannot be read or updated safely."""


class InvalidTaskTransitionError(ResearchTaskError):
    """A task attempted an illegal state transition."""


class TaskState(StrEnum):
    ACCEPTED = "accepted"
    ADMITTED = "admitted"
    QUEUED = "queued"
    RUNNING = "running"
    RECONCILING = "reconciling"
    CANCEL_REQUESTED = "cancel_requested"
    COMPLETED = "completed"
    REQUIRES_REVIEW = "requires_review"
    UNAVAILABLE = "unavailable"
    FAILED_UNRESOLVED = "failed_unresolved"
    CANCELED = "canceled"


_TERMINAL_STATES = frozenset(
    {
        TaskState.COMPLETED,
        TaskState.REQUIRES_REVIEW,
        TaskState.UNAVAILABLE,
        TaskState.FAILED_UNRESOLVED,
        TaskState.CANCELED,
    }
)
_ALLOWED_TRANSITIONS = {
    TaskState.ACCEPTED: frozenset({TaskState.ADMITTED, TaskState.UNAVAILABLE}),
    TaskState.ADMITTED: frozenset({TaskState.QUEUED, TaskState.UNAVAILABLE}),
    TaskState.QUEUED: frozenset({TaskState.RUNNING, TaskState.CANCELED, TaskState.UNAVAILABLE}),
    TaskState.RUNNING: frozenset(
        {TaskState.COMPLETED, TaskState.REQUIRES_REVIEW, TaskState.RECONCILING, TaskState.CANCEL_REQUESTED, TaskState.UNAVAILABLE, TaskState.FAILED_UNRESOLVED}
    ),
    TaskState.RECONCILING: frozenset(
        {TaskState.COMPLETED, TaskState.REQUIRES_REVIEW, TaskState.UNAVAILABLE, TaskState.FAILED_UNRESOLVED, TaskState.CANCEL_REQUESTED}
    ),
    TaskState.CANCEL_REQUESTED: frozenset({TaskState.CANCELED, TaskState.FAILED_UNRESOLVED}),
}


class ProviderReconciliationState(StrEnum):
    NOT_STARTED = "not_started"
    COMPLETED = "completed"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ProviderReconciliation:
    state: ProviderReconciliationState
    response: Mapping[str, object] | None = None
    actual_cost_micro_usd: int | None = None

    def __post_init__(self) -> None:
        if self.state is ProviderReconciliationState.COMPLETED and self.response is None:
            raise ValueError("completed provider reconciliation requires a result")
        if self.state is not ProviderReconciliationState.COMPLETED and self.response is not None:
            raise ValueError("only a completed reconciliation may carry a result")
        if self.actual_cost_micro_usd is not None and self.actual_cost_micro_usd < 0:
            raise ValueError("provider reconciliation cost cannot be negative")


class ProviderReconciler(Protocol):
    def reconcile(self, *, task_id: str) -> ProviderReconciliation: ...


class UnavailableProviderReconciler:
    """Safe default when a provider exposes no attributable result lookup."""

    def reconcile(self, *, task_id: str) -> ProviderReconciliation:
        del task_id
        return ProviderReconciliation(state=ProviderReconciliationState.UNAVAILABLE)


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True, slots=True)
class ResearchTaskRequest:
    """Canonicalizable, bounded input for the first typed ``verify_claims`` tool."""

    cik: str
    analysis: str
    as_of_date: date
    forms: tuple[str, ...] = ("10-K", "10-Q")
    evidence_requests: tuple[EvidenceRequestType, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "cik", SecCompanyFactsClient.normalize_cik(self.cik))
        if not self.analysis.strip() or len(self.analysis.split()) > 250:
            raise ValueError("analysis must contain one through 250 words")
        forms = tuple(sorted({form.removesuffix("/A") for form in self.forms}))
        if not forms or any(form not in {"10-K", "10-Q"} for form in forms):
            raise ValueError("forms must contain only 10-K or 10-Q")
        object.__setattr__(self, "forms", forms)
        requests = tuple(sorted(set(self.evidence_requests), key=lambda item: item.value))
        if len(requests) != len(self.evidence_requests):
            raise ValueError("evidence requests must be unique")
        if len(requests) > 2:
            raise ValueError("evidence acquisition exceeds the two-round V1 limit")
        object.__setattr__(self, "evidence_requests", requests)

    def canonical_payload(self) -> dict[str, object]:
        return {
            "analysis": self.analysis,
            "as_of_date": self.as_of_date.isoformat(),
            "cik": self.cik,
            "evidence_requests": [item.value for item in self.evidence_requests],
            "forms": list(self.forms),
            "tool": "verify_claims",
        }

    @property
    def canonical_request_hash(self) -> str:
        return sha256(_canonical_json(self.canonical_payload())).hexdigest()

    def verify_request(self) -> VerifyRequest:
        return VerifyRequest(
            analysis=self.analysis,
            as_of_date=self.as_of_date,
            forms=self.forms,
            evidence_requests=self.evidence_requests,
        )


@dataclass(frozen=True, slots=True)
class TaskCapacityPolicy:
    """Exact global caps partitioned deterministically across counter shards."""

    shard_count: int
    daily_task_limit: int
    monthly_reservation_limit_micro_usd: int
    reservation_micro_usd: int

    def __post_init__(self) -> None:
        if (
            self.shard_count <= 0
            or self.daily_task_limit <= 0
            or self.monthly_reservation_limit_micro_usd <= 0
            or self.reservation_micro_usd <= 0
            or self.reservation_micro_usd > self.monthly_reservation_limit_micro_usd
        ):
            raise ValueError("task capacity policy is invalid")

    def shard_for(self, *, canonical_request_hash: str) -> int:
        if len(canonical_request_hash) != 64:
            raise ValueError("canonical request hash is invalid")
        try:
            value = int(canonical_request_hash[:16], 16)
        except ValueError as error:
            raise ValueError("canonical request hash is invalid") from error
        return value % self.shard_count

    @staticmethod
    def _partition(*, total: int, shard_count: int, shard: int) -> int:
        base, remainder = divmod(total, shard_count)
        return base + (1 if shard < remainder else 0)

    def daily_limit_for_shard(self, *, shard: int) -> int:
        return self._partition(
            total=self.daily_task_limit, shard_count=self.shard_count, shard=shard
        )

    def monthly_cost_limit_for_shard(self, *, shard: int) -> int:
        return self._partition(
            total=self.monthly_reservation_limit_micro_usd,
            shard_count=self.shard_count,
            shard=shard,
        )

    def reservation_for(
        self, *, reservation_id: str, canonical_request_hash: str, now: datetime
    ) -> "TaskReservation":
        current = now.astimezone(timezone.utc)
        return TaskReservation(
            reservation_id=reservation_id,
            shard=self.shard_for(canonical_request_hash=canonical_request_hash),
            day_bucket=current.strftime("%Y-%m-%d"),
            month_bucket=current.strftime("%Y-%m"),
            reserved_micro_usd=self.reservation_micro_usd,
        )


@dataclass(frozen=True, slots=True)
class TaskReservation:
    reservation_id: str
    shard: int
    day_bucket: str
    month_bucket: str
    reserved_micro_usd: int


class DeterministicShardedAdmission:
    """Thread-safe local model of DynamoDB's sharded hard-cap reservation."""

    def __init__(self, *, policy: TaskCapacityPolicy) -> None:
        self._policy = policy
        self._daily_counts: dict[tuple[str, int], int] = {}
        self._monthly_costs: dict[tuple[str, int], int] = {}
        self._reservations: dict[str, TaskReservation] = {}
        self._lock = RLock()

    def reserve(
        self,
        *,
        reservation_id: str,
        canonical_request_hash: str,
        now: datetime,
    ) -> TaskReservation:
        reservation = self._policy.reservation_for(
            reservation_id=reservation_id,
            canonical_request_hash=canonical_request_hash,
            now=now,
        )
        shard = reservation.shard
        day_bucket = reservation.day_bucket
        month_bucket = reservation.month_bucket
        with self._lock:
            existing = self._reservations.get(reservation_id)
            if existing is not None:
                return existing
            daily_key = (day_bucket, shard)
            monthly_key = (month_bucket, shard)
            if self._daily_counts.get(daily_key, 0) >= self._policy.daily_limit_for_shard(shard=shard):
                raise TaskCapacityExceededError("daily task capacity is exhausted")
            cost_limit = self._policy.monthly_cost_limit_for_shard(shard=shard)
            if self._monthly_costs.get(monthly_key, 0) > cost_limit - self._policy.reservation_micro_usd:
                raise TaskCapacityExceededError("monthly model capacity is exhausted")
            self._daily_counts[daily_key] = self._daily_counts.get(daily_key, 0) + 1
            self._monthly_costs[monthly_key] = (
                self._monthly_costs.get(monthly_key, 0) + reservation.reserved_micro_usd
            )
            self._reservations[reservation_id] = reservation
            return reservation

    def release(self, *, reservation_id: str) -> None:
        with self._lock:
            reservation = self._reservations.pop(reservation_id, None)
            if reservation is None:
                return
            daily_key = (reservation.day_bucket, reservation.shard)
            monthly_key = (reservation.month_bucket, reservation.shard)
            self._daily_counts[daily_key] -= 1
            self._monthly_costs[monthly_key] -= reservation.reserved_micro_usd

    def settle(self, *, reservation_id: str, actual_cost_micro_usd: int) -> None:
        """Replace a worst-case reservation with attributable completed usage."""

        if actual_cost_micro_usd < 0:
            raise ValueError("actual provider cost cannot be negative")
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None:
                raise TaskStoreUnavailableError("provider reservation is unavailable")
            if actual_cost_micro_usd > reservation.reserved_micro_usd:
                raise TaskStoreUnavailableError("provider cost exceeds its reserved capacity")
            monthly_key = (reservation.month_bucket, reservation.shard)
            self._monthly_costs[monthly_key] -= (
                reservation.reserved_micro_usd - actual_cost_micro_usd
            )
            self._reservations[reservation_id] = TaskReservation(
                reservation_id=reservation.reservation_id,
                shard=reservation.shard,
                day_bucket=reservation.day_bucket,
                month_bucket=reservation.month_bucket,
                reserved_micro_usd=actual_cost_micro_usd,
            )


@dataclass(frozen=True, slots=True)
class QueueMessage:
    task_id: str
    receipt_handle: str
    receive_count: int


class ResearchTaskQueue(Protocol):
    def enqueue(self, *, task_id: str) -> None: ...

    def receive(self) -> QueueMessage | None: ...

    def acknowledge(self, *, message: QueueMessage) -> None: ...

    def fail(self, *, message: QueueMessage) -> None: ...


class SqsClient(Protocol):
    def send_message(self, **kwargs: object) -> Mapping[str, object]: ...

    def receive_message(self, **kwargs: object) -> Mapping[str, object]: ...

    def delete_message(self, **kwargs: object) -> Mapping[str, object]: ...

    def change_message_visibility(self, **kwargs: object) -> Mapping[str, object]: ...


class SqsResearchTaskQueue:
    """SQS adapter with an explicit DLQ handoff after bounded receives."""

    def __init__(
        self,
        *,
        queue_url: str,
        dead_letter_queue_url: str,
        client: SqsClient,
        maximum_receives: int = 3,
    ) -> None:
        if not queue_url or not dead_letter_queue_url or maximum_receives <= 0:
            raise ValueError("SQS task queue configuration is invalid")
        self._queue_url = queue_url
        self._dead_letter_queue_url = dead_letter_queue_url
        self._client = client
        self._maximum_receives = maximum_receives

    def enqueue(self, *, task_id: str) -> None:
        try:
            self._client.send_message(
                QueueUrl=self._queue_url,
                MessageBody=json.dumps({"task_id": task_id}, separators=(",", ":")),
            )
        except Exception as error:
            raise TaskQueueUnavailableError("research task queue is unavailable") from error

    def receive(self) -> QueueMessage | None:
        try:
            response = self._client.receive_message(
                QueueUrl=self._queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=0,
                AttributeNames=["ApproximateReceiveCount"],
            )
        except Exception as error:
            raise TaskQueueUnavailableError("research task queue is unavailable") from error
        messages = response.get("Messages", ())
        if not isinstance(messages, list) or not messages:
            return None
        message = messages[0]
        if not isinstance(message, Mapping):
            raise TaskQueueUnavailableError("research task queue returned an invalid message")
        try:
            payload = json.loads(message["Body"])
            attributes = message["Attributes"]
            task_id = payload["task_id"]
            receipt_handle = message["ReceiptHandle"]
            receive_count = int(attributes["ApproximateReceiveCount"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise TaskQueueUnavailableError("research task queue returned an invalid message") from error
        if not isinstance(task_id, str) or not task_id or not isinstance(receipt_handle, str):
            raise TaskQueueUnavailableError("research task queue returned an invalid message")
        return QueueMessage(
            task_id=task_id,
            receipt_handle=receipt_handle,
            receive_count=receive_count,
        )

    def acknowledge(self, *, message: QueueMessage) -> None:
        try:
            self._client.delete_message(
                QueueUrl=self._queue_url, ReceiptHandle=message.receipt_handle
            )
        except Exception as error:
            raise TaskQueueUnavailableError("research task acknowledgement is unavailable") from error

    def fail(self, *, message: QueueMessage) -> None:
        try:
            if message.receive_count >= self._maximum_receives:
                self._client.send_message(
                    QueueUrl=self._dead_letter_queue_url,
                    MessageBody=json.dumps(
                        {"task_id": message.task_id}, separators=(",", ":")
                    ),
                )
                self._client.delete_message(
                    QueueUrl=self._queue_url, ReceiptHandle=message.receipt_handle
                )
            else:
                self._client.change_message_visibility(
                    QueueUrl=self._queue_url,
                    ReceiptHandle=message.receipt_handle,
                    VisibilityTimeout=0,
                )
        except Exception as error:
            raise TaskQueueUnavailableError("research task failure handling is unavailable") from error


class InMemoryResearchTaskQueue:
    """Bounded queue with replay-visible DLQ behavior for tests/local execution."""

    def __init__(self, *, maximum_messages: int = 100, maximum_receives: int = 3) -> None:
        if maximum_messages <= 0 or maximum_receives <= 0:
            raise ValueError("queue bounds are invalid")
        self._maximum_messages = maximum_messages
        self._maximum_receives = maximum_receives
        self._messages: list[QueueMessage] = []
        self.dead_letter: list[QueueMessage] = []

    def enqueue(self, *, task_id: str) -> None:
        if len(self._messages) >= self._maximum_messages:
            raise TaskQueueUnavailableError("research task queue is saturated")
        self._messages.append(QueueMessage(task_id=task_id, receipt_handle=task_id, receive_count=0))

    def receive(self) -> QueueMessage | None:
        if not self._messages:
            return None
        message = self._messages.pop(0)
        return QueueMessage(
            task_id=message.task_id,
            receipt_handle=message.receipt_handle,
            receive_count=message.receive_count + 1,
        )

    def acknowledge(self, *, message: QueueMessage) -> None:
        del message

    def fail(self, *, message: QueueMessage) -> None:
        if message.receive_count >= self._maximum_receives:
            self.dead_letter.append(message)
        else:
            self._messages.append(message)


class LambdaSqsBatchQueue:
    """One Lambda SQS batch exposed through the normal bounded worker queue.

    Lambda, rather than this adapter, owns acknowledgement and redrive.  A
    failed message is returned in ``batchItemFailures`` so the event-source
    mapping applies its configured retry/DLQ policy.  Invalid bodies are never
    logged or interpreted as task input.
    """

    def __init__(self, *, event: Mapping[str, object]) -> None:
        records = event.get("Records")
        if not isinstance(records, list):
            raise TaskQueueUnavailableError("SQS batch event is invalid")
        self._messages: list[QueueMessage] = []
        self._failures: list[str] = []
        for record in records:
            if not isinstance(record, Mapping):
                raise TaskQueueUnavailableError("SQS batch event is invalid")
            message_id = record.get("messageId")
            body = record.get("body")
            if not isinstance(message_id, str) or not message_id:
                raise TaskQueueUnavailableError("SQS batch event is invalid")
            try:
                payload = json.loads(body) if isinstance(body, str) else None
                task_id = payload.get("task_id") if isinstance(payload, Mapping) else None
            except json.JSONDecodeError:
                task_id = None
            if not isinstance(task_id, str) or not task_id:
                self._failures.append(message_id)
                continue
            self._messages.append(
                QueueMessage(task_id=task_id, receipt_handle=message_id, receive_count=1)
            )

    def enqueue(self, *, task_id: str) -> None:
        del task_id
        raise TaskQueueUnavailableError("Lambda SQS batch queue cannot enqueue work")

    def receive(self) -> QueueMessage | None:
        return self._messages.pop(0) if self._messages else None

    def acknowledge(self, *, message: QueueMessage) -> None:
        del message

    def fail(self, *, message: QueueMessage) -> None:
        self._failures.append(message.receipt_handle)

    @property
    def has_pending_messages(self) -> bool:
        return bool(self._messages)

    def response(self) -> dict[str, object]:
        return {
            "batchItemFailures": [
                {"itemIdentifier": message_id} for message_id in sorted(set(self._failures))
            ]
        }


class LambdaSqsBatchProcessor:
    """Adapt one SQS event to the existing deterministic task worker."""

    def __init__(
        self, *, worker_factory: Callable[[ResearchTaskQueue], "ResearchTaskWorker"]
    ) -> None:
        self._worker_factory = worker_factory

    def process(self, *, event: Mapping[str, object]) -> dict[str, object]:
        queue = LambdaSqsBatchQueue(event=event)
        worker = self._worker_factory(queue)
        while queue.has_pending_messages:
            worker.run_once()
        return queue.response()


@dataclass(slots=True)
class _TaskRecord:
    task_id: str
    request: ResearchTaskRequest
    idempotency_key: str
    canonical_request_hash: str
    policy_pointers: PolicyControlPointers
    reservation: TaskReservation
    state: TaskState
    state_history: list[TaskState] = field(default_factory=list)
    safe_result: dict[str, object] | None = None
    retry_of_task_id: str | None = None
    manual_retry_task_id: str | None = None
    reservation_released: bool = False


class InMemoryResearchTaskStore:
    """Atomic local store; a DynamoDB adapter must preserve these semantics."""

    def __init__(self) -> None:
        self._tasks: dict[str, _TaskRecord] = {}
        self._idempotency: dict[str, tuple[str, str]] = {}
        self._lock = RLock()

    def existing_for_idempotency(
        self, *, idempotency_key: str, canonical_request_hash: str
    ) -> _TaskRecord | None:
        with self._lock:
            existing = self._idempotency.get(idempotency_key)
            if existing is None:
                return None
            stored_hash, task_id = existing
            if stored_hash != canonical_request_hash:
                raise IdempotencyConflictError(
                    "idempotency key was reused for different request content"
                )
            return self._tasks[task_id]

    def create(self, *, record: _TaskRecord) -> None:
        with self._lock:
            if record.task_id in self._tasks or record.idempotency_key in self._idempotency:
                raise TaskStoreUnavailableError("task store create was not atomic")
            self._tasks[record.task_id] = record
            self._idempotency[record.idempotency_key] = (
                record.canonical_request_hash,
                record.task_id,
            )

    def get(self, *, task_id: str) -> _TaskRecord:
        with self._lock:
            try:
                return self._tasks[task_id]
            except KeyError as error:
                raise TaskStoreUnavailableError("research task does not exist") from error

    def transition(
        self,
        *,
        task_id: str,
        next_state: TaskState,
        safe_result: dict[str, object] | None = None,
    ) -> _TaskRecord:
        with self._lock:
            task = self.get(task_id=task_id)
            if next_state not in _ALLOWED_TRANSITIONS.get(task.state, frozenset()):
                raise InvalidTaskTransitionError(
                    f"cannot transition task from {task.state} to {next_state}"
                )
            task.state = next_state
            task.state_history.append(next_state)
            task.safe_result = safe_result
            return task

    def mark_reservation_released(self, *, task_id: str) -> None:
        with self._lock:
            self.get(task_id=task_id).reservation_released = True

    def link_manual_retry(self, *, task_id: str, retry_task_id: str) -> None:
        with self._lock:
            task = self.get(task_id=task_id)
            if task.manual_retry_task_id is not None:
                raise InvalidTaskTransitionError("task already has a controlled retry")
            task.manual_retry_task_id = retry_task_id


class DynamoDbResearchTaskStore:
    """Durable task/idempotency/capacity storage with transactional admission.

    The table uses the ``pk``/``sk`` keys declared by the pilot template.  A
    single DynamoDB transaction creates the task and idempotency records while
    incrementing the deterministic daily and monthly counter shards.  It never
    logs request content and maps uncertain DynamoDB responses to fail-closed
    task-store errors.
    """

    def __init__(self, *, table_name: str, client: object, policy: TaskCapacityPolicy) -> None:
        if not table_name:
            raise ValueError("research task table name is required")
        self._table_name = table_name
        self._client = client
        self._policy = policy

    def reservation_for(
        self, *, reservation_id: str, canonical_request_hash: str, now: datetime
    ) -> TaskReservation:
        return self._policy.reservation_for(
            reservation_id=reservation_id,
            canonical_request_hash=canonical_request_hash,
            now=now,
        )

    @staticmethod
    def _key(*, pk: str, sk: str) -> dict[str, dict[str, str]]:
        return {"pk": {"S": pk}, "sk": {"S": sk}}

    @staticmethod
    def _task_key(task_id: str) -> dict[str, dict[str, str]]:
        return DynamoDbResearchTaskStore._key(pk=f"TASK#{task_id}", sk="TASK")

    @staticmethod
    def _idempotency_key(idempotency_key: str) -> dict[str, dict[str, str]]:
        return DynamoDbResearchTaskStore._key(pk=f"IDEMPOTENCY#{idempotency_key}", sk="KEY")

    @staticmethod
    def _daily_counter_key(reservation: TaskReservation) -> dict[str, dict[str, str]]:
        return DynamoDbResearchTaskStore._key(
            pk=f"CAPACITY#DAY#{reservation.day_bucket}#{reservation.shard}", sk="COUNTER"
        )

    @staticmethod
    def _monthly_counter_key(reservation: TaskReservation) -> dict[str, dict[str, str]]:
        return DynamoDbResearchTaskStore._key(
            pk=f"CAPACITY#MONTH#{reservation.month_bucket}#{reservation.shard}", sk="COUNTER"
        )

    @staticmethod
    def _record_payload(record: _TaskRecord) -> str:
        return json.dumps(
            {
                "task_id": record.task_id,
                "request": {
                    "cik": record.request.cik,
                    "analysis": record.request.analysis,
                    "as_of_date": record.request.as_of_date.isoformat(),
                    "forms": record.request.forms,
                    "evidence_requests": [item.value for item in record.request.evidence_requests],
                },
                "idempotency_key": record.idempotency_key,
                "canonical_request_hash": record.canonical_request_hash,
                "policy_pointers": {
                    "evidence_release_manifest_hash": record.policy_pointers.evidence_release_manifest_hash,
                    "runtime_policy_bundle_hash": record.policy_pointers.runtime_policy_bundle_hash,
                    "release_gate_policy_hash": record.policy_pointers.release_gate_policy_hash,
                },
                "reservation": {
                    "reservation_id": record.reservation.reservation_id,
                    "shard": record.reservation.shard,
                    "day_bucket": record.reservation.day_bucket,
                    "month_bucket": record.reservation.month_bucket,
                    "reserved_micro_usd": record.reservation.reserved_micro_usd,
                },
                "state": record.state.value,
                "state_history": [state.value for state in record.state_history],
                "safe_result": record.safe_result,
                "retry_of_task_id": record.retry_of_task_id,
                "manual_retry_task_id": record.manual_retry_task_id,
                "reservation_released": record.reservation_released,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _record_from_payload(payload: str) -> _TaskRecord:
        try:
            raw = json.loads(payload)
            request_raw = raw["request"]
            pointers_raw = raw["policy_pointers"]
            reservation_raw = raw["reservation"]
            request = ResearchTaskRequest(
                cik=request_raw["cik"],
                analysis=request_raw["analysis"],
                as_of_date=date.fromisoformat(request_raw["as_of_date"]),
                forms=tuple(request_raw["forms"]),
                evidence_requests=tuple(
                    EvidenceRequestType(value) for value in request_raw["evidence_requests"]
                ),
            )
            return _TaskRecord(
                task_id=raw["task_id"],
                request=request,
                idempotency_key=raw["idempotency_key"],
                canonical_request_hash=raw["canonical_request_hash"],
                policy_pointers=PolicyControlPointers(**pointers_raw),
                reservation=TaskReservation(**reservation_raw),
                state=TaskState(raw["state"]),
                state_history=[TaskState(value) for value in raw["state_history"]],
                safe_result=raw["safe_result"],
                retry_of_task_id=raw["retry_of_task_id"],
                manual_retry_task_id=raw["manual_retry_task_id"],
                reservation_released=raw["reservation_released"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise TaskStoreUnavailableError("stored research task is invalid") from error

    def create_with_reservation(self, *, record: _TaskRecord) -> None:
        reservation = record.reservation
        task_item = {
            **self._task_key(record.task_id),
            "record_json": {"S": self._record_payload(record)},
        }
        idempotency_item = {
            **self._idempotency_key(record.idempotency_key),
            "canonical_request_hash": {"S": record.canonical_request_hash},
            "task_id": {"S": record.task_id},
        }
        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self._table_name,
                            "Item": task_item,
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                    {
                        "Put": {
                            "TableName": self._table_name,
                            "Item": idempotency_item,
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": self._table_name,
                            "Key": self._daily_counter_key(reservation),
                            "UpdateExpression": "SET #used = if_not_exists(#used, :zero) + :one",
                            "ConditionExpression": "attribute_not_exists(#used) OR #used < :limit",
                            "ExpressionAttributeNames": {"#used": "used"},
                            "ExpressionAttributeValues": {
                                ":zero": {"N": "0"},
                                ":one": {"N": "1"},
                                ":limit": {"N": str(self._policy.daily_limit_for_shard(shard=reservation.shard))},
                            },
                        }
                    },
                    {
                        "Update": {
                            "TableName": self._table_name,
                            "Key": self._monthly_counter_key(reservation),
                            "UpdateExpression": "SET #used = if_not_exists(#used, :zero) + :amount",
                            "ConditionExpression": "attribute_not_exists(#used) OR #used <= :remaining",
                            "ExpressionAttributeNames": {"#used": "used"},
                            "ExpressionAttributeValues": {
                                ":zero": {"N": "0"},
                                ":amount": {"N": str(reservation.reserved_micro_usd)},
                                ":remaining": {"N": str(self._policy.monthly_cost_limit_for_shard(shard=reservation.shard) - reservation.reserved_micro_usd)},
                            },
                        }
                    },
                ]
            )
        except Exception as error:
            response = getattr(error, "response", None)
            code = response.get("Error", {}).get("Code") if isinstance(response, Mapping) else None
            if code in {"TransactionCanceledException", "ConditionalCheckFailedException"}:
                raise TaskCapacityExceededError("task admission transaction was rejected") from error
            raise TaskStoreUnavailableError("task admission transaction is unavailable") from error

    def get(self, *, task_id: str) -> _TaskRecord:
        try:
            response = self._client.get_item(
                TableName=self._table_name, Key=self._task_key(task_id), ConsistentRead=True
            )
            item = response.get("Item")
            payload = item.get("record_json", {}).get("S") if isinstance(item, Mapping) else None
            if not isinstance(payload, str):
                raise TaskStoreUnavailableError("research task does not exist")
            return self._record_from_payload(payload)
        except TaskStoreUnavailableError:
            raise
        except Exception as error:
            raise TaskStoreUnavailableError("research task cannot be read") from error

    def existing_for_idempotency(
        self, *, idempotency_key: str, canonical_request_hash: str
    ) -> _TaskRecord | None:
        try:
            response = self._client.get_item(
                TableName=self._table_name,
                Key=self._idempotency_key(idempotency_key),
                ConsistentRead=True,
            )
            item = response.get("Item")
            if not isinstance(item, Mapping):
                return None
            stored_hash = item.get("canonical_request_hash", {}).get("S")
            task_id = item.get("task_id", {}).get("S")
            if not isinstance(stored_hash, str) or not isinstance(task_id, str):
                raise TaskStoreUnavailableError("idempotency record is invalid")
            if stored_hash != canonical_request_hash:
                raise IdempotencyConflictError("idempotency key was reused for different request content")
            return self.get(task_id=task_id)
        except (TaskStoreUnavailableError, IdempotencyConflictError):
            raise
        except Exception as error:
            raise TaskStoreUnavailableError("idempotency record cannot be read") from error

    def _replace(self, *, previous: _TaskRecord, updated: _TaskRecord) -> _TaskRecord:
        try:
            self._client.update_item(
                TableName=self._table_name,
                Key=self._task_key(previous.task_id),
                UpdateExpression="SET record_json = :updated",
                ConditionExpression="record_json = :previous",
                ExpressionAttributeValues={
                    ":previous": {"S": self._record_payload(previous)},
                    ":updated": {"S": self._record_payload(updated)},
                },
            )
            return updated
        except Exception as error:
            response = getattr(error, "response", None)
            code = response.get("Error", {}).get("Code") if isinstance(response, Mapping) else None
            if code == "ConditionalCheckFailedException":
                raise TaskStoreUnavailableError("research task changed concurrently") from error
            raise TaskStoreUnavailableError("research task cannot be updated") from error

    def transition(
        self,
        *,
        task_id: str,
        next_state: TaskState,
        safe_result: dict[str, object] | None = None,
    ) -> _TaskRecord:
        previous = self.get(task_id=task_id)
        if next_state not in _ALLOWED_TRANSITIONS.get(previous.state, frozenset()):
            raise InvalidTaskTransitionError(
                f"cannot transition task from {previous.state} to {next_state}"
            )
        updated = _TaskRecord(
            task_id=previous.task_id,
            request=previous.request,
            idempotency_key=previous.idempotency_key,
            canonical_request_hash=previous.canonical_request_hash,
            policy_pointers=previous.policy_pointers,
            reservation=previous.reservation,
            state=next_state,
            state_history=[*previous.state_history, next_state],
            safe_result=safe_result,
            retry_of_task_id=previous.retry_of_task_id,
            manual_retry_task_id=previous.manual_retry_task_id,
            reservation_released=previous.reservation_released,
        )
        return self._replace(previous=previous, updated=updated)

    def mark_reservation_released(self, *, task_id: str) -> None:
        previous = self.get(task_id=task_id)
        if previous.reservation_released:
            return
        updated = _TaskRecord(
            task_id=previous.task_id,
            request=previous.request,
            idempotency_key=previous.idempotency_key,
            canonical_request_hash=previous.canonical_request_hash,
            policy_pointers=previous.policy_pointers,
            reservation=previous.reservation,
            state=previous.state,
            state_history=previous.state_history,
            safe_result=previous.safe_result,
            retry_of_task_id=previous.retry_of_task_id,
            manual_retry_task_id=previous.manual_retry_task_id,
            reservation_released=True,
        )
        self._replace(previous=previous, updated=updated)

    def release_reservation(self, *, task_id: str) -> None:
        previous = self.get(task_id=task_id)
        if previous.reservation_released:
            return
        updated = _TaskRecord(
            task_id=previous.task_id,
            request=previous.request,
            idempotency_key=previous.idempotency_key,
            canonical_request_hash=previous.canonical_request_hash,
            policy_pointers=previous.policy_pointers,
            reservation=previous.reservation,
            state=previous.state,
            state_history=previous.state_history,
            safe_result=previous.safe_result,
            retry_of_task_id=previous.retry_of_task_id,
            manual_retry_task_id=previous.manual_retry_task_id,
            reservation_released=True,
        )
        reservation = previous.reservation
        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": self._table_name,
                            "Key": self._task_key(task_id),
                            "UpdateExpression": "SET record_json = :updated",
                            "ConditionExpression": "record_json = :previous",
                            "ExpressionAttributeValues": {
                                ":previous": {"S": self._record_payload(previous)},
                                ":updated": {"S": self._record_payload(updated)},
                            },
                        }
                    },
                    {
                        "Update": {
                            "TableName": self._table_name,
                            "Key": self._daily_counter_key(reservation),
                            "UpdateExpression": "ADD #used :decrement",
                            "ConditionExpression": "#used >= :one",
                            "ExpressionAttributeNames": {"#used": "used"},
                            "ExpressionAttributeValues": {
                                ":decrement": {"N": "-1"}, ":one": {"N": "1"}
                            },
                        }
                    },
                    {
                        "Update": {
                            "TableName": self._table_name,
                            "Key": self._monthly_counter_key(reservation),
                            "UpdateExpression": "ADD #used :decrement",
                            "ConditionExpression": "#used >= :amount",
                            "ExpressionAttributeNames": {"#used": "used"},
                            "ExpressionAttributeValues": {
                                ":decrement": {"N": str(-reservation.reserved_micro_usd)},
                                ":amount": {"N": str(reservation.reserved_micro_usd)},
                            },
                        }
                    },
                ]
            )
        except Exception as error:
            raise TaskStoreUnavailableError("task reservation cannot be released") from error

    def settle_reservation(self, *, task_id: str, actual_cost_micro_usd: int) -> None:
        previous = self.get(task_id=task_id)
        if actual_cost_micro_usd < 0 or actual_cost_micro_usd > previous.reservation.reserved_micro_usd:
            raise TaskStoreUnavailableError("provider cost exceeds its reserved capacity")
        difference = previous.reservation.reserved_micro_usd - actual_cost_micro_usd
        if difference == 0:
            return
        reservation = previous.reservation
        updated_reservation = TaskReservation(
            reservation_id=reservation.reservation_id,
            shard=reservation.shard,
            day_bucket=reservation.day_bucket,
            month_bucket=reservation.month_bucket,
            reserved_micro_usd=actual_cost_micro_usd,
        )
        updated = _TaskRecord(
            task_id=previous.task_id,
            request=previous.request,
            idempotency_key=previous.idempotency_key,
            canonical_request_hash=previous.canonical_request_hash,
            policy_pointers=previous.policy_pointers,
            reservation=updated_reservation,
            state=previous.state,
            state_history=previous.state_history,
            safe_result=previous.safe_result,
            retry_of_task_id=previous.retry_of_task_id,
            manual_retry_task_id=previous.manual_retry_task_id,
            reservation_released=previous.reservation_released,
        )
        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": self._table_name,
                            "Key": self._task_key(task_id),
                            "UpdateExpression": "SET record_json = :updated",
                            "ConditionExpression": "record_json = :previous",
                            "ExpressionAttributeValues": {
                                ":previous": {"S": self._record_payload(previous)},
                                ":updated": {"S": self._record_payload(updated)},
                            },
                        }
                    },
                    {
                        "Update": {
                            "TableName": self._table_name,
                            "Key": self._monthly_counter_key(reservation),
                            "UpdateExpression": "ADD #used :decrement",
                            "ConditionExpression": "#used >= :amount",
                            "ExpressionAttributeNames": {"#used": "used"},
                            "ExpressionAttributeValues": {
                                ":decrement": {"N": str(-difference)},
                                ":amount": {"N": str(difference)},
                            },
                        }
                    },
                ]
            )
        except Exception as error:
            raise TaskStoreUnavailableError("task reservation cannot be settled") from error

    def link_manual_retry(self, *, task_id: str, retry_task_id: str) -> None:
        previous = self.get(task_id=task_id)
        if previous.manual_retry_task_id is not None:
            raise InvalidTaskTransitionError("task already has a controlled retry")
        updated = _TaskRecord(
            task_id=previous.task_id,
            request=previous.request,
            idempotency_key=previous.idempotency_key,
            canonical_request_hash=previous.canonical_request_hash,
            policy_pointers=previous.policy_pointers,
            reservation=previous.reservation,
            state=previous.state,
            state_history=previous.state_history,
            safe_result=previous.safe_result,
            retry_of_task_id=previous.retry_of_task_id,
            manual_retry_task_id=retry_task_id,
            reservation_released=previous.reservation_released,
        )
        self._replace(previous=previous, updated=updated)


class ResearchTaskService:
    """Admission and status facade for the bounded internal task capability."""

    def __init__(
        self,
        *,
        policy_control: PolicyControlPlane,
        admission: DeterministicShardedAdmission,
        store: InMemoryResearchTaskStore,
        queue: ResearchTaskQueue,
        reconciler: ProviderReconciler | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        task_id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self._policy_control = policy_control
        self._admission = admission
        self._store = store
        self._queue = queue
        self._reconciler = reconciler or UnavailableProviderReconciler()
        self._clock = clock
        self._task_id_factory = task_id_factory
        self._submit_lock = Lock()

    def submit(
        self, *, request: ResearchTaskRequest, idempotency_key: str
    ) -> dict[str, object]:
        if not idempotency_key or len(idempotency_key) > 256:
            raise ValueError("idempotency key is invalid")
        # This local lock models the one DynamoDB transaction that will create
        # the idempotency record, task record, and reservation in production.
        with self._submit_lock:
            return self._submit_locked(
                request=request, idempotency_key=idempotency_key, retry_of_task_id=None
            )

    def _submit_locked(
        self, *, request: ResearchTaskRequest, idempotency_key: str, retry_of_task_id: str | None
    ) -> dict[str, object]:
        canonical_request_hash = request.canonical_request_hash
        existing = self._store.existing_for_idempotency(
            idempotency_key=idempotency_key,
            canonical_request_hash=canonical_request_hash,
        )
        if existing is not None:
            return self._safe_status(existing)
        pointers = self._policy_control.current_pointers()
        self._policy_control.authorize_tool(
            task_pointers=pointers, tool_name="verify_claims"
        )
        task_id = self._task_id_factory()
        reservation_factory = getattr(self._store, "reservation_for", None)
        if callable(reservation_factory):
            reservation = reservation_factory(
                reservation_id=task_id,
                canonical_request_hash=canonical_request_hash,
                now=self._clock(),
            )
        else:
            reservation = self._admission.reserve(
                reservation_id=task_id,
                canonical_request_hash=canonical_request_hash,
                now=self._clock(),
            )
        record = _TaskRecord(
            task_id=task_id,
            request=request,
            idempotency_key=idempotency_key,
            canonical_request_hash=canonical_request_hash,
            policy_pointers=pointers,
            reservation=reservation,
            state=TaskState.ACCEPTED,
            state_history=[TaskState.ACCEPTED],
            retry_of_task_id=retry_of_task_id,
        )
        try:
            create_with_reservation = getattr(self._store, "create_with_reservation", None)
            if callable(create_with_reservation):
                create_with_reservation(record=record)
            else:
                self._store.create(record=record)
            self._store.transition(task_id=task_id, next_state=TaskState.ADMITTED)
            self._store.transition(task_id=task_id, next_state=TaskState.QUEUED)
            self._queue.enqueue(task_id=task_id)
        except Exception as error:
            self._release_reservation(task_id=task_id)
            try:
                self._store.transition(task_id=task_id, next_state=TaskState.UNAVAILABLE)
            except (TaskStoreUnavailableError, InvalidTaskTransitionError):
                pass
            if isinstance(error, ResearchTaskError):
                raise
            raise TaskQueueUnavailableError("research task could not be queued") from error
        return self._safe_status(self._store.get(task_id=task_id))

    def status(self, *, task_id: str) -> dict[str, object]:
        task = self._store.get(task_id=task_id)
        self._policy_control.authorize_serving(task_pointers=task.policy_pointers)
        return self._safe_status(task)

    def cancel(self, *, task_id: str) -> dict[str, object]:
        task = self._store.get(task_id=task_id)
        if task.state is TaskState.QUEUED:
            task = self._store.transition(task_id=task_id, next_state=TaskState.CANCELED)
            self._release_if_unstarted(task=task)
        elif task.state in {TaskState.RUNNING, TaskState.RECONCILING}:
            task = self._store.transition(
                task_id=task_id, next_state=TaskState.CANCEL_REQUESTED
            )
        else:
            raise InvalidTaskTransitionError("task cannot be canceled in its current state")
        return self._safe_status(task)

    def retry(self, *, task_id: str, idempotency_key: str) -> dict[str, object]:
        if not idempotency_key or len(idempotency_key) > 256:
            raise ValueError("idempotency key is invalid")
        with self._submit_lock:
            original = self._store.get(task_id=task_id)
            if original.state not in {TaskState.UNAVAILABLE, TaskState.FAILED_UNRESOLVED}:
                raise InvalidTaskTransitionError("only an unresolved task may be retried")
            if original.manual_retry_task_id is not None or original.retry_of_task_id is not None:
                raise InvalidTaskTransitionError("only one controlled retry is permitted")
            created = self._submit_locked(
                request=original.request,
                idempotency_key=idempotency_key,
                retry_of_task_id=original.task_id,
            )
            self._store.link_manual_retry(
                task_id=original.task_id, retry_task_id=str(created["task_id"])
            )
            return created

    def reconcile(self, *, task_id: str) -> dict[str, object]:
        task = self._store.get(task_id=task_id)
        if task.state not in {TaskState.RECONCILING, TaskState.CANCEL_REQUESTED}:
            raise InvalidTaskTransitionError("task does not require provider reconciliation")
        outcome = self._reconciler.reconcile(task_id=task.task_id)
        if outcome.state is ProviderReconciliationState.NOT_STARTED:
            self._release_if_unstarted(task=task)
            task = self._store.transition(task_id=task.task_id, next_state=TaskState.UNAVAILABLE)
        elif outcome.state is ProviderReconciliationState.COMPLETED:
            assert outcome.response is not None
            safe_result = ResearchTaskWorker._safe_result(
                response=outcome.response, pointers=task.policy_pointers
            )
            self._policy_control.authorize_serving(task_pointers=task.policy_pointers)
            if outcome.actual_cost_micro_usd is not None:
                settle = getattr(self._store, "settle_reservation", None)
                if callable(settle):
                    settle(
                        task_id=task.task_id,
                        actual_cost_micro_usd=outcome.actual_cost_micro_usd,
                    )
                else:
                    self._admission.settle(
                        reservation_id=task.task_id,
                        actual_cost_micro_usd=outcome.actual_cost_micro_usd,
                    )
            target = (
                TaskState.CANCELED
                if task.state is TaskState.CANCEL_REQUESTED
                else (
                    TaskState.REQUIRES_REVIEW
                    if safe_result["requires_agent_resolution"]
                    else TaskState.COMPLETED
                )
            )
            task = self._store.transition(
                task_id=task.task_id,
                next_state=target,
                safe_result=None if target is TaskState.CANCELED else safe_result,
            )
        else:
            task = self._store.transition(
                task_id=task.task_id, next_state=TaskState.FAILED_UNRESOLVED
            )
        return self._safe_status(task)

    def _release_if_unstarted(self, *, task: _TaskRecord) -> None:
        if not task.reservation_released:
            self._release_reservation(task_id=task.task_id)

    def _release_reservation(self, *, task_id: str) -> None:
        release = getattr(self._store, "release_reservation", None)
        if callable(release):
            release(task_id=task_id)
            return
        self._admission.release(reservation_id=task_id)
        self._store.mark_reservation_released(task_id=task_id)

    @staticmethod
    def _safe_status(task: _TaskRecord) -> dict[str, object]:
        response: dict[str, object] = {
            "task_id": task.task_id,
            "state": task.state.value,
            "evidence_release_manifest_hash": task.policy_pointers.evidence_release_manifest_hash,
            "runtime_policy_bundle_hash": task.policy_pointers.runtime_policy_bundle_hash,
            "release_gate_policy_hash": task.policy_pointers.release_gate_policy_hash,
            "retry_of_task_id": task.retry_of_task_id,
        }
        if task.safe_result is not None:
            response["result"] = task.safe_result
        return response


class ResearchTaskWorker:
    """One-message worker; deterministic verification composes all verdicts."""

    def __init__(
        self,
        *,
        service: ResearchTaskService,
        store: InMemoryResearchTaskStore,
        queue: ResearchTaskQueue,
        policy_control: PolicyControlPlane,
        verifier: ApplicationService,
    ) -> None:
        self._service = service
        self._store = store
        self._queue = queue
        self._policy_control = policy_control
        self._verifier = verifier

    def run_once(self) -> dict[str, object] | None:
        message = self._queue.receive()
        if message is None:
            return None
        try:
            task = self._store.get(task_id=message.task_id)
        except TaskStoreUnavailableError:
            self._queue.fail(message=message)
            return None
        if task.state is TaskState.CANCELED:
            self._queue.acknowledge(message=message)
            return self._service._safe_status(task)
        try:
            task = self._store.transition(task_id=task.task_id, next_state=TaskState.RUNNING)
            self._policy_control.authorize_tool(
                task_pointers=task.policy_pointers, tool_name="verify_claims"
            )
            response = self._verifier.verify(
                cik=task.request.cik, request=task.request.verify_request()
            )
            safe_result = self._safe_result(
                response=response, pointers=task.policy_pointers
            )
            next_state = (
                TaskState.REQUIRES_REVIEW
                if safe_result["requires_agent_resolution"]
                else TaskState.COMPLETED
            )
            self._policy_control.authorize_serving(task_pointers=task.policy_pointers)
            current = self._store.get(task_id=task.task_id)
            if current.state is TaskState.CANCEL_REQUESTED:
                task = self._store.transition(
                    task_id=task.task_id, next_state=TaskState.CANCELED
                )
                self._queue.acknowledge(message=message)
                return self._service._safe_status(task)
            task = self._store.transition(
                task_id=task.task_id, next_state=next_state, safe_result=safe_result
            )
            self._queue.acknowledge(message=message)
            return self._service._safe_status(task)
        except ModelUnavailableError:
            task = self._store.transition(task_id=task.task_id, next_state=TaskState.RECONCILING)
            self._queue.acknowledge(message=message)
            return self._service._safe_status(task)
        except PolicyControlError:
            task = self._store.transition(task_id=task.task_id, next_state=TaskState.UNAVAILABLE)
            self._queue.acknowledge(message=message)
            return self._service._safe_status(task)
        except Exception:
            task = self._store.transition(
                task_id=task.task_id, next_state=TaskState.FAILED_UNRESOLVED
            )
            self._queue.acknowledge(message=message)
            return self._service._safe_status(task)

    @staticmethod
    def _safe_result(
        *, response: Mapping[str, object], pointers: PolicyControlPointers
    ) -> dict[str, object]:
        audit = response.get("audit_manifest")
        if not isinstance(audit, Mapping):
            raise TaskStoreUnavailableError("verification response has no audit manifest")
        expected = {
            "evidence_release_manifest_hash": pointers.evidence_release_manifest_hash,
            "runtime_policy_bundle_hash": pointers.runtime_policy_bundle_hash,
            "release_gate_policy_hash": pointers.release_gate_policy_hash,
        }
        if any(audit.get(key) != value for key, value in expected.items()):
            raise TaskStoreUnavailableError("verification audit policy hashes do not match task")
        return agent_safe_result(response)
