"""Auditable separation of local warrant and CE1 counterevidence."""

from __future__ import annotations

from .schemas import (
    ClaimAnalysisResult,
    CounterevidencePair,
    EvidenceSnapshot,
    LocalWarrantResult,
    MetricBaselineClaim,
    MetricComparisonClaim,
    MetricThresholdClaim,
    VerificationOutcome,
)
from .verifier import verify_claim


TypedClaim = MetricThresholdClaim | MetricComparisonClaim | MetricBaselineClaim


def analyze_claims(
    *, snapshot: EvidenceSnapshot, claims: tuple[TypedClaim, ...]
) -> ClaimAnalysisResult:
    """Run pure local-warrant and CE1 analysis for validated typed claims.

    Results are sorted by IDs, so they remain stable even when callers provide
    claims in a different order. A duplicate claim ID is rejected because it
    would make the audit trail ambiguous.
    """

    claim_ids = [claim.claim_id for claim in claims]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("claim IDs must be unique within one analysis")

    local_warrants: list[LocalWarrantResult] = []
    counterevidence_pairs: list[CounterevidencePair] = []
    for claim in sorted(claims, key=lambda item: item.claim_id):
        result = verify_claim(snapshot=snapshot, claim=claim)
        local_warrants.append(
            LocalWarrantResult(
                claim_id=claim.claim_id,
                passed=result.outcome is not VerificationOutcome.UNSUPPORTED,
                cited_evidence_ids=result.cited_evidence_ids,
            )
        )
        counterevidence_pairs.extend(
            CounterevidencePair(claim_id=claim.claim_id, evidence_id=evidence_id)
            for evidence_id in result.counterevidence_evidence_ids
        )

    return ClaimAnalysisResult(
        local_warrants=tuple(local_warrants),
        counterevidence_pairs=tuple(
            sorted(
                counterevidence_pairs,
                key=lambda pair: (pair.claim_id, pair.evidence_id),
            )
        ),
    )
