"""Pure temporal-persistence annotations for frozen, comparable SEC evidence."""

from __future__ import annotations

from collections import defaultdict

from .schemas import (
    EvidenceSnapshot,
    EvidenceValue,
    PersistenceDirection,
    TemporalPersistence,
)


def annotate_temporal_persistence(
    *, snapshot: EvidenceSnapshot
) -> tuple[TemporalPersistence, ...]:
    """Describe contiguous comparable periods without affecting any verdict.

    Annual, point-in-time, and SEC year-to-date interim durations are kept in
    separate families.  A sequence breaks if its period ends are more than one
    reporting year apart, preventing a missing year from being called
    consecutive.  This function never infers standalone quarters.
    """

    by_family: dict[tuple[str, str, str, str], list[EvidenceValue]] = defaultdict(list)
    for evidence in snapshot.evidence:
        if evidence.eligible:
            by_family[
                (
                    evidence.entity_cik,
                    evidence.metric,
                    evidence.unit,
                    _period_family(evidence),
                )
            ].append(evidence)

    annotations: list[TemporalPersistence] = []
    for (_, metric, _, _), evidence in sorted(by_family.items()):
        ordered = sorted(
            evidence,
            key=lambda item: (item.period_end, item.period_start, item.evidence_id),
        )
        for run in _consecutive_runs(ordered):
            if len(run) < 2:
                continue
            annotations.append(
                TemporalPersistence(
                    metric_name=metric,
                    consecutive_periods=len(run),
                    direction=_direction(run),
                    period_ids=tuple(item.evidence_id for item in run),
                )
            )
    return tuple(
        sorted(
            annotations,
            key=lambda item: (item.metric_name, item.period_ids),
        )
    )


def _period_family(evidence: EvidenceValue) -> str:
    duration_days = (evidence.period_end - evidence.period_start).days
    if duration_days == 0:
        return "instant"
    if duration_days >= 300:
        return "annual"
    if duration_days <= 120:
        return "interim_ytd_q1"
    if duration_days <= 220:
        return "interim_ytd_q2"
    return "interim_ytd_q3"


def _consecutive_runs(
    evidence: list[EvidenceValue],
) -> tuple[tuple[EvidenceValue, ...], ...]:
    if not evidence:
        return ()
    runs: list[list[EvidenceValue]] = [[evidence[0]]]
    for item in evidence[1:]:
        previous = runs[-1][-1]
        elapsed_days = (item.period_end - previous.period_end).days
        if 300 <= elapsed_days <= 430:
            runs[-1].append(item)
        else:
            runs.append([item])
    return tuple(tuple(run) for run in runs)


def _direction(evidence: tuple[EvidenceValue, ...]) -> PersistenceDirection:
    deltas = [
        current.value - previous.value
        for previous, current in zip(evidence, evidence[1:])
    ]
    if all(delta > 0 for delta in deltas):
        return PersistenceDirection.POSITIVE
    if all(delta < 0 for delta in deltas):
        return PersistenceDirection.NEGATIVE
    return PersistenceDirection.MIXED
