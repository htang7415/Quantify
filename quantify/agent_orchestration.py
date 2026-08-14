"""Provider-free evaluation boundary for one bounded agent-planning attempt.

This module accepts a synthetic or already-observed provider outcome. It does
not call a model, execute a tool, persist a record, serve an answer, or retry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from quantify.agent_plans import (
    AgentPlanError,
    AgentPlanGroundingContext,
    AgentPlanRequest,
    AgentPlanResult,
    DeterministicAgentPlanAdapter,
    hash_document,
)
from quantify.model_attempts import (
    DeterministicModelAttemptRecorder,
    ModelAttemptAdmission,
    ModelAttemptError,
    ModelAttemptRecord,
    ModelOutputValidationStatus,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)


@dataclass(frozen=True, slots=True)
class AgentPlanningEvaluation:
    plan: AgentPlanResult | None
    model_attempt: ModelAttemptRecord
    rejection_code: str | None

    @property
    def accepted(self) -> bool:
        return self.plan is not None and self.rejection_code is None


class ProviderFreeAgentPlanningBoundary:
    """Bind, validate, and safely record one already-observed plan proposal."""

    def evaluate(
        self,
        *,
        request: AgentPlanRequest,
        grounding_context: AgentPlanGroundingContext,
        admission: ModelAttemptAdmission,
        sequence_number: int,
        outcome: ProviderAttemptOutcome,
        proposed_plan: Mapping[str, object] | None,
    ) -> AgentPlanningEvaluation:
        grounding_context.validate_request(request)
        self._validate_admission(request=request, admission=admission)
        recorder = DeterministicModelAttemptRecorder()
        if outcome.status is not ProviderAttemptStatus.COMPLETED:
            if proposed_plan is not None:
                raise ModelAttemptError(
                    "invalid_attempt", "incomplete provider outcome cannot carry a proposal"
                )
            record = recorder.record(
                admission=admission,
                sequence_number=sequence_number,
                outcome=outcome,
                validation_status=ModelOutputValidationStatus.NOT_EVALUATED,
            )
            return AgentPlanningEvaluation(
                plan=None,
                model_attempt=record,
                rejection_code=outcome.status.value,
            )
        if proposed_plan is None:
            raise ModelAttemptError(
                "invalid_attempt", "completed provider outcome requires a proposal"
            )
        proposal_hash = hash_document(proposed_plan)
        if outcome.output_hash != proposal_hash:
            raise ModelAttemptError(
                "output_mismatch", "provider output hash differs from the proposal"
            )
        try:
            plan = DeterministicAgentPlanAdapter().validate(
                request=request,
                grounding_context=grounding_context,
                proposed_plan=proposed_plan,
            )
        except AgentPlanError as error:
            record = recorder.record(
                admission=admission,
                sequence_number=sequence_number,
                outcome=outcome,
                validation_status=ModelOutputValidationStatus.REJECTED,
            )
            return AgentPlanningEvaluation(
                plan=None,
                model_attempt=record,
                rejection_code=error.code,
            )
        record = recorder.record(
            admission=admission,
            sequence_number=sequence_number,
            outcome=outcome,
            validation_status=ModelOutputValidationStatus.ACCEPTED,
        )
        return AgentPlanningEvaluation(
            plan=plan,
            model_attempt=record,
            rejection_code=None,
        )

    @staticmethod
    def _validate_admission(
        *, request: AgentPlanRequest, admission: ModelAttemptAdmission
    ) -> None:
        if (
            admission.task_id != request.task_id
            or admission.plan_request_hash != request.request_hash
            or admission.runtime_policy_bundle_hash
            != request.runtime_policy_bundle_hash
            or admission.prompt_contract_hash != request.prompt_contract_hash
            or admission.tool_contract_hash != request.tool_contract_hash
            or admission.maximum_model_calls != request.maximum_model_calls
        ):
            raise ModelAttemptError(
                "scope_mismatch", "model admission differs from the plan request"
            )
