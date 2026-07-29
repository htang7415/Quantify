"""Compile completed campaign records into offline Batch quality measurements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .campaign import CampaignLedger, ScheduledEvaluationCampaign, campaign_hash
from .stability import RepeatedRunStability


@dataclass(frozen=True, slots=True)
class ScheduledOperationalMeasurements:
    """Measurements derived from completed no-secret campaign ledger entries."""

    artifact_version: str
    campaign_hash: str
    completed_batch_count: int
    mean_batch_elapsed_seconds: float
    quantify_max_cost_per_report: float
    sec_insufficiency_count: int
    verified_defeated_flips: int


def compile_scheduled_operational_measurements(
    *,
    campaign: ScheduledEvaluationCampaign,
    ledger: CampaignLedger,
    stability: RepeatedRunStability,
    sec_insufficiency_count: int,
) -> ScheduledOperationalMeasurements:
    """Produce Batch quality measurements only from a complete authorized run.

    Gemini Batch does not provide a billing receipt in the Batch result used by
    this adapter.  Cost is therefore recorded as the pinned maximum token-price
    envelope, never represented as an observed invoice amount.
    """

    if ledger.campaign_hash != campaign_hash(campaign=campaign):
        raise ValueError("operational ledger does not match its campaign authorization")
    if stability.case_count != campaign.case_count or stability.trial_count != campaign.trial_count:
        raise ValueError("stability artifact does not match the completed campaign")
    if (
        isinstance(sec_insufficiency_count, bool)
        or not isinstance(sec_insufficiency_count, int)
        or sec_insufficiency_count < 0
        or sec_insufficiency_count > campaign.case_count
    ):
        raise ValueError("SEC insufficiency count must be between zero and case count")
    expected_slots = {
        (trial, path)
        for trial in range(1, campaign.trial_count + 1)
        for path in campaign.paths
    }
    completed = {(item.trial, item.path): item for item in ledger.reservations}
    if set(completed) != expected_slots or any(
        item.status != "collected" for item in completed.values()
    ):
        raise ValueError("operational measurements require all campaign batches collected")
    elapsed = tuple(
        _elapsed_seconds(submitted_at=item.submitted_at, collected_at=item.collected_at)
        for item in completed.values()
    )
    quantify_cost = sum(
        item.max_cost_usd for item in completed.values() if item.path == "quantify"
    )
    return ScheduledOperationalMeasurements(
        artifact_version="1.1.0",
        campaign_hash=ledger.campaign_hash,
        completed_batch_count=len(completed),
        mean_batch_elapsed_seconds=sum(elapsed) / len(elapsed),
        quantify_max_cost_per_report=(
            quantify_cost / (campaign.trial_count * campaign.case_count)
        ),
        sec_insufficiency_count=sec_insufficiency_count,
        verified_defeated_flips=(
            stability.quantify.mechanical_verified_defeated_flips
        ),
    )


def scheduled_operational_measurements_as_dict(
    *, measurements: ScheduledOperationalMeasurements
) -> dict[str, Any]:
    """Return the strict v1.1 Batch-quality artifact without credentials."""

    return {
        "artifact_version": measurements.artifact_version,
        "campaign_hash": measurements.campaign_hash,
        "provenance": {
            "completed_batch_count": measurements.completed_batch_count,
            "latency_kind": "mean_submitted_to_collected_batch_elapsed_seconds",
            "cost_kind": "quantify_maximum_token_envelope_per_report",
        },
        "measurements": {
            "verified_defeated_flips": measurements.verified_defeated_flips,
            "latency_seconds": measurements.mean_batch_elapsed_seconds,
            "cost_per_report": measurements.quantify_max_cost_per_report,
            "sec_insufficiency_count": measurements.sec_insufficiency_count,
        },
    }


def _elapsed_seconds(*, submitted_at: str | None, collected_at: str | None) -> float:
    if not submitted_at or not collected_at:
        raise ValueError("completed campaign batch is missing timing metadata")
    try:
        elapsed = (
            datetime.fromisoformat(collected_at) - datetime.fromisoformat(submitted_at)
        ).total_seconds()
    except ValueError as error:
        raise ValueError("campaign timing must use ISO-8601 timestamps") from error
    if elapsed < 0:
        raise ValueError("campaign collection cannot precede submission")
    return elapsed
