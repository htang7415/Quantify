from __future__ import annotations

import pytest

from quantify.regional_resilience import (
    CellState,
    RegionalCell,
    RegionalRecoveryError,
    exercise_recovery,
    select_regional_cell,
)


_HASH = "a" * 64


def _cell(region: str, *, state: CellState = CellState.HEALTHY, capacity: int = 5, release: str = _HASH) -> RegionalCell:
    return RegionalCell(region, state, release, "b" * 64, "sha256:" + "c" * 64, capacity)


def test_same_release_failover_selects_independent_highest_capacity_cell() -> None:
    decision = select_regional_cell(
        primary=_cell("us-east-2", state=CellState.UNAVAILABLE, capacity=0),
        candidates=(_cell("us-east-1", capacity=3), _cell("us-west-2", capacity=8)),
    )

    assert decision.selected_region == "us-west-2"
    assert decision.failover is True
    assert decision.reason == "same_release_failover"


def test_mismatched_release_or_policy_fails_closed() -> None:
    with pytest.raises(RegionalRecoveryError):
        select_regional_cell(
            primary=_cell("us-east-2", state=CellState.UNAVAILABLE, capacity=0),
            candidates=(_cell("us-east-1", release="d" * 64),),
        )


def test_recovery_exercise_records_unavailable_without_a_compatible_cell() -> None:
    exercise = exercise_recovery(
        scenario="provider-outage",
        primary=_cell("us-east-2", state=CellState.DEGRADED, capacity=0),
        candidates=(),
    )

    assert exercise.unavailable is True
    assert exercise.decision is None
