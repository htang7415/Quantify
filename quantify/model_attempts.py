"""Attributable, replay-visible model-attempt records without raw model data.

This module performs no provider call, retry, reconciliation, persistence, or
publication. It records only independently admitted model identity, hashes,
bounded usage, provider outcome, and deterministic validation outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
import re


_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_LIMITATION = (
    "Attribution record only; no raw prompt, provider output, hidden reasoning, "
    "credential, retry authorization, fallback authorization, or verdict."
)


class ModelAttemptError(ValueError):
    """A model-attempt admission or provider outcome failed closed."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class ProviderAttemptStatus(StrEnum):
    NOT_STARTED = "not_started"
    COMPLETED = "completed"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


class ModelOutputValidationStatus(StrEnum):
    NOT_EVALUATED = "not_evaluated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _content_hash(value: object) -> str:
    try:
        return sha256(_canonical_json(value)).hexdigest()
    except (TypeError, ValueError) as error:
        raise ModelAttemptError("invalid_attempt", "attempt is not canonical JSON") from error


def _require_hash(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value):
        raise ModelAttemptError("invalid_attempt", f"{field} must be a lowercase SHA-256 hash")


def _require_id(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        raise ModelAttemptError("invalid_attempt", f"{field} is invalid")


def _require_token_cap(value: int, *, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ModelAttemptError("invalid_attempt", f"{field} is invalid")


@dataclass(frozen=True, slots=True)
class ModelAttemptAdmission:
    task_id: str
    plan_request_hash: str
    runtime_policy_bundle_hash: str
    provider: str
    model_id: str
    model_version: str
    secret_version: str
    prompt_contract_hash: str
    tool_contract_hash: str
    maximum_model_calls: int
    maximum_input_tokens: int
    maximum_output_tokens: int

    def __post_init__(self) -> None:
        for field in (
            "task_id",
            "provider",
            "model_id",
            "model_version",
            "secret_version",
        ):
            _require_id(getattr(self, field), field=field)
        for field in (
            "plan_request_hash",
            "runtime_policy_bundle_hash",
            "prompt_contract_hash",
            "tool_contract_hash",
        ):
            _require_hash(getattr(self, field), field=field)
        if (
            not isinstance(self.maximum_model_calls, int)
            or isinstance(self.maximum_model_calls, bool)
            or not 1 <= self.maximum_model_calls <= 8
        ):
            raise ModelAttemptError("invalid_attempt", "maximum_model_calls is invalid")
        _require_token_cap(self.maximum_input_tokens, field="maximum_input_tokens")
        _require_token_cap(self.maximum_output_tokens, field="maximum_output_tokens")


@dataclass(frozen=True, slots=True)
class ProviderAttemptOutcome:
    status: ProviderAttemptStatus
    provider_attempt_id: str | None = None
    output_hash: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    actual_cost_micro_usd: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ProviderAttemptStatus):
            raise ModelAttemptError("invalid_attempt", "provider status is invalid")
        if self.provider_attempt_id is not None:
            _require_id(self.provider_attempt_id, field="provider_attempt_id")
        if self.output_hash is not None:
            _require_hash(self.output_hash, field="output_hash")
        for field in ("input_tokens", "output_tokens", "actual_cost_micro_usd"):
            value = getattr(self, field)
            if value is not None:
                _require_token_cap(value, field=field)
        if self.status is ProviderAttemptStatus.COMPLETED:
            if (
                self.provider_attempt_id is None
                or self.output_hash is None
                or self.input_tokens is None
                or self.output_tokens is None
                or self.actual_cost_micro_usd is None
            ):
                raise ModelAttemptError(
                    "invalid_attempt", "completed outcome requires attribution and usage"
                )
        elif any(
            value is not None
            for value in (
                self.output_hash,
                self.input_tokens,
                self.output_tokens,
                self.actual_cost_micro_usd,
            )
        ):
            raise ModelAttemptError(
                "invalid_attempt", "incomplete provider outcome cannot carry output or usage"
            )
        if (
            self.status in {ProviderAttemptStatus.NOT_STARTED, ProviderAttemptStatus.UNAVAILABLE}
            and self.provider_attempt_id is not None
        ):
            raise ModelAttemptError(
                "invalid_attempt", "provider attempt ID requires a started or completed attempt"
            )


@dataclass(frozen=True, slots=True)
class ModelAttemptRecord:
    attempt_id: str
    task_id: str
    plan_request_hash: str
    runtime_policy_bundle_hash: str
    sequence_number: int
    provider: str
    model_id: str
    model_version: str
    secret_version: str
    prompt_contract_hash: str
    tool_contract_hash: str
    provider_status: ProviderAttemptStatus
    validation_status: ModelOutputValidationStatus
    provider_attempt_id: str | None
    output_hash: str | None
    input_tokens: int | None
    output_tokens: int | None
    actual_cost_micro_usd: int | None
    schema_version: str = "model-attempt.v1"

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id,
            "task_id": self.task_id,
            "plan_request_hash": self.plan_request_hash,
            "runtime_policy_bundle_hash": self.runtime_policy_bundle_hash,
            "sequence_number": self.sequence_number,
            "model": {
                "provider": self.provider,
                "model_id": self.model_id,
                "model_version": self.model_version,
                "secret_version": self.secret_version,
                "prompt_contract_hash": self.prompt_contract_hash,
                "tool_contract_hash": self.tool_contract_hash,
            },
            "provider_status": self.provider_status.value,
            "validation_status": self.validation_status.value,
            "provider_attempt_id": self.provider_attempt_id,
            "output_hash": self.output_hash,
            "usage": (
                {
                    "input_tokens": self.input_tokens,
                    "output_tokens": self.output_tokens,
                    "actual_cost_micro_usd": self.actual_cost_micro_usd,
                }
                if self.provider_status is ProviderAttemptStatus.COMPLETED
                else None
            ),
            "limitations": [_LIMITATION],
        }

    @property
    def record_hash(self) -> str:
        return _content_hash(self.to_document())


class DeterministicModelAttemptRecorder:
    """Bind one observed provider outcome to its exact admission."""

    def record(
        self,
        *,
        admission: ModelAttemptAdmission,
        sequence_number: int,
        outcome: ProviderAttemptOutcome,
        validation_status: ModelOutputValidationStatus,
    ) -> ModelAttemptRecord:
        if not isinstance(admission, ModelAttemptAdmission):
            raise ModelAttemptError("invalid_attempt", "model admission is invalid")
        if (
            not isinstance(sequence_number, int)
            or isinstance(sequence_number, bool)
            or not 1 <= sequence_number <= admission.maximum_model_calls
        ):
            raise ModelAttemptError("budget_exceeded", "model-call sequence exceeds admission")
        if not isinstance(outcome, ProviderAttemptOutcome) or not isinstance(
            validation_status, ModelOutputValidationStatus
        ):
            raise ModelAttemptError("invalid_attempt", "attempt outcome is invalid")
        if outcome.status is ProviderAttemptStatus.COMPLETED:
            if validation_status is ModelOutputValidationStatus.NOT_EVALUATED:
                raise ModelAttemptError(
                    "invalid_attempt", "completed output requires deterministic validation"
                )
            assert outcome.input_tokens is not None and outcome.output_tokens is not None
            if (
                outcome.input_tokens > admission.maximum_input_tokens
                or outcome.output_tokens > admission.maximum_output_tokens
            ):
                raise ModelAttemptError("budget_exceeded", "token usage exceeds admission")
        elif validation_status is not ModelOutputValidationStatus.NOT_EVALUATED:
            raise ModelAttemptError(
                "invalid_attempt", "incomplete output cannot have a validation verdict"
            )
        identity = {
            "task_id": admission.task_id,
            "plan_request_hash": admission.plan_request_hash,
            "runtime_policy_bundle_hash": admission.runtime_policy_bundle_hash,
            "sequence_number": sequence_number,
            "provider": admission.provider,
            "model_id": admission.model_id,
            "model_version": admission.model_version,
            "secret_version": admission.secret_version,
            "prompt_contract_hash": admission.prompt_contract_hash,
            "tool_contract_hash": admission.tool_contract_hash,
            "provider_status": outcome.status.value,
            "validation_status": validation_status.value,
            "provider_attempt_id": outcome.provider_attempt_id,
            "output_hash": outcome.output_hash,
            "input_tokens": outcome.input_tokens,
            "output_tokens": outcome.output_tokens,
            "actual_cost_micro_usd": outcome.actual_cost_micro_usd,
        }
        attempt_hash = _content_hash(identity)
        return ModelAttemptRecord(
            attempt_id=f"model-attempt-{attempt_hash[:32]}",
            task_id=admission.task_id,
            plan_request_hash=admission.plan_request_hash,
            runtime_policy_bundle_hash=admission.runtime_policy_bundle_hash,
            sequence_number=sequence_number,
            provider=admission.provider,
            model_id=admission.model_id,
            model_version=admission.model_version,
            secret_version=admission.secret_version,
            prompt_contract_hash=admission.prompt_contract_hash,
            tool_contract_hash=admission.tool_contract_hash,
            provider_status=outcome.status,
            validation_status=validation_status,
            provider_attempt_id=outcome.provider_attempt_id,
            output_hash=outcome.output_hash,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            actual_cost_micro_usd=outcome.actual_cost_micro_usd,
        )
