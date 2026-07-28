"""Pure local-warrant and counterevidence verification."""

from __future__ import annotations

from .schemas import (
    EvidenceSnapshot,
    EvidenceValue,
    MetricThresholdClaim,
    Relation,
    VerificationOutcome,
    VerificationResult,
)


def _satisfies(*, value: object, relation: Relation, threshold: object) -> bool:
    if relation is Relation.GREATER_THAN:
        return value > threshold
    if relation is Relation.LESS_THAN:
        return value < threshold
    raise ValueError(f"unsupported relation: {relation}")


def _defeats(*, evidence: EvidenceValue, claim: MetricThresholdClaim) -> bool:
    return not _satisfies(
        value=evidence.value,
        relation=claim.relation,
        threshold=claim.threshold,
    )


def verify_claim(
    *, snapshot: EvidenceSnapshot, claim: MetricThresholdClaim
) -> VerificationResult:
    """Return a deterministic pre-disclosure verification outcome.

    A claim is unsupported when its cited fact is absent, ineligible, or does
    not satisfy the typed relation. A locally warranted claim receives a
    counterevidence outcome only when another eligible fact has identical
    semantic identity and directly fails that same relation.

    Disclosure assessment is intentionally outside this pure function; a later
    layer can compose a final ``DEFEATED`` or ``QUALIFIED`` verdict.
    """

    cited = snapshot.evidence_by_id(claim.cited_evidence_id)
    if cited is None or not cited.eligible:
        return VerificationResult(
            claim_id=claim.claim_id,
            outcome=VerificationOutcome.UNSUPPORTED,
            cited_evidence_id=claim.cited_evidence_id,
        )

    if not _satisfies(
        value=cited.value, relation=claim.relation, threshold=claim.threshold
    ):
        return VerificationResult(
            claim_id=claim.claim_id,
            outcome=VerificationOutcome.UNSUPPORTED,
            cited_evidence_id=claim.cited_evidence_id,
        )

    counterevidence_ids = tuple(
        item.evidence_id
        for item in snapshot.evidence
        if (
            item.evidence_id != cited.evidence_id
            and item.eligible
            and item.semantic_key == cited.semantic_key
            and _defeats(evidence=item, claim=claim)
        )
    )
    if counterevidence_ids:
        return VerificationResult(
            claim_id=claim.claim_id,
            outcome=VerificationOutcome.COUNTEREVIDENCE,
            cited_evidence_id=cited.evidence_id,
            counterevidence_evidence_ids=counterevidence_ids,
        )

    return VerificationResult(
        claim_id=claim.claim_id,
        outcome=VerificationOutcome.VERIFIED,
        cited_evidence_id=cited.evidence_id,
    )
