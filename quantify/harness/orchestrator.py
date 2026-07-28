"""Offline orchestration from validated extraction to an audit-ready report."""

from __future__ import annotations

from dataclasses import dataclass

from quantify.engine import (
    ClaimAnalysisResult,
    ClaimVerdict,
    ComposedClaimVerdict,
    DisclosureAssessment,
    DisclosureStatus,
    EvidenceSnapshot,
    ReviewItem,
    analyze_claims,
    compose_claim_verdicts,
)

from .extraction import ExtractionResult, validate_extraction


@dataclass(frozen=True, slots=True)
class MaterialOmission:
    claim_id: str
    evidence_id: str


@dataclass(frozen=True, slots=True)
class VerificationReport:
    claim_analysis: ClaimAnalysisResult
    claim_verdicts: tuple[ComposedClaimVerdict, ...]
    review_items: tuple[ReviewItem, ...]
    unclassified_statement_ids: tuple[str, ...]
    non_factual_statement_ids: tuple[str, ...]
    material_omissions: tuple[MaterialOmission, ...]


def verify_report(
    *,
    report_text: str,
    snapshot: EvidenceSnapshot,
    extraction: ExtractionResult,
    disclosure_assessments: tuple[DisclosureAssessment, ...] = (),
) -> VerificationReport:
    """Run frozen inputs through validation, analysis, and final composition."""

    validated = validate_extraction(
        report_text=report_text, snapshot=snapshot, extraction=extraction
    )
    analysis = analyze_claims(snapshot=snapshot, claims=validated.claims)
    verdicts = compose_claim_verdicts(
        analysis=analysis, disclosure_assessments=disclosure_assessments
    )
    omissions = tuple(
        MaterialOmission(claim_id=verdict.claim_id, evidence_id=detail.evidence_id)
        for verdict in verdicts
        if verdict.verdict is ClaimVerdict.DEFEATED
        for detail in verdict.counterevidence_detail
        if detail.disclosure_status is DisclosureStatus.NOT_DISCLOSED
    )
    return VerificationReport(
        claim_analysis=analysis,
        claim_verdicts=verdicts,
        review_items=validated.review_items,
        unclassified_statement_ids=validated.unclassified_statement_ids,
        non_factual_statement_ids=validated.non_factual_statement_ids,
        material_omissions=omissions,
    )
