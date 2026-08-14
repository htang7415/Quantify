"""Deterministic, grounded review-task records for bounded agent work.

Creating one of these records marks a safe ``requires_review`` state. It does
not persist, assign, notify, approve, publish, or compose a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
import re

from quantify.research_answers import has_prohibited_investment_output
from quantify.research_intents import ResearchIntent


_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
_URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
_LIMITATION = (
    "Deterministic review-required record only; no reviewer assignment, approval, "
    "persistence, notification, publication permission, model call, or verdict."
)


class ReviewTaskError(ValueError):
    """A review request, grounding context, or result failed closed."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


ReviewTaskType = ResearchIntent


class ReviewOrigin(StrEnum):
    BOUNDED_AGENT = "bounded_agent"
    DETERMINISTIC_VALIDATOR = "deterministic_validator"
    DETERMINISTIC_VERIFIER = "deterministic_verifier"
    POLICY_CONTROL = "policy_control"


class ReviewReason(StrEnum):
    AMBIGUOUS_EVIDENCE = "ambiguous_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    MISSING_REQUIRED_EVIDENCE = "missing_required_evidence"
    INTERPRETATION_REQUIRES_REVIEW = "interpretation_requires_review"
    VERIFICATION_REQUIRES_AGENT_RESOLUTION = (
        "verification_requires_agent_resolution"
    )
    PUBLICATION_POLICY_REQUIRES_REVIEW = "publication_policy_requires_review"


_REASONS_BY_ORIGIN = {
    ReviewOrigin.BOUNDED_AGENT: frozenset(
        {
            ReviewReason.AMBIGUOUS_EVIDENCE,
            ReviewReason.CONFLICTING_EVIDENCE,
            ReviewReason.MISSING_REQUIRED_EVIDENCE,
            ReviewReason.INTERPRETATION_REQUIRES_REVIEW,
        }
    ),
    ReviewOrigin.DETERMINISTIC_VALIDATOR: frozenset(
        {
            ReviewReason.AMBIGUOUS_EVIDENCE,
            ReviewReason.CONFLICTING_EVIDENCE,
            ReviewReason.MISSING_REQUIRED_EVIDENCE,
            ReviewReason.INTERPRETATION_REQUIRES_REVIEW,
        }
    ),
    ReviewOrigin.DETERMINISTIC_VERIFIER: frozenset(
        {ReviewReason.VERIFICATION_REQUIRES_AGENT_RESOLUTION}
    ),
    ReviewOrigin.POLICY_CONTROL: frozenset(
        {ReviewReason.PUBLICATION_POLICY_REQUIRES_REVIEW}
    ),
}


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _require_hash(value: str, *, field: str, code: str) -> None:
    if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value):
        raise ReviewTaskError(code, f"{field} must be a lowercase SHA-256 hash")


def _require_text(value: str, *, field: str, code: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReviewTaskError(code, f"{field} is invalid")


def _validate_question(value: str, *, code: str) -> None:
    _require_text(value, field="question", code=code)
    if (
        len(value) > 500
        or "\n" in value
        or "\r" in value
        or not value.endswith("?")
        or _URL_PATTERN.search(value)
    ):
        raise ReviewTaskError(code, "question must be one concise URL-free question")
    if has_prohibited_investment_output(value):
        raise ReviewTaskError(code, "question contains prohibited investment output")


def _validate_hashes(
    values: tuple[str, ...],
    *,
    field: str,
    minimum: int,
    maximum: int,
    code: str,
) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum:
        raise ReviewTaskError(code, f"{field} must contain {minimum} to {maximum} hashes")
    for value in values:
        _require_hash(value, field=field, code=code)
    if len(set(values)) != len(values):
        raise ReviewTaskError(code, f"{field} must be unique")
    return tuple(sorted(values))


def _validate_ids(
    values: tuple[str, ...], *, field: str, code: str
) -> tuple[str, ...]:
    if (
        not isinstance(values, tuple)
        or len(values) > 32
        or any(
            not isinstance(value, str) or not _ID_PATTERN.fullmatch(value)
            for value in values
        )
    ):
        raise ReviewTaskError(code, f"{field} must contain at most 32 identifiers")
    if len(set(values)) != len(values):
        raise ReviewTaskError(code, f"{field} must be unique")
    return tuple(sorted(values))


def _validate_origin_reason(
    origin: ReviewOrigin, reason: ReviewReason, *, code: str
) -> None:
    if not isinstance(origin, ReviewOrigin) or not isinstance(reason, ReviewReason):
        raise ReviewTaskError(code, "review origin or reason is invalid")
    if reason not in _REASONS_BY_ORIGIN[origin]:
        raise ReviewTaskError(code, "review reason is not permitted for its origin")


@dataclass(frozen=True, slots=True)
class ApprovedReviewTaskRequest:
    task_type: ReviewTaskType
    review_origin: ReviewOrigin
    reason: ReviewReason
    question: str
    release_id: str
    release_manifest_hash: str
    runtime_policy_bundle_hash: str
    release_gate_policy_hash: str
    source_result_hashes: tuple[str, ...]
    audit_manifest_hash: str
    derived_from_statement_ids: tuple[str, ...] = ()
    derived_from_citation_ids: tuple[str, ...] = ()
    schema_version: str = "approved-review-task-request.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "approved-review-task-request.v1":
            raise ReviewTaskError("invalid_request", "request schema version is invalid")
        if not isinstance(self.task_type, ReviewTaskType):
            raise ReviewTaskError("invalid_request", "task_type is invalid")
        _validate_origin_reason(self.review_origin, self.reason, code="invalid_request")
        _validate_question(self.question, code="invalid_request")
        _require_text(self.release_id, field="release_id", code="invalid_request")
        for field in (
            "release_manifest_hash",
            "runtime_policy_bundle_hash",
            "release_gate_policy_hash",
            "audit_manifest_hash",
        ):
            _require_hash(getattr(self, field), field=field, code="invalid_request")
        object.__setattr__(
            self,
            "source_result_hashes",
            _validate_hashes(
                self.source_result_hashes,
                field="source_result_hashes",
                minimum=1,
                maximum=8,
                code="invalid_request",
            ),
        )
        object.__setattr__(
            self,
            "derived_from_statement_ids",
            _validate_ids(
                self.derived_from_statement_ids,
                field="derived_from_statement_ids",
                code="invalid_request",
            ),
        )
        object.__setattr__(
            self,
            "derived_from_citation_ids",
            _validate_ids(
                self.derived_from_citation_ids,
                field="derived_from_citation_ids",
                code="invalid_request",
            ),
        )
        if not self.derived_from_statement_ids and not self.derived_from_citation_ids:
            raise ReviewTaskError("invalid_request", "review task is not grounded")

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "task_type": self.task_type.value,
            "review_origin": self.review_origin.value,
            "reason": self.reason.value,
            "question": self.question,
            "release": {
                "release_id": self.release_id,
                "manifest_hash": self.release_manifest_hash,
            },
            "policy": {
                "runtime_policy_bundle_hash": self.runtime_policy_bundle_hash,
                "release_gate_policy_hash": self.release_gate_policy_hash,
            },
            "source_result_hashes": list(self.source_result_hashes),
            "derived_from_statement_ids": list(self.derived_from_statement_ids),
            "derived_from_citation_ids": list(self.derived_from_citation_ids),
            "audit_manifest_hash": self.audit_manifest_hash,
        }

    @property
    def request_hash(self) -> str:
        return sha256(_canonical_json(self.to_document())).hexdigest()


@dataclass(frozen=True, slots=True)
class ReviewTaskGroundingContext:
    task_type: ReviewTaskType
    review_origin: ReviewOrigin
    authorized_question: str
    release_id: str
    release_manifest_hash: str
    runtime_policy_bundle_hash: str
    release_gate_policy_hash: str
    audit_manifest_hash: str
    authorized_source_result_hashes: tuple[str, ...]
    authorized_statement_ids: tuple[str, ...] = ()
    authorized_citation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.task_type, ReviewTaskType):
            raise ReviewTaskError("invalid_context", "task_type is invalid")
        if not isinstance(self.review_origin, ReviewOrigin):
            raise ReviewTaskError("invalid_context", "review_origin is invalid")
        _validate_question(self.authorized_question, code="invalid_context")
        _require_text(self.release_id, field="release_id", code="invalid_context")
        for field in (
            "release_manifest_hash",
            "runtime_policy_bundle_hash",
            "release_gate_policy_hash",
            "audit_manifest_hash",
        ):
            _require_hash(getattr(self, field), field=field, code="invalid_context")
        object.__setattr__(
            self,
            "authorized_source_result_hashes",
            _validate_hashes(
                self.authorized_source_result_hashes,
                field="authorized_source_result_hashes",
                minimum=1,
                maximum=8,
                code="invalid_context",
            ),
        )
        object.__setattr__(
            self,
            "authorized_statement_ids",
            _validate_ids(
                self.authorized_statement_ids,
                field="authorized_statement_ids",
                code="invalid_context",
            ),
        )
        object.__setattr__(
            self,
            "authorized_citation_ids",
            _validate_ids(
                self.authorized_citation_ids,
                field="authorized_citation_ids",
                code="invalid_context",
            ),
        )


@dataclass(frozen=True, slots=True)
class ApprovedReviewTaskResult:
    request: ApprovedReviewTaskRequest
    grounding_context: ReviewTaskGroundingContext
    schema_version: str = "approved-review-task-result.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "approved-review-task-result.v1":
            raise ReviewTaskError("invalid_result", "result schema version is invalid")
        if not isinstance(self.request, ApprovedReviewTaskRequest) or not isinstance(
            self.grounding_context, ReviewTaskGroundingContext
        ):
            raise ReviewTaskError("invalid_result", "result bindings are invalid")
        _validate_binding(self.request, self.grounding_context)

    @property
    def review_task_id(self) -> str:
        return f"review-{self.request.request_hash[:32]}"

    def to_document(self) -> dict[str, object]:
        request = self.request.to_document()
        return {
            "schema_version": self.schema_version,
            "request_hash": self.request.request_hash,
            "review_task_id": self.review_task_id,
            "status": "requires_review",
            **{key: value for key, value in request.items() if key != "schema_version"},
            "limitation": _LIMITATION,
        }

    @property
    def result_hash(self) -> str:
        return sha256(_canonical_json(self.to_document())).hexdigest()


def _validate_binding(
    request: ApprovedReviewTaskRequest,
    context: ReviewTaskGroundingContext,
) -> None:
    if (
        request.task_type != context.task_type
        or request.review_origin != context.review_origin
        or request.question != context.authorized_question
        or request.release_id != context.release_id
        or request.release_manifest_hash != context.release_manifest_hash
        or request.runtime_policy_bundle_hash != context.runtime_policy_bundle_hash
        or request.release_gate_policy_hash != context.release_gate_policy_hash
        or request.audit_manifest_hash != context.audit_manifest_hash
    ):
        raise ReviewTaskError(
            "grounding_mismatch", "review task differs from its admitted context"
        )
    if not set(request.source_result_hashes).issubset(
        context.authorized_source_result_hashes
    ):
        raise ReviewTaskError(
            "source_result_not_authorized", "source result hash is not admitted"
        )
    if not set(request.derived_from_statement_ids).issubset(
        context.authorized_statement_ids
    ):
        raise ReviewTaskError(
            "statement_not_authorized", "statement reference is not admitted"
        )
    if not set(request.derived_from_citation_ids).issubset(
        context.authorized_citation_ids
    ):
        raise ReviewTaskError(
            "citation_not_authorized", "citation reference is not admitted"
        )


class DeterministicReviewTaskAdapter:
    """Create one replayable non-persistent review-required record."""

    def create(
        self,
        *,
        request: ApprovedReviewTaskRequest,
        grounding_context: ReviewTaskGroundingContext,
    ) -> ApprovedReviewTaskResult:
        return ApprovedReviewTaskResult(
            request=request,
            grounding_context=grounding_context,
        )
