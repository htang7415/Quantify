from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from quantify.approved_tools import ApprovedReleaseTools, ToolUnavailableError
from quantify.calculations import (
    ApprovedCalculationInstruction,
    ApprovedCalculationRequest,
    CalculationOperation,
)
from quantify.evidence_search import (
    ApprovedEvidenceQuery,
    ApprovedEvidenceSearchRequest,
    EvidenceSearchStatus,
    EvidenceSearchTask,
)
from quantify.narrative_context import (
    ApprovedNarrativeContextRequest,
    NarrativeContextStatus,
    NarrativeContextTask,
)
from quantify.policy_control import (
    ArtifactKind,
    HmacPolicySigner,
    PolicyControlPlane,
    PolicyControlPointers,
    ReleaseGatePolicy,
    RuntimePolicyBundle,
)
from quantify.review_tasks import (
    ApprovedReviewTaskRequest,
    ReviewOrigin,
    ReviewReason,
    ReviewTaskError,
    ReviewTaskGroundingContext,
    ReviewTaskType,
)
from tests.test_indexed_release import _compiled_msft_release


def tools() -> tuple[ApprovedReleaseTools, object, PolicyControlPointers]:
    release, _, _ = _compiled_msft_release()
    signer = HmacPolicySigner(key_id="tools-key", key=b"k" * 32)
    policy = PolicyControlPlane(signer=signer)
    runtime = RuntimePolicyBundle(
        "1.0.0",
        "tools-v1",
        "google",
        "gemini-3.1-flash-lite",
        "2026-07",
        "secret-v1",
        "a" * 64,
        1,
        1,
        1,
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
        "1.0.0", "gate-v1", 9900, 100, 25, 30, True, True
    )
    policy.publish(signer.sign(kind=ArtifactKind.RUNTIME_POLICY, artifact=runtime))
    policy.publish(signer.sign(kind=ArtifactKind.RELEASE_GATE_POLICY, artifact=gate))
    policy.register_evidence_release(manifest_hash=release.evidence_release.manifest_hash)
    pointers = PolicyControlPointers(
        release.evidence_release.manifest_hash,
        runtime.content_hash,
        gate.content_hash,
    )
    policy.set_pointers(pointers)
    return (
        ApprovedReleaseTools(release=release, policy=policy, pointers=pointers),
        release,
        pointers,
    )


def request_for(record, release, *, metric: str | None = None):
    return ApprovedEvidenceSearchRequest(
        task_type=EvidenceSearchTask.VERIFY,
        cik=record.key.cik,
        as_of=date(2024, 7, 30),
        release_id=release.evidence_release.release_id,
        release_manifest_hash=release.evidence_release.manifest_hash,
        queries=(
            ApprovedEvidenceQuery(
                query_id="exact-fact",
                metric=metric or record.key.metric,
                period_start=record.key.fiscal_period_start,
                period_end=record.key.fiscal_period_end,
                unit=record.key.unit,
            ),
        ),
    )


def context_request_for(release, *, manifest_hash: str | None = None):
    return ApprovedNarrativeContextRequest(
        task_type=NarrativeContextTask.ANALYZE,
        cik="0000789019",
        as_of=date(2024, 7, 30),
        release_id=release.evidence_release.release_id,
        release_manifest_hash=manifest_hash or release.evidence_release.manifest_hash,
    )


def review_request_for(search_result, release, pointers):
    fact = search_result.facts[0]
    question = "Which evidence qualification requires human review?"
    request = ApprovedReviewTaskRequest(
        task_type=ReviewTaskType.VERIFY,
        review_origin=ReviewOrigin.DETERMINISTIC_VALIDATOR,
        reason=ReviewReason.AMBIGUOUS_EVIDENCE,
        question=question,
        release_id=release.evidence_release.release_id,
        release_manifest_hash=release.evidence_release.manifest_hash,
        runtime_policy_bundle_hash=pointers.runtime_policy_bundle_hash,
        release_gate_policy_hash=pointers.release_gate_policy_hash,
        source_result_hashes=(search_result.result_hash,),
        audit_manifest_hash="f" * 64,
        derived_from_statement_ids=(fact.statement_id,),
        derived_from_citation_ids=(fact.citation_id,),
    )
    context = ReviewTaskGroundingContext(
        task_type=request.task_type,
        review_origin=request.review_origin,
        authorized_question=question,
        release_id=request.release_id,
        release_manifest_hash=request.release_manifest_hash,
        runtime_policy_bundle_hash=request.runtime_policy_bundle_hash,
        release_gate_policy_hash=request.release_gate_policy_hash,
        audit_manifest_hash=request.audit_manifest_hash,
        authorized_source_result_hashes=(search_result.result_hash,),
        authorized_statement_ids=(fact.statement_id,),
        authorized_citation_ids=(fact.citation_id,),
    )
    return request, context


def test_exact_search_review_and_context_only_tools() -> None:
    approved_tools, release, pointers = tools()
    record = next(
        item for item in release.exact_facts.records if item.evidence.metric == "revenue"
    )

    result = approved_tools.search_approved_evidence_release(
        request=request_for(record, release)
    )

    assert result.status is EvidenceSearchStatus.COMPLETED
    assert result.facts[0].evidence_id == record.evidence.evidence_id
    assert result.to_document()["facts"][0]["citation"]["evidence_id"] == record.evidence.evidence_id
    review_request, review_context = review_request_for(result, release, pointers)
    review = approved_tools.create_review_task(
        request=review_request,
        grounding_context=review_context,
    )
    assert review.to_document()["status"] == "requires_review"
    assert review.to_document()["release"]["manifest_hash"] == (
        release.evidence_release.manifest_hash
    )
    context_result = approved_tools.narrative_context(
        request=context_request_for(release)
    )
    assert context_result.status is NarrativeContextStatus.UNAVAILABLE
    assert context_result.contexts == ()
    assert context_result.unavailable[0].reason == "narrative_context_not_released"


def test_tools_fail_closed_when_disabled_or_unavailable() -> None:
    approved_tools, release, pointers = tools()
    record = release.exact_facts.records[0]
    result = approved_tools.search_approved_evidence_release(
        request=request_for(record, release, metric="nope")
    )

    assert result.status is EvidenceSearchStatus.UNAVAILABLE
    assert result.facts == ()
    assert result.unavailable[0].reason == "exact_fact_not_found"
    valid_result = approved_tools.search_approved_evidence_release(
        request=request_for(record, release)
    )
    review_request, review_context = review_request_for(
        valid_result, release, pointers
    )
    with pytest.raises(ReviewTaskError, match="citation reference"):
        approved_tools.create_review_task(
            request=review_request,
            grounding_context=replace(
                review_context,
                authorized_citation_ids=("other-citation",),
            ),
        )


def test_approved_tool_rejects_a_request_outside_active_policy_pointer() -> None:
    approved_tools, release, pointers = tools()
    record = release.exact_facts.records[0]
    request = ApprovedEvidenceSearchRequest(
        task_type=EvidenceSearchTask.EXPLORE,
        cik=record.key.cik,
        as_of=date(2024, 7, 30),
        release_id=release.evidence_release.release_id,
        release_manifest_hash="f" * 64,
        queries=(
            ApprovedEvidenceQuery(
                query_id="outside",
                metric=record.key.metric,
                period_start=record.key.fiscal_period_start,
                period_end=record.key.fiscal_period_end,
                unit=record.key.unit,
            ),
        ),
    )

    with pytest.raises(ToolUnavailableError, match="active evidence release"):
        approved_tools.search_approved_evidence_release(request=request)

    with pytest.raises(ToolUnavailableError, match="active evidence release"):
        approved_tools.narrative_context(
            request=context_request_for(release, manifest_hash="f" * 64)
        )

    valid_search = approved_tools.search_approved_evidence_release(
        request=request_for(record, release)
    )
    review_request, review_context = review_request_for(
        valid_search, release, pointers
    )
    with pytest.raises(ToolUnavailableError, match="active policy scope"):
        approved_tools.create_review_task(
            request=replace(
                review_request,
                runtime_policy_bundle_hash="0" * 64,
            ),
            grounding_context=review_context,
        )
    with pytest.raises(ToolUnavailableError, match="active policy scope"):
        approved_tools.create_review_task(
            request=replace(review_request, release_id="other-release"),
            grounding_context=review_context,
        )


def test_approved_calculation_tool_uses_only_its_policy_admitted_search_result() -> None:
    approved_tools, release, _ = tools()
    revenue = sorted(
        (
            record
            for record in release.exact_facts.records
            if record.evidence.entity_cik == "0000789019"
            and record.evidence.metric == "revenue"
            and record.evidence.period_end in {date(2023, 6, 30), date(2024, 6, 30)}
        ),
        key=lambda record: record.evidence.period_end,
        reverse=True,
    )
    search_request = ApprovedEvidenceSearchRequest(
        task_type=EvidenceSearchTask.ANALYZE,
        cik="0000789019",
        as_of=date(2024, 7, 30),
        release_id=release.evidence_release.release_id,
        release_manifest_hash=release.evidence_release.manifest_hash,
        queries=tuple(
            ApprovedEvidenceQuery(
                query_id=f"revenue-{index}",
                metric=record.key.metric,
                period_start=record.key.fiscal_period_start,
                period_end=record.key.fiscal_period_end,
                unit=record.key.unit,
            )
            for index, record in enumerate(revenue)
        ),
    )
    search_result = approved_tools.search_approved_evidence_release(
        request=search_request
    )
    facts = sorted(
        search_result.facts, key=lambda fact: fact.period_end, reverse=True
    )
    calculation_request = ApprovedCalculationRequest(
        evidence_search_result_hash=search_result.result_hash,
        release_manifest_hash=release.evidence_release.manifest_hash,
        calculations=(
            ApprovedCalculationInstruction(
                result_statement_id="calc-revenue-change",
                operation=CalculationOperation.PERCENT_CHANGE,
                input_statement_ids=tuple(fact.statement_id for fact in facts),
                decimal_places=2,
            ),
        ),
    )

    result = approved_tools.calculate_approved_evidence(
        request=calculation_request,
        evidence_search_result=search_result,
    )

    assert result.calculations[0].statement_text == (
        "Calculated percent change: 15.67%."
    )
