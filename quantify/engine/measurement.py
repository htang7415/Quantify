"""Deterministic calibration for historical baseline claims."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from hashlib import sha256
import json

from .schemas import (
    Calibration,
    CalibrationMethod,
    EvidenceSnapshot,
    EvidenceValue,
)


def _canonical_calibration_id(
    *,
    historical_evidence_ids: tuple[str, ...],
    historical_cutoff: date,
    upper_baseline: Decimal,
    scale_value: Decimal,
    method: CalibrationMethod,
) -> str:
    payload = {
        "historical_evidence_ids": historical_evidence_ids,
        "historical_cutoff": historical_cutoff.isoformat(),
        "upper_baseline": str(upper_baseline),
        "scale_value": str(scale_value),
        "method": method.value,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"calibration-{sha256(encoded).hexdigest()[:16]}"


def build_upper_baseline_calibration(
    *,
    snapshot: EvidenceSnapshot,
    historical_evidence_ids: tuple[str, ...],
    historical_cutoff: date,
    method: CalibrationMethod = CalibrationMethod.HISTORICAL_RANGE,
) -> Calibration:
    """Build a replayable upper baseline from compatible historical facts.

    The initial method uses the maximum historical value as the upper baseline
    and the historical range as its calibrated scale. At least two distinct
    observations are necessary; a zero range cannot yield a meaningful scale.
    """

    canonical_ids = tuple(sorted(historical_evidence_ids))
    if len(canonical_ids) < 2 or len(canonical_ids) != len(set(canonical_ids)):
        raise ValueError("calibration requires at least two unique historical facts")

    historical: list[EvidenceValue] = []
    for evidence_id in canonical_ids:
        item = snapshot.evidence_by_id(evidence_id)
        if item is None or not item.eligible:
            raise ValueError("calibration requires eligible historical facts")
        if item.period_end > historical_cutoff:
            raise ValueError("historical facts must not be after the historical cutoff")
        historical.append(item)

    comparability_key = historical[0].comparability_key
    if any(item.comparability_key != comparability_key for item in historical[1:]):
        raise ValueError("historical calibration facts must be comparable")
    if method is not CalibrationMethod.HISTORICAL_RANGE:
        raise ValueError(f"unsupported calibration method: {method}")

    upper_baseline = max(item.value for item in historical)
    scale_value = upper_baseline - min(item.value for item in historical)
    if scale_value <= 0:
        raise ValueError("calibration scale must be positive")

    return Calibration(
        calibration_id=_canonical_calibration_id(
            historical_evidence_ids=canonical_ids,
            historical_cutoff=historical_cutoff,
            upper_baseline=upper_baseline,
            scale_value=scale_value,
            method=method,
        ),
        historical_evidence_ids=canonical_ids,
        lookback_periods=len(canonical_ids),
        historical_cutoff=historical_cutoff,
        upper_baseline=upper_baseline,
        scale_value=scale_value,
        method=method,
    )
