from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from quantify.engine import (
    CalibrationMethod,
    EvidenceSnapshot,
    EvidenceValue,
    MeasurementMode,
    MetricBaselineClaim,
    MetricThresholdClaim,
    Relation,
    SourceType,
    VerificationOutcome,
    build_upper_baseline_calibration,
    verify_claim,
)


def _fact(evidence_id: str, value: str, period_end: date) -> EvidenceValue:
    return EvidenceValue(
        evidence_id=evidence_id,
        entity_cik="0000789019",
        metric="revenue",
        value=Decimal(value),
        unit="USD",
        period_start=date(period_end.year - 1, 7, 1),
        period_end=period_end,
        accession=f"0000789019-{period_end.year}",
        filed_at=period_end,
        source_url="https://www.sec.gov/Archives/edgar/data/789019/example.htm",
    )


def _snapshot(*, target_value: str = "130") -> EvidenceSnapshot:
    return EvidenceSnapshot.freeze(
        snapshot_id="baseline-v1",
        evidence=(
            _fact("revenue-fy2022", "100", date(2022, 6, 30)),
            _fact("revenue-fy2023", "120", date(2023, 6, 30)),
            _fact("revenue-fy2024", target_value, date(2024, 6, 30)),
        ),
        source_type=SourceType.SEC_COMPANY_FACTS,
    )


def _claim(snapshot: EvidenceSnapshot) -> MetricBaselineClaim:
    calibration = build_upper_baseline_calibration(
        snapshot=snapshot,
        historical_evidence_ids=("revenue-fy2023", "revenue-fy2022"),
        historical_cutoff=date(2023, 6, 30),
    )
    return MetricBaselineClaim(
        claim_id="revenue-above-history",
        cited_evidence_id="revenue-fy2024",
        relation=Relation.OUTSIDE_UPPER_BASELINE,
        calibration=calibration,
    )


def test_historical_upper_baseline_is_replayable_and_records_all_metadata() -> None:
    snapshot = _snapshot()
    calibration = _claim(snapshot).calibration

    assert calibration.historical_evidence_ids == ("revenue-fy2022", "revenue-fy2023")
    assert calibration.lookback_periods == 2
    assert calibration.historical_cutoff == date(2023, 6, 30)
    assert calibration.upper_baseline == Decimal("120")
    assert calibration.scale_value == Decimal("20")
    assert calibration.method is CalibrationMethod.HISTORICAL_RANGE
    assert calibration.calibration_id.startswith("calibration-")


def test_calibrated_upper_baseline_returns_clipped_distance() -> None:
    snapshot = _snapshot(target_value="130")
    result = verify_claim(snapshot=snapshot, claim=_claim(snapshot))

    assert result.outcome is VerificationOutcome.VERIFIED
    assert result.measurement_mode is MeasurementMode.CALIBRATED_DISTANCE
    assert result.calibrated_distance == Decimal("0.5")
    assert result.calibration_id == _claim(snapshot).calibration.calibration_id


def test_calibrated_distance_caps_at_one() -> None:
    snapshot = _snapshot(target_value="150")

    assert verify_claim(snapshot=snapshot, claim=_claim(snapshot)).calibrated_distance == Decimal("1")


@pytest.mark.parametrize("target_value", ["120", "110"])
def test_equal_or_lower_than_upper_baseline_is_unsupported(target_value: str) -> None:
    snapshot = _snapshot(target_value=target_value)
    result = verify_claim(snapshot=snapshot, claim=_claim(snapshot))

    assert result.outcome is VerificationOutcome.UNSUPPORTED
    assert result.calibrated_distance == Decimal("0")


def test_verifier_rejects_altered_or_missing_calibration_semantics() -> None:
    snapshot = _snapshot()
    claim = _claim(snapshot)
    altered = replace(claim, calibration=replace(claim.calibration, scale_value=Decimal("999")))
    missing_history = replace(
        claim,
        calibration=replace(claim.calibration, historical_evidence_ids=("missing", "revenue-fy2023")),
    )

    assert verify_claim(snapshot=snapshot, claim=altered).outcome is VerificationOutcome.UNSUPPORTED
    assert verify_claim(snapshot=snapshot, claim=missing_history).outcome is VerificationOutcome.UNSUPPORTED


def test_calibration_rejects_zero_scale_and_future_history() -> None:
    zero_scale_snapshot = EvidenceSnapshot.freeze(
        snapshot_id="zero-scale",
        evidence=(
            _fact("one", "100", date(2022, 6, 30)),
            _fact("two", "100", date(2023, 6, 30)),
        ),
        source_type=SourceType.SEC_COMPANY_FACTS,
    )

    with pytest.raises(ValueError, match="scale must be positive"):
        build_upper_baseline_calibration(
            snapshot=zero_scale_snapshot,
            historical_evidence_ids=("one", "two"),
            historical_cutoff=date(2023, 6, 30),
        )
    with pytest.raises(ValueError, match="must not be after"):
        build_upper_baseline_calibration(
            snapshot=_snapshot(),
            historical_evidence_ids=("revenue-fy2023", "revenue-fy2024"),
            historical_cutoff=date(2023, 6, 30),
        )


def test_upper_baseline_relation_on_the_wrong_claim_type_fails_closed() -> None:
    snapshot = _snapshot()
    result = verify_claim(
        snapshot=snapshot,
        claim=MetricThresholdClaim(
            claim_id="invalid-baseline-claim",
            cited_evidence_id="revenue-fy2024",
            relation=Relation.OUTSIDE_UPPER_BASELINE,
            threshold=Decimal("120"),
        ),
    )

    assert result.outcome is VerificationOutcome.UNSUPPORTED
