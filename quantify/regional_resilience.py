"""Fail-closed regional-cell selection and recovery evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CellState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class RegionalRecoveryError(RuntimeError):
    """No independent cell can preserve the declared verification contract."""


@dataclass(frozen=True, slots=True)
class RegionalCell:
    """The immutable compatibility and available budget for one regional cell."""

    region: str
    state: CellState
    evidence_release_manifest_hash: str
    policy_bundle_hash: str
    image_digest: str
    remaining_request_capacity: int

    def __post_init__(self) -> None:
        if not self.region or self.remaining_request_capacity < 0:
            raise ValueError("regional cell configuration is invalid")
        if not all(
            len(value) == 64 and all(char in "0123456789abcdef" for char in value)
            for value in (
                self.evidence_release_manifest_hash,
                self.policy_bundle_hash,
            )
        ) or not self.image_digest.startswith("sha256:"):
            raise ValueError("regional cell versions are not immutable")

    def can_accept(self) -> bool:
        return self.state is CellState.HEALTHY and self.remaining_request_capacity > 0


@dataclass(frozen=True, slots=True)
class FailoverDecision:
    selected_region: str
    failover: bool
    reason: str


def select_regional_cell(*, primary: RegionalCell, candidates: tuple[RegionalCell, ...]) -> FailoverDecision:
    """Select only a healthy cell with exactly the primary's evidence and policy."""

    if primary.can_accept():
        return FailoverDecision(primary.region, False, "primary_healthy")
    compatible = tuple(
        cell
        for cell in candidates
        if cell.region != primary.region
        and cell.can_accept()
        and cell.evidence_release_manifest_hash == primary.evidence_release_manifest_hash
        and cell.policy_bundle_hash == primary.policy_bundle_hash
        and cell.image_digest == primary.image_digest
    )
    if not compatible:
        raise RegionalRecoveryError("no compatible regional cell is available")
    selected = min(
        compatible,
        key=lambda cell: (-cell.remaining_request_capacity, cell.region),
    )
    return FailoverDecision(selected.region, True, "same_release_failover")


@dataclass(frozen=True, slots=True)
class RecoveryExercise:
    """Replayable evidence that one outage mode preserved fail-closed semantics."""

    scenario: str
    primary_state: CellState
    decision: FailoverDecision | None
    unavailable: bool


def exercise_recovery(*, scenario: str, primary: RegionalCell, candidates: tuple[RegionalCell, ...]) -> RecoveryExercise:
    """Record a provider-neutral recovery result without executing customer work."""

    try:
        decision = select_regional_cell(primary=primary, candidates=candidates)
    except RegionalRecoveryError:
        return RecoveryExercise(scenario, primary.state, None, True)
    return RecoveryExercise(scenario, primary.state, decision, False)
