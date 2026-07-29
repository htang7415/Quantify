"""Bounded, SEC-only evidence-acquisition planning."""

from __future__ import annotations

from dataclasses import dataclass

from quantify.engine import EvidenceSnapshot

from .coverage import EvidenceRequestType, assess_coverage


MAX_ACQUISITION_ROUNDS = 2


@dataclass(frozen=True, slots=True)
class EvidenceAcquisitionRecord:
    request_type: EvidenceRequestType
    reason: str


def approve_acquisition_requests(
    *,
    snapshot: EvidenceSnapshot,
    requested: tuple[EvidenceRequestType, ...],
) -> tuple[EvidenceAcquisitionRecord, ...]:
    """Approve only unmet, non-duplicated requests from the closed vocabulary."""

    if len(requested) > MAX_ACQUISITION_ROUNDS:
        raise ValueError("evidence acquisition exceeds the two-round V1 limit")
    if len(requested) != len(set(requested)):
        raise ValueError("evidence acquisition requests must be unique")
    available = set(assess_coverage(snapshot=snapshot))
    unsupported = set(requested).difference(available)
    if unsupported:
        raise ValueError("evidence acquisition request does not address a coverage gap")
    return tuple(
        EvidenceAcquisitionRecord(
            request_type=request_type,
            reason=f"deterministic coverage gap: {request_type.value}",
        )
        for request_type in sorted(requested, key=lambda item: item.value)
    )
