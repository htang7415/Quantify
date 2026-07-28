"""Deterministic eligibility and restatement selection policies."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from .schemas import (
    EvidenceEligibilityDecision,
    EvidenceEligibilityReason,
    EvidenceSnapshot,
    EvidenceValue,
    RestatementPolicy,
    RestatementSelection,
    SourceType,
)


def _has_provenance(evidence: EvidenceValue) -> bool:
    return bool(evidence.accession and evidence.source_url)


def _selection_key(evidence: EvidenceValue) -> tuple[date, str, str]:
    return (evidence.filed_at, evidence.accession, evidence.evidence_id)


def select_evidence(
    *,
    evidence: tuple[EvidenceValue, ...],
    policy: RestatementPolicy,
    as_of_date: date,
) -> tuple[tuple[EvidenceValue, ...], RestatementSelection]:
    """Select one eligible fact per semantic identity under a named policy.

    ``AS_FILED_AT_CUTOFF`` preserves the earliest eligible filed value for a
    period. ``LATEST_AVAILABLE_AT_CUTOFF`` uses the most recently filed value
    known at the supplied cutoff. ``LATEST_KNOWN`` ignores the cutoff when
    choosing the most recent value. Facts without provenance and facts not yet
    filed at the cutoff cannot enter the result.
    """

    decisions: list[EvidenceEligibilityDecision] = []
    candidates: list[EvidenceValue] = []
    for item in sorted(evidence, key=lambda value: value.evidence_id):
        if not _has_provenance(item):
            decisions.append(
                EvidenceEligibilityDecision(
                    evidence_id=item.evidence_id,
                    reason=EvidenceEligibilityReason.MISSING_PROVENANCE,
                )
            )
        elif policy is not RestatementPolicy.LATEST_KNOWN and item.filed_at > as_of_date:
            decisions.append(
                EvidenceEligibilityDecision(
                    evidence_id=item.evidence_id,
                    reason=EvidenceEligibilityReason.FUTURE_FILING,
                )
            )
        else:
            candidates.append(item)

    grouped: dict[tuple[str, str, str, date, date], list[EvidenceValue]] = {}
    for item in candidates:
        grouped.setdefault(item.semantic_key, []).append(item)

    selected: list[EvidenceValue] = []
    superseded_ids: list[str] = []
    for semantic_key in sorted(grouped):
        competing = sorted(grouped[semantic_key], key=_selection_key)
        if policy is RestatementPolicy.AS_FILED_AT_CUTOFF:
            chosen = competing[0]
        else:
            chosen = competing[-1]
        selected.append(replace(chosen, eligible=True))
        decisions.append(
            EvidenceEligibilityDecision(
                evidence_id=chosen.evidence_id,
                reason=EvidenceEligibilityReason.ELIGIBLE,
            )
        )
        superseded_ids.extend(
            item.evidence_id for item in competing if item.evidence_id != chosen.evidence_id
        )

    selected_ids = tuple(item.evidence_id for item in sorted(selected, key=_selection_key))
    selection = RestatementSelection(
        policy=policy,
        as_of_date=as_of_date,
        selected_evidence_ids=selected_ids,
        superseded_evidence_ids=tuple(sorted(superseded_ids)),
        eligibility_decisions=tuple(sorted(decisions, key=lambda item: item.evidence_id)),
    )
    return tuple(sorted(selected, key=lambda item: item.evidence_id)), selection


def freeze_selected_snapshot(
    *,
    snapshot_id: str,
    evidence: tuple[EvidenceValue, ...],
    policy: RestatementPolicy,
    as_of_date: date,
    source_type: SourceType,
) -> tuple[EvidenceSnapshot, RestatementSelection]:
    """Apply policy before producing a production-valid immutable snapshot."""

    selected, selection = select_evidence(
        evidence=evidence, policy=policy, as_of_date=as_of_date
    )
    return (
        EvidenceSnapshot.freeze(
            snapshot_id=snapshot_id,
            evidence=selected,
            source_type=source_type,
        ),
        selection,
    )
