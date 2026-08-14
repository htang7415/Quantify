from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from quantify.agent_orchestration import ProviderFreeAgentPlanningBoundary
from quantify.agent_plans import (
    AgentPlanError,
    AgentPlanGroundingContext,
    AgentPlanRequest,
    AgentPlanStatus,
    DeterministicAgentPlanAdapter,
    hash_document,
    question_hash,
)
from quantify.model_attempts import (
    DeterministicModelAttemptRecorder,
    ModelAttemptAdmission,
    ModelAttemptError,
    ModelOutputValidationStatus,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from quantify.research_intents import AgentToolName, ResearchIntent


QUESTION = "Compare the released revenue periods and explain the filing context."
RELEASE_HASH = "a" * 64
RUNTIME_HASH = "b" * 64
GATE_HASH = "c" * 64
PROMPT_HASH = "d" * 64
TOOL_HASH = "e" * 64


def request() -> AgentPlanRequest:
    return AgentPlanRequest(
        task_id="task-001",
        task_intent=ResearchIntent.ANALYZE,
        question_hash=question_hash(QUESTION),
        cik="789019",
        as_of=date(2024, 7, 30),
        release_id="release-001",
        release_manifest_hash=RELEASE_HASH,
        runtime_policy_bundle_hash=RUNTIME_HASH,
        release_gate_policy_hash=GATE_HASH,
        allowed_tools=(
            AgentToolName.CREATE_REVIEW_TASK,
            AgentToolName.NARRATIVE_CONTEXT,
            AgentToolName.CALCULATE_APPROVED_EVIDENCE,
            AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
        ),
        maximum_actions=4,
        maximum_model_calls=1,
        prompt_contract_hash=PROMPT_HASH,
        tool_contract_hash=TOOL_HASH,
    )


def context(plan_request: AgentPlanRequest | None = None) -> AgentPlanGroundingContext:
    item = plan_request or request()
    return AgentPlanGroundingContext(
        task_id=item.task_id,
        task_intent=item.task_intent,
        authorized_question=QUESTION,
        cik=item.cik,
        as_of=item.as_of,
        release_id=item.release_id,
        release_manifest_hash=item.release_manifest_hash,
        runtime_policy_bundle_hash=item.runtime_policy_bundle_hash,
        release_gate_policy_hash=item.release_gate_policy_hash,
        authorized_tools=item.allowed_tools,
        maximum_actions=item.maximum_actions,
        maximum_model_calls=item.maximum_model_calls,
        prompt_contract_hash=item.prompt_contract_hash,
        tool_contract_hash=item.tool_contract_hash,
    )


def proposal() -> dict[str, object]:
    return {
        "status": "planned",
        "stages": [
            {
                "stage_id": "search",
                "tool_name": "search_approved_evidence_release",
                "purpose": "retrieve_facts",
                "depends_on_stage_ids": [],
            },
            {
                "stage_id": "calculate",
                "tool_name": "calculate_approved_evidence",
                "purpose": "calculate",
                "depends_on_stage_ids": ["search"],
            },
            {
                "stage_id": "context",
                "tool_name": "narrative_context",
                "purpose": "retrieve_context",
                "depends_on_stage_ids": [],
            },
            {
                "stage_id": "review",
                "tool_name": "create_review_task",
                "purpose": "route_review",
                "depends_on_stage_ids": ["calculate", "context"],
            },
        ],
        "unavailable_reason": None,
    }


def admission(plan_request: AgentPlanRequest | None = None) -> ModelAttemptAdmission:
    item = plan_request or request()
    return ModelAttemptAdmission(
        task_id=item.task_id,
        plan_request_hash=item.request_hash,
        runtime_policy_bundle_hash=item.runtime_policy_bundle_hash,
        provider="synthetic-provider",
        model_id="pinned-planner",
        model_version="v1",
        secret_version="secret-v1",
        prompt_contract_hash=item.prompt_contract_hash,
        tool_contract_hash=item.tool_contract_hash,
        maximum_model_calls=item.maximum_model_calls,
        maximum_input_tokens=1_000,
        maximum_output_tokens=500,
    )


def completed_outcome(value: dict[str, object] | None = None) -> ProviderAttemptOutcome:
    document = value or proposal()
    return ProviderAttemptOutcome(
        status=ProviderAttemptStatus.COMPLETED,
        provider_attempt_id="provider-attempt-001",
        output_hash=hash_document(document),
        input_tokens=120,
        output_tokens=80,
        actual_cost_micro_usd=250,
    )


def test_plan_request_is_scope_bound_and_does_not_persist_question() -> None:
    item = request()
    document = item.to_document()

    assert item.cik == "0000789019"
    assert document["question_hash"] == question_hash(QUESTION)
    assert QUESTION not in str(document)
    assert document["allowed_tools"] == [
        "search_approved_evidence_release",
        "calculate_approved_evidence",
        "narrative_context",
        "create_review_task",
    ]
    context(item).validate_request(item)


def test_valid_plan_is_deterministic_and_non_executable() -> None:
    item = request()
    adapter = DeterministicAgentPlanAdapter()
    first = adapter.validate(
        request=item,
        grounding_context=context(item),
        proposed_plan=proposal(),
    )
    second = adapter.validate(
        request=item,
        grounding_context=context(item),
        proposed_plan=proposal(),
    )

    assert first == second
    assert first.status is AgentPlanStatus.PLANNED
    assert first.plan_id.startswith("agent-plan-")
    assert first.to_document()["stages"][0] == {
        "stage_id": "search",
        "tool_name": "search_approved_evidence_release",
        "purpose": "retrieve_facts",
        "depends_on_stage_ids": [],
    }
    assert "arguments" not in str(first.to_document())
    assert "verdict" in first.to_document()["limitations"][0]


def test_unavailable_is_a_complete_plan_state() -> None:
    item = request()
    result = DeterministicAgentPlanAdapter().validate(
        request=item,
        grounding_context=context(item),
        proposed_plan={
            "status": "unavailable",
            "stages": [],
            "unavailable_reason": "unsupported_question",
        },
    )

    assert result.status is AgentPlanStatus.UNAVAILABLE
    assert result.stages == ()
    assert result.to_document()["unavailable_reason"] == "unsupported_question"


def test_request_cannot_authorize_its_own_scope() -> None:
    item = request()
    with pytest.raises(AgentPlanError, match="differs from admission"):
        context(item).validate_request(replace(item, release_manifest_hash="f" * 64))


@pytest.mark.parametrize(
    "mutate,code",
    [
        (
            lambda value: value["stages"][0].update(
                {"tool_name": "verify_claims", "purpose": "verify_claim"}
            ),
            "tool_not_permitted",
        ),
        (
            lambda value: value["stages"][1].update({"depends_on_stage_ids": []}),
            "invalid_dependency",
        ),
        (
            lambda value: value["stages"][0].update({"purpose": "calculate"}),
            "invalid_proposal",
        ),
        (
            lambda value: value["stages"][0].update(
                {"depends_on_stage_ids": ["calculate"]}
            ),
            "invalid_dependency",
        ),
    ],
)
def test_invalid_or_overbroad_model_plans_fail_closed(mutate, code: str) -> None:
    item = request()
    value = proposal()
    mutate(value)

    with pytest.raises(AgentPlanError) as captured:
        DeterministicAgentPlanAdapter().validate(
            request=item,
            grounding_context=context(item),
            proposed_plan=value,
        )
    assert captured.value.code == code


def test_provider_free_boundary_accepts_and_attributes_valid_plan() -> None:
    item = request()
    value = proposal()
    evaluation = ProviderFreeAgentPlanningBoundary().evaluate(
        request=item,
        grounding_context=context(item),
        admission=admission(item),
        sequence_number=1,
        outcome=completed_outcome(value),
        proposed_plan=value,
    )

    assert evaluation.accepted
    assert evaluation.plan is not None
    assert evaluation.model_attempt.validation_status is ModelOutputValidationStatus.ACCEPTED
    document = evaluation.model_attempt.to_document()
    assert document["provider_attempt_id"] == "provider-attempt-001"
    assert document["output_hash"] == hash_document(value)
    assert QUESTION not in str(document)
    assert value not in document.values()


def test_invalid_completed_plan_is_recorded_rejected_without_a_plan() -> None:
    item = request()
    value = proposal()
    value["stages"][0]["tool_name"] = "verify_claims"
    value["stages"][0]["purpose"] = "verify_claim"

    evaluation = ProviderFreeAgentPlanningBoundary().evaluate(
        request=item,
        grounding_context=context(item),
        admission=admission(item),
        sequence_number=1,
        outcome=completed_outcome(value),
        proposed_plan=value,
    )

    assert not evaluation.accepted
    assert evaluation.plan is None
    assert evaluation.rejection_code == "tool_not_permitted"
    assert evaluation.model_attempt.validation_status is ModelOutputValidationStatus.REJECTED


def test_unavailable_provider_cannot_smuggle_a_proposal() -> None:
    item = request()
    outcome = ProviderAttemptOutcome(status=ProviderAttemptStatus.UNAVAILABLE)

    with pytest.raises(ModelAttemptError, match="cannot carry a proposal"):
        ProviderFreeAgentPlanningBoundary().evaluate(
            request=item,
            grounding_context=context(item),
            admission=admission(item),
            sequence_number=1,
            outcome=outcome,
            proposed_plan=proposal(),
        )

    evaluation = ProviderFreeAgentPlanningBoundary().evaluate(
        request=item,
        grounding_context=context(item),
        admission=admission(item),
        sequence_number=1,
        outcome=outcome,
        proposed_plan=None,
    )
    assert not evaluation.accepted
    assert evaluation.rejection_code == "unavailable"
    assert evaluation.model_attempt.validation_status is ModelOutputValidationStatus.NOT_EVALUATED


def test_provider_output_and_admission_mismatches_fail_closed() -> None:
    item = request()
    value = proposal()
    with pytest.raises(ModelAttemptError, match="output hash"):
        ProviderFreeAgentPlanningBoundary().evaluate(
            request=item,
            grounding_context=context(item),
            admission=admission(item),
            sequence_number=1,
            outcome=replace(completed_outcome(value), output_hash="f" * 64),
            proposed_plan=value,
        )
    with pytest.raises(ModelAttemptError, match="differs from the plan request"):
        ProviderFreeAgentPlanningBoundary().evaluate(
            request=item,
            grounding_context=context(item),
            admission=replace(admission(item), runtime_policy_bundle_hash="f" * 64),
            sequence_number=1,
            outcome=completed_outcome(value),
            proposed_plan=value,
        )


def test_model_call_and_token_caps_fail_closed() -> None:
    item = request()
    recorder = DeterministicModelAttemptRecorder()
    with pytest.raises(ModelAttemptError, match="sequence"):
        recorder.record(
            admission=admission(item),
            sequence_number=2,
            outcome=completed_outcome(),
            validation_status=ModelOutputValidationStatus.ACCEPTED,
        )
    with pytest.raises(ModelAttemptError, match="token usage"):
        recorder.record(
            admission=admission(item),
            sequence_number=1,
            outcome=replace(completed_outcome(), output_tokens=501),
            validation_status=ModelOutputValidationStatus.ACCEPTED,
        )
