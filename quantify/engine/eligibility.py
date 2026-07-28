"""Deterministic admission checks before facts enter a frozen snapshot."""

from __future__ import annotations

from datetime import date

from .schemas import EvidenceEligibilityDecision, EvidenceEligibilityReason, EvidenceValue


def evaluate_eligibility(
    *, evidence: tuple[EvidenceValue, ...], expected_cik: str, as_of_date: date
) -> tuple[EvidenceEligibilityDecision, ...]:
    """Return one explicit admission decision for every normalized fact."""

    decisions: list[EvidenceEligibilityDecision] = []
    for item in sorted(evidence, key=lambda value: value.evidence_id):
        if not item.accession or not item.source_url:
            reason = EvidenceEligibilityReason.MISSING_PROVENANCE
        elif item.entity_cik != expected_cik:
            reason = EvidenceEligibilityReason.ENTITY_SCOPE_MISMATCH
        elif not item.unit:
            reason = EvidenceEligibilityReason.UNIT_MISMATCH
        elif item.period_start > item.period_end:
            reason = EvidenceEligibilityReason.PERIOD_ALIGNMENT_MISMATCH
        elif item.filed_at > as_of_date:
            reason = EvidenceEligibilityReason.FUTURE_FILING
        elif not item.eligible:
            reason = EvidenceEligibilityReason.TRANSFORMATION_FAILURE
        else:
            reason = EvidenceEligibilityReason.ELIGIBLE
        decisions.append(EvidenceEligibilityDecision(item.evidence_id, reason))
    return tuple(decisions)
