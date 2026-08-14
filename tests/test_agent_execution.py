from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import pytest

from quantify.agent_execution import (
    AgentArtifactRegistry,
    AgentExecutionError,
    AgentExecutionStatus,
    AgentExecutionUnavailableReason,
    AgentStageInvocation,
    ProviderFreeAgentExecutionRunner,
)
from quantify.agent_plans import (
    AgentPlanGroundingContext,
    AgentPlanPurpose,
    AgentPlanRequest,
    AgentPlanStage,
    DeterministicAgentPlanAdapter,
    question_hash,
)
from quantify.approved_tools import ApprovedReleaseTools
from quantify.calculations import (
    ApprovedCalculationInstruction,
    ApprovedCalculationRequest,
    CalculationOperation,
)
from quantify.evidence_search import (
    ApprovedEvidenceQuery,
    ApprovedEvidenceSearchRequest,
    ApprovedEvidenceSearchResult,
)
from quantify.narrative_context import ApprovedNarrativeContextRequest
from quantify.policy_control import (
    ArtifactKind,
    HmacPolicySigner,
    PolicyControlPlane,
    PolicyControlPointers,
    PolicyStatus,
    ReleaseGatePolicy,
    RuntimePolicyBundle,
)
from quantify.research_intents import AgentToolName, ResearchIntent
from quantify.research_tasks import ResearchTaskRequest
from quantify.review_tasks import (
    ApprovedReviewTaskRequest,
    ReviewOrigin,
    ReviewReason,
    ReviewTaskGroundingContext,
)
from tests.test_indexed_release import _compiled_msft_release


QUESTION = "Compare the released revenue periods and explain the filing context."
VERIFY_QUESTION = "Microsoft fiscal 2024 revenue was 245122000000 USD."
PROMPT_HASH = "d" * 64
TOOL_HASH = "e" * 64


@dataclass
class Environment:
    release: object
    policy: PolicyControlPlane
    pointers: PolicyControlPointers
    tools: ApprovedReleaseTools


def environment() -> Environment:
    release, _, _ = _compiled_msft_release()
    signer = HmacPolicySigner(key_id="runner-key", key=b"k" * 32)
    policy = PolicyControlPlane(signer=signer)
    runtime = RuntimePolicyBundle(
        "1.0.0",
        "runner-v1",
        "synthetic",
        "pinned-planner",
        "v1",
        "secret-v1",
        PROMPT_HASH,
        1,
        2_000,
        1_000,
        (
            "verify_claims",
            "search_approved_evidence_release",
            "calculate_approved_evidence",
            "create_review_task",
            "narrative_context",
        ),
        (),
        ("structured_fact", "narrative_disclosure"),
        (
            "arbitrary_url_fetch",
            "live_sec_retrieval",
            "private_document_access",
            "policy_mutation",
            "verdict_composition",
            "trade_execution",
        ),
        "admission-v1",
        "cache-v1",
    )
    gate = ReleaseGatePolicy(
        "1.0.0", "runner-gate-v1", 9900, 100, 25, 30, True, True
    )
    policy.publish(signer.sign(kind=ArtifactKind.RUNTIME_POLICY, artifact=runtime))
    policy.publish(signer.sign(kind=ArtifactKind.RELEASE_GATE_POLICY, artifact=gate))
    policy.register_evidence_release(
        manifest_hash=release.evidence_release.manifest_hash
    )
    pointers = PolicyControlPointers(
        release.evidence_release.manifest_hash,
        runtime.content_hash,
        gate.content_hash,
    )
    policy.set_pointers(pointers)
    return Environment(
        release=release,
        policy=policy,
        pointers=pointers,
        tools=ApprovedReleaseTools(
            release=release,
            policy=policy,
            pointers=pointers,
        ),
    )


def plan_request(
    env: Environment,
    *,
    intent: ResearchIntent = ResearchIntent.ANALYZE,
    question: str = QUESTION,
    allowed_tools: tuple[AgentToolName, ...] = (
        AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
        AgentToolName.CALCULATE_APPROVED_EVIDENCE,
        AgentToolName.NARRATIVE_CONTEXT,
        AgentToolName.CREATE_REVIEW_TASK,
    ),
    maximum_actions: int = 4,
) -> AgentPlanRequest:
    return AgentPlanRequest(
        task_id="task-execution-001",
        task_intent=intent,
        question_hash=question_hash(question),
        cik="0000789019",
        as_of=date(2024, 7, 30),
        release_id=env.release.evidence_release.release_id,
        release_manifest_hash=env.release.evidence_release.manifest_hash,
        runtime_policy_bundle_hash=env.pointers.runtime_policy_bundle_hash,
        release_gate_policy_hash=env.pointers.release_gate_policy_hash,
        allowed_tools=allowed_tools,
        maximum_actions=maximum_actions,
        maximum_model_calls=1,
        prompt_contract_hash=PROMPT_HASH,
        tool_contract_hash=TOOL_HASH,
    )


def grounding(
    request: AgentPlanRequest, *, question: str = QUESTION
) -> AgentPlanGroundingContext:
    return AgentPlanGroundingContext(
        task_id=request.task_id,
        task_intent=request.task_intent,
        authorized_question=question,
        cik=request.cik,
        as_of=request.as_of,
        release_id=request.release_id,
        release_manifest_hash=request.release_manifest_hash,
        runtime_policy_bundle_hash=request.runtime_policy_bundle_hash,
        release_gate_policy_hash=request.release_gate_policy_hash,
        authorized_tools=request.allowed_tools,
        maximum_actions=request.maximum_actions,
        maximum_model_calls=request.maximum_model_calls,
        prompt_contract_hash=request.prompt_contract_hash,
        tool_contract_hash=request.tool_contract_hash,
    )


def validated_plan(request: AgentPlanRequest, stages: list[dict[str, object]]):
    return DeterministicAgentPlanAdapter().validate(
        request=request,
        grounding_context=grounding(
            request,
            question=(VERIFY_QUESTION if request.task_intent is ResearchIntent.VERIFY else QUESTION),
        ),
        proposed_plan={
            "status": "planned",
            "stages": stages,
            "unavailable_reason": None,
        },
    )


def search_stage() -> dict[str, object]:
    return {
        "stage_id": "search",
        "tool_name": "search_approved_evidence_release",
        "purpose": "retrieve_facts",
        "depends_on_stage_ids": [],
    }


def calculation_stage() -> dict[str, object]:
    return {
        "stage_id": "calculate",
        "tool_name": "calculate_approved_evidence",
        "purpose": "calculate",
        "depends_on_stage_ids": ["search"],
    }


def narrative_stage() -> dict[str, object]:
    return {
        "stage_id": "context",
        "tool_name": "narrative_context",
        "purpose": "retrieve_context",
        "depends_on_stage_ids": [],
    }


def exact_search_request(env: Environment, *, metric: str | None = None):
    records = tuple(
        next(
            record
            for record in env.release.exact_facts.records
            if record.evidence.entity_cik == "0000789019"
            and record.evidence.metric == "revenue"
            and record.evidence.period_end == period_end
        )
        for period_end in (date(2024, 6, 30), date(2023, 6, 30))
    )
    return ApprovedEvidenceSearchRequest(
        task_type=ResearchIntent.ANALYZE,
        cik="0000789019",
        as_of=date(2024, 7, 30),
        release_id=env.release.evidence_release.release_id,
        release_manifest_hash=env.release.evidence_release.manifest_hash,
        queries=tuple(
            ApprovedEvidenceQuery(
                query_id=f"revenue-{index}",
                metric=metric or record.key.metric,
                period_start=record.key.fiscal_period_start,
                period_end=record.key.fiscal_period_end,
                unit=record.key.unit,
            )
            for index, record in enumerate(records)
        ),
    )


def calculation_request(search: ApprovedEvidenceSearchResult):
    facts = tuple(sorted(search.facts, key=lambda fact: fact.period_end, reverse=True))
    return ApprovedCalculationRequest(
        evidence_search_result_hash=search.result_hash,
        release_manifest_hash=search.request.release_manifest_hash,
        calculations=(
            ApprovedCalculationInstruction(
                result_statement_id="calc-revenue-change",
                operation=CalculationOperation.PERCENT_CHANGE,
                input_statement_ids=tuple(fact.statement_id for fact in facts),
                decimal_places=2,
            ),
        ),
    )


def narrative_request(env: Environment):
    return ApprovedNarrativeContextRequest(
        task_type=ResearchIntent.ANALYZE,
        cik="0000789019",
        as_of=date(2024, 7, 30),
        release_id=env.release.evidence_release.release_id,
        release_manifest_hash=env.release.evidence_release.manifest_hash,
    )


def runner(env: Environment, *, verifier=None) -> ProviderFreeAgentExecutionRunner:
    return ProviderFreeAgentExecutionRunner(
        tools=env.tools,
        policy_control=env.policy,
        policy_pointers=env.pointers,
        verification_executor=verifier,
    )


def test_runner_executes_typed_stages_and_registers_only_metadata() -> None:
    env = environment()
    request = plan_request(env, maximum_actions=3)
    plan = validated_plan(request, [search_stage(), calculation_stage(), narrative_stage()])

    def provide(stage, artifacts):
        if stage.stage_id == "search":
            return AgentStageInvocation(stage.stage_id, exact_search_request(env))
        if stage.stage_id == "calculate":
            search = artifacts.typed_result(
                stage_id="search",
                tool_name=AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
            )
            assert isinstance(search, ApprovedEvidenceSearchResult)
            return AgentStageInvocation(stage.stage_id, calculation_request(search))
        return AgentStageInvocation(stage.stage_id, narrative_request(env))

    first = runner(env).execute(
        plan_request=request,
        grounding_context=grounding(request),
        plan=plan,
        stage_request_provider=provide,
    )
    second = runner(env).execute(
        plan_request=request,
        grounding_context=grounding(request),
        plan=plan,
        stage_request_provider=provide,
    )

    assert first == second
    assert first.status is AgentExecutionStatus.COMPLETED
    assert [artifact.status for artifact in first.artifacts] == [
        "completed",
        "completed",
        "unavailable",
    ]
    assert first.artifacts[1].dependency_result_hashes == (
        first.artifacts[0].result_hash,
    )
    document = first.to_document()
    assert "245122000000" not in str(document)
    assert all("facts" not in artifact for artifact in document["artifacts"])
    assert all("contexts" not in artifact for artifact in document["artifacts"])


def test_all_unavailable_data_is_a_complete_unavailable_state() -> None:
    env = environment()
    request = plan_request(
        env,
        allowed_tools=(AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,),
        maximum_actions=1,
    )
    plan = validated_plan(request, [search_stage()])

    result = runner(env).execute(
        plan_request=request,
        grounding_context=grounding(request),
        plan=plan,
        stage_request_provider=lambda stage, artifacts: AgentStageInvocation(
            stage.stage_id, exact_search_request(env, metric="not_released")
        ),
    )

    assert result.status is AgentExecutionStatus.UNAVAILABLE
    assert result.unavailable_reason is AgentExecutionUnavailableReason.REQUIRED_DATA_UNAVAILABLE
    assert result.artifacts[0].status == "unavailable"


def test_cross_task_calculation_result_hash_is_rejected() -> None:
    env = environment()
    request = plan_request(
        env,
        allowed_tools=(
            AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
            AgentToolName.CALCULATE_APPROVED_EVIDENCE,
        ),
        maximum_actions=2,
    )
    plan = validated_plan(request, [search_stage(), calculation_stage()])

    def provide(stage, artifacts):
        if stage.stage_id == "search":
            return AgentStageInvocation(stage.stage_id, exact_search_request(env))
        search = artifacts.typed_result(
            stage_id="search",
            tool_name=AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
        )
        assert isinstance(search, ApprovedEvidenceSearchResult)
        return AgentStageInvocation(
            stage.stage_id,
            replace(calculation_request(search), evidence_search_result_hash="f" * 64),
        )

    with pytest.raises(AgentExecutionError) as captured:
        runner(env).execute(
            plan_request=request,
            grounding_context=grounding(request),
            plan=plan,
            stage_request_provider=provide,
        )
    assert captured.value.code == "dependency_mismatch"


def test_stage_and_request_type_mismatches_are_rejected() -> None:
    env = environment()
    request = plan_request(
        env,
        allowed_tools=(AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,),
        maximum_actions=1,
    )
    plan = validated_plan(request, [search_stage()])
    with pytest.raises(AgentExecutionError) as captured:
        runner(env).execute(
            plan_request=request,
            grounding_context=grounding(request),
            plan=plan,
            stage_request_provider=lambda stage, artifacts: AgentStageInvocation(
                "other-stage", exact_search_request(env)
            ),
        )
    assert captured.value.code == "stage_mismatch"


def test_registry_rejects_ambiguous_cross_artifact_identifiers() -> None:
    registry = AgentArtifactRegistry(task_id="task-001", plan_id="plan-001")
    search = AgentPlanStage(
        stage_id="search",
        tool_name=AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
        purpose=AgentPlanPurpose.RETRIEVE_FACTS,
        depends_on_stage_ids=(),
    )
    context = AgentPlanStage(
        stage_id="context",
        tool_name=AgentToolName.NARRATIVE_CONTEXT,
        purpose=AgentPlanPurpose.RETRIEVE_CONTEXT,
        depends_on_stage_ids=(),
    )
    registry.register(
        stage=search,
        request_hash="a" * 64,
        result_hash="b" * 64,
        dependency_result_hashes=(),
        status="completed",
        result={},
        statement_ids=("same-statement",),
    )

    with pytest.raises(AgentExecutionError) as captured:
        registry.register(
            stage=context,
            request_hash="c" * 64,
            result_hash="d" * 64,
            dependency_result_hashes=(),
            status="completed",
            result={},
            statement_ids=("same-statement",),
        )
    assert captured.value.code == "duplicate_reference"


def test_policy_revocation_between_stages_stops_before_second_action() -> None:
    env = environment()
    request = plan_request(
        env,
        allowed_tools=(
            AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
            AgentToolName.CALCULATE_APPROVED_EVIDENCE,
        ),
        maximum_actions=2,
    )
    plan = validated_plan(request, [search_stage(), calculation_stage()])

    def provide(stage, artifacts):
        if stage.stage_id == "search":
            return AgentStageInvocation(stage.stage_id, exact_search_request(env))
        search = artifacts.typed_result(
            stage_id="search",
            tool_name=AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
        )
        assert isinstance(search, ApprovedEvidenceSearchResult)
        env.policy.set_status(
            kind=ArtifactKind.RUNTIME_POLICY,
            artifact_hash=env.pointers.runtime_policy_bundle_hash,
            status=PolicyStatus.REVOKED,
        )
        return AgentStageInvocation(stage.stage_id, calculation_request(search))

    result = runner(env).execute(
        plan_request=request,
        grounding_context=grounding(request),
        plan=plan,
        stage_request_provider=provide,
    )

    assert result.status is AgentExecutionStatus.UNAVAILABLE
    assert result.unavailable_reason is AgentExecutionUnavailableReason.POLICY_UNAVAILABLE
    assert len(result.artifacts) == 1


def test_review_can_reference_only_task_local_artifacts_and_is_terminal() -> None:
    env = environment()
    request = plan_request(
        env,
        allowed_tools=(
            AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
            AgentToolName.CREATE_REVIEW_TASK,
        ),
        maximum_actions=2,
    )
    review_stage = {
        "stage_id": "review",
        "tool_name": "create_review_task",
        "purpose": "route_review",
        "depends_on_stage_ids": ["search"],
    }
    plan = validated_plan(request, [search_stage(), review_stage])

    def provide(stage, artifacts):
        if stage.stage_id == "search":
            return AgentStageInvocation(stage.stage_id, exact_search_request(env))
        search_artifact = artifacts.artifact(stage_id="search")
        question = "Which evidence qualification requires human review?"
        review_request = ApprovedReviewTaskRequest(
            task_type=ResearchIntent.ANALYZE,
            review_origin=ReviewOrigin.BOUNDED_AGENT,
            reason=ReviewReason.AMBIGUOUS_EVIDENCE,
            question=question,
            release_id=request.release_id,
            release_manifest_hash=request.release_manifest_hash,
            runtime_policy_bundle_hash=request.runtime_policy_bundle_hash,
            release_gate_policy_hash=request.release_gate_policy_hash,
            source_result_hashes=(search_artifact.result_hash,),
            audit_manifest_hash="a" * 64,
            derived_from_statement_ids=(search_artifact.statement_ids[0],),
            derived_from_citation_ids=(search_artifact.citation_ids[0],),
        )
        review_context = ReviewTaskGroundingContext(
            task_type=review_request.task_type,
            review_origin=review_request.review_origin,
            authorized_question=question,
            release_id=review_request.release_id,
            release_manifest_hash=review_request.release_manifest_hash,
            runtime_policy_bundle_hash=review_request.runtime_policy_bundle_hash,
            release_gate_policy_hash=review_request.release_gate_policy_hash,
            audit_manifest_hash=review_request.audit_manifest_hash,
            authorized_source_result_hashes=(search_artifact.result_hash,),
            authorized_statement_ids=search_artifact.statement_ids,
            authorized_citation_ids=search_artifact.citation_ids,
        )
        return AgentStageInvocation(
            stage.stage_id,
            review_request,
            review_grounding_context=review_context,
        )

    result = runner(env).execute(
        plan_request=request,
        grounding_context=grounding(request),
        plan=plan,
        stage_request_provider=provide,
    )

    assert result.status is AgentExecutionStatus.REQUIRES_REVIEW
    assert result.unavailable_reason is None
    assert result.artifacts[-1].status == "requires_review"


def test_review_rejects_a_foreign_result_even_if_context_repeats_it() -> None:
    env = environment()
    request = plan_request(
        env,
        allowed_tools=(
            AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
            AgentToolName.CREATE_REVIEW_TASK,
        ),
        maximum_actions=2,
    )
    plan = validated_plan(
        request,
        [
            search_stage(),
            {
                "stage_id": "review",
                "tool_name": "create_review_task",
                "purpose": "route_review",
                "depends_on_stage_ids": ["search"],
            },
        ],
    )

    def provide(stage, artifacts):
        if stage.stage_id == "search":
            return AgentStageInvocation(stage.stage_id, exact_search_request(env))
        artifact = artifacts.artifact(stage_id="search")
        foreign_hash = "f" * 64
        question = "Which evidence qualification requires human review?"
        review_request = ApprovedReviewTaskRequest(
            task_type=ResearchIntent.ANALYZE,
            review_origin=ReviewOrigin.BOUNDED_AGENT,
            reason=ReviewReason.AMBIGUOUS_EVIDENCE,
            question=question,
            release_id=request.release_id,
            release_manifest_hash=request.release_manifest_hash,
            runtime_policy_bundle_hash=request.runtime_policy_bundle_hash,
            release_gate_policy_hash=request.release_gate_policy_hash,
            source_result_hashes=(foreign_hash,),
            audit_manifest_hash="a" * 64,
            derived_from_statement_ids=(artifact.statement_ids[0],),
        )
        review_context = ReviewTaskGroundingContext(
            task_type=review_request.task_type,
            review_origin=review_request.review_origin,
            authorized_question=question,
            release_id=review_request.release_id,
            release_manifest_hash=review_request.release_manifest_hash,
            runtime_policy_bundle_hash=review_request.runtime_policy_bundle_hash,
            release_gate_policy_hash=review_request.release_gate_policy_hash,
            audit_manifest_hash=review_request.audit_manifest_hash,
            authorized_source_result_hashes=(foreign_hash,),
            authorized_statement_ids=artifact.statement_ids,
        )
        return AgentStageInvocation(
            stage.stage_id,
            review_request,
            review_grounding_context=review_context,
        )

    with pytest.raises(AgentExecutionError) as captured:
        runner(env).execute(
            plan_request=request,
            grounding_context=grounding(request),
            plan=plan,
            stage_request_provider=provide,
        )
    assert captured.value.code == "cross_task_reference"


class FakeVerifier:
    def __init__(self, env: Environment, *, wrong_policy: bool = False) -> None:
        self.env = env
        self.wrong_policy = wrong_policy
        self.calls = 0

    def verify(self, *, cik: str, request: object):
        self.calls += 1
        return {
            "evidence_scope": {
                "source": "SEC EDGAR",
                "entity_level_only": True,
                "forms": ["10-K", "10-Q"],
                "snapshot_manifest_hash": self.env.pointers.evidence_release_manifest_hash,
            },
            "audit_manifest": {
                "manifest_hash": "9" * 64,
                "evidence_release_manifest_hash": self.env.pointers.evidence_release_manifest_hash,
                "runtime_policy_bundle_hash": (
                    "f" * 64
                    if self.wrong_policy
                    else self.env.pointers.runtime_policy_bundle_hash
                ),
                "release_gate_policy_hash": self.env.pointers.release_gate_policy_hash,
            },
            "claim_results": [{"claim_id": "claim-001", "verdict": "verified"}],
            "review_items": [],
        }


def verification_setup(env: Environment):
    request = plan_request(
        env,
        intent=ResearchIntent.VERIFY,
        question=VERIFY_QUESTION,
        allowed_tools=(AgentToolName.VERIFY_CLAIMS,),
        maximum_actions=1,
    )
    plan = validated_plan(
        request,
        [
            {
                "stage_id": "verify",
                "tool_name": "verify_claims",
                "purpose": "verify_claim",
                "depends_on_stage_ids": [],
            }
        ],
    )
    verification_request = ResearchTaskRequest(
        cik=request.cik,
        analysis=VERIFY_QUESTION,
        as_of_date=request.as_of,
    )
    return request, plan, verification_request


def test_explicit_verification_uses_only_injected_deterministic_verifier() -> None:
    env = environment()
    request, plan, verification_request = verification_setup(env)
    verifier = FakeVerifier(env)

    result = runner(env, verifier=verifier).execute(
        plan_request=request,
        grounding_context=grounding(request, question=VERIFY_QUESTION),
        plan=plan,
        stage_request_provider=lambda stage, artifacts: AgentStageInvocation(
            stage.stage_id, verification_request
        ),
    )

    assert verifier.calls == 1
    assert result.status is AgentExecutionStatus.COMPLETED
    assert result.artifacts[0].claim_ids == ("claim-001",)
    assert result.artifacts[0].statement_ids == ()


def test_missing_or_cross_policy_verifier_fails_closed() -> None:
    env = environment()
    request, plan, verification_request = verification_setup(env)
    missing = runner(env).execute(
        plan_request=request,
        grounding_context=grounding(request, question=VERIFY_QUESTION),
        plan=plan,
        stage_request_provider=lambda stage, artifacts: AgentStageInvocation(
            stage.stage_id, verification_request
        ),
    )
    assert missing.status is AgentExecutionStatus.UNAVAILABLE
    assert missing.unavailable_reason is AgentExecutionUnavailableReason.VERIFIER_UNAVAILABLE

    with pytest.raises(AgentExecutionError) as captured:
        runner(env, verifier=FakeVerifier(env, wrong_policy=True)).execute(
            plan_request=request,
            grounding_context=grounding(request, question=VERIFY_QUESTION),
            plan=plan,
            stage_request_provider=lambda stage, artifacts: AgentStageInvocation(
                stage.stage_id, verification_request
            ),
        )
    assert captured.value.code == "verification_scope_mismatch"
