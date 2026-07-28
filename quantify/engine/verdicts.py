"""Pure final verdict composition after harness disclosure assessment."""

from __future__ import annotations

from collections import defaultdict

from .schemas import (
    ClaimAnalysisResult,
    ClaimVerdict,
    ComposedClaimVerdict,
    CounterevidenceDetail,
    DisclosureAssessment,
    DisclosureStatus,
)


def compose_claim_verdicts(
    *,
    analysis: ClaimAnalysisResult,
    disclosure_assessments: tuple[DisclosureAssessment, ...],
) -> tuple[ComposedClaimVerdict, ...]:
    """Compose final verdicts using the conservative V1 decision table.

    Missing or ambiguous disclosure assessment fails closed to human review.
    An assessment for a pair that CE1 did not produce is invalid input because
    it would break auditability.
    """

    warrants = {item.claim_id: item for item in analysis.local_warrants}
    if len(warrants) != len(analysis.local_warrants):
        raise ValueError("local warrant results must have unique claim IDs")

    expected_pairs = {
        (item.claim_id, item.evidence_id) for item in analysis.counterevidence_pairs
    }
    assessment_by_pair = {
        (item.claim_id, item.defeating_evidence_id): item
        for item in disclosure_assessments
    }
    if len(assessment_by_pair) != len(disclosure_assessments):
        raise ValueError("disclosure assessments must be unique per claim/evidence pair")
    unexpected_pairs = set(assessment_by_pair).difference(expected_pairs)
    if unexpected_pairs:
        raise ValueError("disclosure assessment supplied for a non-CE1 pair")

    pairs_by_claim: dict[str, list[str]] = defaultdict(list)
    for claim_id, evidence_id in expected_pairs:
        pairs_by_claim[claim_id].append(evidence_id)

    composed: list[ComposedClaimVerdict] = []
    for claim_id in sorted(warrants):
        warrant = warrants[claim_id]
        if not warrant.passed:
            composed.append(
                ComposedClaimVerdict(
                    claim_id=claim_id, verdict=ClaimVerdict.UNSUPPORTED
                )
            )
            continue

        defeating_ids = sorted(pairs_by_claim[claim_id])
        if not defeating_ids:
            composed.append(
                ComposedClaimVerdict(claim_id=claim_id, verdict=ClaimVerdict.VERIFIED)
            )
            continue

        assessments = [assessment_by_pair.get((claim_id, evidence_id)) for evidence_id in defeating_ids]
        details = tuple(
            CounterevidenceDetail(
                evidence_id=evidence_id,
                disclosure_status=assessment.status,
                report_span_ids=assessment.supporting_report_span_ids,
            )
            for evidence_id, assessment in zip(defeating_ids, assessments, strict=True)
            if assessment is not None
        )
        if (
            any(assessment is None for assessment in assessments)
            or any(
                assessment.status is DisclosureStatus.AMBIGUOUS
                for assessment in assessments
                if assessment is not None
            )
        ):
            verdict = ClaimVerdict.REQUIRES_HUMAN_REVIEW
        elif all(
            assessment.status is DisclosureStatus.NOT_DISCLOSED
            for assessment in assessments
            if assessment is not None
        ):
            verdict = ClaimVerdict.DEFEATED
        else:
            verdict = ClaimVerdict.QUALIFIED
        composed.append(
            ComposedClaimVerdict(
                claim_id=claim_id, verdict=verdict, counterevidence_detail=details
            )
        )

    return tuple(composed)
