"""Deterministic admission checks before facts enter a frozen snapshot."""

from __future__ import annotations

from datetime import date

from .schemas import EvidenceEligibilityDecision, EvidenceEligibilityReason, EvidenceValue


def evaluate_eligibility(
    *, evidence: tuple[EvidenceValue, ...], expected_cik: str, as_of_date: date
) -> tuple[EvidenceEligibilityDecision, ...]:
    """Return one explicit admission decision for every normalized fact."""

    preliminary: dict[str, EvidenceEligibilityReason] = {}
    eligible_by_semantic_key: dict[tuple[str, str, str, date, date], list[EvidenceValue]] = {}
    for item in sorted(evidence, key=lambda value: value.evidence_id):
        if not item.accession or not item.source_url:
            reason = EvidenceEligibilityReason.MISSING_PROVENANCE
        elif not item.is_standard_tag:
            reason = EvidenceEligibilityReason.CUSTOM_TAG_UNSUPPORTED
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
            eligible_by_semantic_key.setdefault(item.semantic_key, []).append(item)
        preliminary[item.evidence_id] = reason

    for competing in eligible_by_semantic_key.values():
        if len(competing) < 2:
            continue
        duplicate_identity = {
            (item.accession, item.filed_at, item.value, item.source_url) for item in competing
        }
        reason = (
            EvidenceEligibilityReason.DUPLICATE_FACT
            if len(duplicate_identity) == 1
            else EvidenceEligibilityReason.UNRESOLVED_RESTATEMENT
        )
        for item in competing:
            preliminary[item.evidence_id] = reason

    return tuple(
        EvidenceEligibilityDecision(item.evidence_id, preliminary[item.evidence_id])
        for item in sorted(evidence, key=lambda value: value.evidence_id)
    )
