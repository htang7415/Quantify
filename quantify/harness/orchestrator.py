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
    TemporalPersistence,
    ReviewItem,
    ReviewReason,
    analyze_claims,
    annotate_temporal_persistence,
    compose_claim_verdicts,
)

from .extraction import ExtractionResult, validate_extraction
from .disclosure import DisclosureContext, DisclosureDetector


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
    temporal_persistence: tuple[TemporalPersistence, ...]
    canonical_claim_source_spans: tuple[tuple[str, tuple[str, ...]], ...]


def verify_report(
    *,
    report_text: str,
    snapshot: EvidenceSnapshot,
    extraction: ExtractionResult,
    disclosure_assessments: tuple[DisclosureAssessment, ...] = (),
    disclosure_detector: DisclosureDetector | None = None,
) -> VerificationReport:
    """Run frozen inputs through validation, analysis, and final composition."""

    validated = validate_extraction(
        report_text=report_text, snapshot=snapshot, extraction=extraction
    )
    analysis = analyze_claims(snapshot=snapshot, claims=validated.claims)
    if disclosure_detector is not None:
        if disclosure_assessments:
            raise ValueError("provide disclosure assessments or a detector, not both")
        claims_by_id = {claim.claim_id: claim for claim in validated.claims}
        contexts = tuple(
            DisclosureContext(
                claim=claims_by_id[pair.claim_id],
                defeating_evidence=snapshot.evidence_by_id(pair.evidence_id),
            )
            for pair in analysis.counterevidence_pairs
            if pair.claim_id in claims_by_id
            and snapshot.evidence_by_id(pair.evidence_id) is not None
        )
        if len(contexts) != len(analysis.counterevidence_pairs):
            raise AssertionError("counterevidence context could not be reconstructed")
        disclosure_assessments = disclosure_detector.assess(
            report_text=report_text,
            counterevidence_pairs=analysis.counterevidence_pairs,
            contexts=contexts,
        )
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
    assessment_by_pair = {
        (item.claim_id, item.defeating_evidence_id): item for item in disclosure_assessments
    }
    disclosure_reviews = []
    for pair in analysis.counterevidence_pairs:
        assessment = assessment_by_pair.get((pair.claim_id, pair.evidence_id))
        if assessment is None:
            disclosure_reviews.append(ReviewItem(
                statement_id=pair.claim_id, reason=ReviewReason.MISSING_DISCLOSURE_ASSESSMENT,
                message="No disclosure assessment was supplied for defeating evidence.",
                claim_id=pair.claim_id, evidence_ids=(pair.evidence_id,),
            ))
        elif assessment.status is DisclosureStatus.AMBIGUOUS:
            disclosure_reviews.append(ReviewItem(
                statement_id=pair.claim_id, reason=ReviewReason.DISCLOSURE_AMBIGUOUS,
                message="Disclosure assessment is ambiguous.", claim_id=pair.claim_id,
                evidence_ids=(pair.evidence_id,),
            ))
    return VerificationReport(
        claim_analysis=analysis,
        claim_verdicts=verdicts,
        review_items=tuple((*validated.review_items, *disclosure_reviews)),
        unclassified_statement_ids=validated.unclassified_statement_ids,
        non_factual_statement_ids=validated.non_factual_statement_ids,
        material_omissions=omissions,
        temporal_persistence=annotate_temporal_persistence(snapshot=snapshot),
        canonical_claim_source_spans=validated.canonical_claim_source_spans,
    )
