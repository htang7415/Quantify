"""Versioned, explicit cost authorization for scheduled stability evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .model_profiles import EvaluationModelProfile, estimate_evaluation_cost


_PATHS = ("prompt_only", "quantify")
CampaignPath = Literal["prompt_only", "quantify"]


@dataclass(frozen=True, slots=True)
class ScheduledEvaluationCampaign:
    """The complete cost envelope for the frozen two-path stability campaign."""

    campaign_version: str
    provider: str
    model: str
    temperature: float
    case_count: int
    trial_count: int
    paths: tuple[str, ...]
    per_path_cost_usd: float
    estimated_total_cost_usd: float
    max_total_cost_usd: float


@dataclass(frozen=True, slots=True)
class CampaignReservation:
    """A fail-closed cost reservation for one provider batch submission."""

    trial: int
    path: CampaignPath
    max_cost_usd: float
    status: Literal["reserved", "submitted", "collected"]
    batch_name: str | None = None
    submitted_at: str | None = None
    collected_at: str | None = None


@dataclass(frozen=True, slots=True)
class CampaignLedger:
    """No-secret append-only accounting state for one campaign authorization."""

    ledger_version: str
    campaign_hash: str
    campaign: ScheduledEvaluationCampaign
    reservations: tuple[CampaignReservation, ...]


def plan_scheduled_evaluation_campaign(
    *,
    profile: EvaluationModelProfile,
    trial_count: int,
    max_total_cost_usd: float,
    case_count: int = 30,
) -> ScheduledEvaluationCampaign:
    """Require an explicit campaign budget before any repeated provider run."""

    if trial_count < 2:
        raise ValueError("scheduled stability evaluation requires at least two trials")
    if case_count != 30:
        raise ValueError("scheduled parity evaluation requires exactly 30 cases")
    if max_total_cost_usd <= 0:
        raise ValueError("scheduled evaluation budget must be positive")
    per_path = estimate_evaluation_cost(
        profile=profile, case_count=case_count, paths_per_case=1
    )
    estimated_total = per_path.total_cost_usd * len(_PATHS) * trial_count
    if estimated_total > max_total_cost_usd:
        raise ValueError(
            "scheduled evaluation token envelope exceeds the explicit campaign budget"
        )
    return ScheduledEvaluationCampaign(
        campaign_version="1.0.0",
        provider=profile.provider,
        model=profile.model,
        temperature=profile.temperature,
        case_count=case_count,
        trial_count=trial_count,
        paths=_PATHS,
        per_path_cost_usd=per_path.total_cost_usd,
        estimated_total_cost_usd=estimated_total,
        max_total_cost_usd=max_total_cost_usd,
    )


def scheduled_evaluation_campaign_as_dict(
    *, campaign: ScheduledEvaluationCampaign
) -> dict:
    """Canonical JSON-ready campaign artifact; it contains no credentials."""

    payload = asdict(campaign)
    payload["paths"] = list(campaign.paths)
    return payload


def load_scheduled_evaluation_campaign(*, path: Path) -> ScheduledEvaluationCampaign:
    """Load and validate the authorization artifact used before provider work."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        campaign = ScheduledEvaluationCampaign(
            campaign_version=payload["campaign_version"],
            provider=payload["provider"],
            model=payload["model"],
            temperature=payload["temperature"],
            case_count=payload["case_count"],
            trial_count=payload["trial_count"],
            paths=tuple(payload["paths"]),
            per_path_cost_usd=payload["per_path_cost_usd"],
            estimated_total_cost_usd=payload["estimated_total_cost_usd"],
            max_total_cost_usd=payload["max_total_cost_usd"],
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid scheduled evaluation campaign artifact") from error
    _validate_campaign(campaign)
    return campaign


def campaign_hash(*, campaign: ScheduledEvaluationCampaign) -> str:
    """Return the stable identity of the exact cost authorization."""

    payload = json.dumps(
        scheduled_evaluation_campaign_as_dict(campaign=campaign),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def require_campaign_matches_profile(
    *, campaign: ScheduledEvaluationCampaign, profile: EvaluationModelProfile
) -> None:
    """Reject a run when its authorization and pinned provider profile differ."""

    _validate_campaign(campaign)
    expected = estimate_evaluation_cost(
        profile=profile,
        case_count=campaign.case_count,
        paths_per_case=1,
    )
    if (
        campaign.provider != profile.provider
        or campaign.model != profile.model
        or campaign.temperature != profile.temperature
        or abs(campaign.per_path_cost_usd - expected.total_cost_usd) > 1e-12
    ):
        raise ValueError("campaign authorization does not match the pinned model profile")


def load_campaign_ledger(
    *, campaign: ScheduledEvaluationCampaign, ledger_path: Path
) -> CampaignLedger:
    """Load ledger state only when it belongs to the supplied authorization."""

    return _load_or_create_ledger(campaign=campaign, ledger_path=ledger_path)


def reserve_campaign_submission(
    *,
    campaign: ScheduledEvaluationCampaign,
    ledger_path: Path,
    trial: int,
    path: CampaignPath,
) -> CampaignLedger:
    """Reserve a unique batch slot before a paid submission is attempted.

    Reservations are intentionally never removed automatically.  A transport
    failure after a provider receives a request can be ambiguous, so retrying
    the same slot could exceed the authorized cost envelope.
    """

    _validate_submission_slot(campaign=campaign, trial=trial, path=path)
    ledger = _load_or_create_ledger(campaign=campaign, ledger_path=ledger_path)
    if any(
        item.trial == trial and item.path == path for item in ledger.reservations
    ):
        raise ValueError("scheduled evaluation campaign slot is already reserved")

    reservation = CampaignReservation(
        trial=trial,
        path=path,
        max_cost_usd=campaign.per_path_cost_usd,
        status="reserved",
    )
    updated = CampaignLedger(
        ledger_version=ledger.ledger_version,
        campaign_hash=ledger.campaign_hash,
        campaign=ledger.campaign,
        reservations=(*ledger.reservations, reservation),
    )
    _validate_ledger(updated)
    _write_ledger(path=ledger_path, ledger=updated)
    return updated


def record_campaign_submission(
    *,
    campaign: ScheduledEvaluationCampaign,
    ledger_path: Path,
    trial: int,
    path: CampaignPath,
    batch_name: str,
    recorded_at: str | None = None,
) -> CampaignLedger:
    """Attach the provider batch name to an existing cost reservation."""

    if not batch_name:
        raise ValueError("provider batch name is required for a campaign submission")
    ledger = _load_or_create_ledger(campaign=campaign, ledger_path=ledger_path)
    updated_reservations: list[CampaignReservation] = []
    found = False
    for item in ledger.reservations:
        if item.trial == trial and item.path == path:
            if item.status != "reserved":
                raise ValueError("scheduled evaluation campaign slot was already submitted")
            updated_reservations.append(
                CampaignReservation(
                    trial=item.trial,
                    path=item.path,
                    max_cost_usd=item.max_cost_usd,
                    status="submitted",
                    batch_name=batch_name,
                    submitted_at=recorded_at or _utc_timestamp(),
                )
            )
            found = True
        else:
            updated_reservations.append(item)
    if not found:
        raise ValueError("scheduled evaluation campaign slot was not reserved")
    updated = CampaignLedger(
        ledger_version=ledger.ledger_version,
        campaign_hash=ledger.campaign_hash,
        campaign=ledger.campaign,
        reservations=tuple(updated_reservations),
    )
    _validate_ledger(updated)
    _write_ledger(path=ledger_path, ledger=updated)
    return updated


def require_campaign_collection(
    *,
    campaign: ScheduledEvaluationCampaign,
    ledger_path: Path,
    trial: int,
    path: CampaignPath,
    batch_name: str,
) -> None:
    """Fail before collection unless the batch belongs to one submitted slot."""

    ledger = _load_or_create_ledger(campaign=campaign, ledger_path=ledger_path)
    matches = tuple(
        item
        for item in ledger.reservations
        if item.trial == trial and item.path == path
    )
    if len(matches) != 1 or matches[0].status != "submitted":
        raise ValueError("campaign collection requires one submitted ledger slot")
    if matches[0].batch_name != batch_name:
        raise ValueError("campaign collection batch does not match its ledger slot")


def record_campaign_collection(
    *,
    campaign: ScheduledEvaluationCampaign,
    ledger_path: Path,
    trial: int,
    path: CampaignPath,
    batch_name: str,
    recorded_at: str | None = None,
) -> CampaignLedger:
    """Record successful collection timing for an already submitted batch."""

    require_campaign_collection(
        campaign=campaign,
        ledger_path=ledger_path,
        trial=trial,
        path=path,
        batch_name=batch_name,
    )
    ledger = _load_or_create_ledger(campaign=campaign, ledger_path=ledger_path)
    updated = CampaignLedger(
        ledger_version=ledger.ledger_version,
        campaign_hash=ledger.campaign_hash,
        campaign=ledger.campaign,
        reservations=tuple(
            CampaignReservation(
                trial=item.trial,
                path=item.path,
                max_cost_usd=item.max_cost_usd,
                status="collected",
                batch_name=item.batch_name,
                submitted_at=item.submitted_at,
                collected_at=recorded_at or _utc_timestamp(),
            )
            if item.trial == trial and item.path == path
            else item
            for item in ledger.reservations
        ),
    )
    _validate_ledger(updated)
    _write_ledger(path=ledger_path, ledger=updated)
    return updated


def campaign_ledger_as_dict(*, ledger: CampaignLedger) -> dict[str, Any]:
    """Canonical JSON-ready accounting artifact; credentials never enter it."""

    return {
        "ledger_version": ledger.ledger_version,
        "campaign_hash": ledger.campaign_hash,
        "campaign": scheduled_evaluation_campaign_as_dict(campaign=ledger.campaign),
        "reservations": [asdict(item) for item in ledger.reservations],
    }


def _load_or_create_ledger(
    *, campaign: ScheduledEvaluationCampaign, ledger_path: Path
) -> CampaignLedger:
    if not ledger_path.exists():
        return CampaignLedger(
            ledger_version="1.0.0",
            campaign_hash=campaign_hash(campaign=campaign),
            campaign=campaign,
            reservations=(),
        )
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        recorded_campaign = _campaign_from_payload(payload["campaign"])
        reservations = tuple(
            CampaignReservation(
                trial=item["trial"],
                path=item["path"],
                max_cost_usd=item["max_cost_usd"],
                status=item["status"],
                batch_name=item.get("batch_name"),
                submitted_at=item.get("submitted_at"),
                collected_at=item.get("collected_at"),
            )
            for item in payload["reservations"]
        )
        ledger = CampaignLedger(
            ledger_version=payload["ledger_version"],
            campaign_hash=payload["campaign_hash"],
            campaign=recorded_campaign,
            reservations=reservations,
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid scheduled evaluation campaign ledger") from error
    _validate_ledger(ledger)
    if ledger.campaign_hash != campaign_hash(campaign=campaign):
        raise ValueError("campaign ledger belongs to a different authorization artifact")
    return ledger


def _campaign_from_payload(payload: dict[str, Any]) -> ScheduledEvaluationCampaign:
    campaign = ScheduledEvaluationCampaign(
        campaign_version=payload["campaign_version"],
        provider=payload["provider"],
        model=payload["model"],
        temperature=payload["temperature"],
        case_count=payload["case_count"],
        trial_count=payload["trial_count"],
        paths=tuple(payload["paths"]),
        per_path_cost_usd=payload["per_path_cost_usd"],
        estimated_total_cost_usd=payload["estimated_total_cost_usd"],
        max_total_cost_usd=payload["max_total_cost_usd"],
    )
    _validate_campaign(campaign)
    return campaign


def _validate_campaign(campaign: ScheduledEvaluationCampaign) -> None:
    if campaign.campaign_version != "1.0.0":
        raise ValueError("unsupported scheduled evaluation campaign version")
    if not campaign.provider or not campaign.model:
        raise ValueError("campaign requires a provider and model")
    if campaign.case_count != 30 or campaign.trial_count < 2:
        raise ValueError("campaign requires exactly 30 cases and at least two trials")
    if campaign.paths != _PATHS:
        raise ValueError("campaign requires the complete prompting-parity paths")
    numeric_values = (
        campaign.temperature,
        campaign.per_path_cost_usd,
        campaign.estimated_total_cost_usd,
        campaign.max_total_cost_usd,
    )
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in numeric_values):
        raise ValueError("campaign contains invalid numeric values")
    if campaign.per_path_cost_usd <= 0 or campaign.max_total_cost_usd <= 0:
        raise ValueError("campaign requires positive cost limits")
    expected_total = campaign.per_path_cost_usd * len(_PATHS) * campaign.trial_count
    if abs(campaign.estimated_total_cost_usd - expected_total) > 1e-12:
        raise ValueError("campaign total cost does not match its batch envelope")
    if campaign.estimated_total_cost_usd > campaign.max_total_cost_usd:
        raise ValueError("campaign cost exceeds its explicit budget")


def _validate_submission_slot(
    *, campaign: ScheduledEvaluationCampaign, trial: int, path: CampaignPath
) -> None:
    _validate_campaign(campaign)
    if isinstance(trial, bool) or not isinstance(trial, int) or not 1 <= trial <= campaign.trial_count:
        raise ValueError("campaign trial is outside the authorized range")
    if path not in campaign.paths:
        raise ValueError("campaign path is outside the authorized scope")


def _validate_ledger(ledger: CampaignLedger) -> None:
    if ledger.ledger_version != "1.0.0":
        raise ValueError("unsupported scheduled evaluation campaign ledger version")
    _validate_campaign(ledger.campaign)
    if ledger.campaign_hash != campaign_hash(campaign=ledger.campaign):
        raise ValueError("campaign ledger hash does not match its authorization")
    seen_slots: set[tuple[int, str]] = set()
    batch_names: set[str] = set()
    for reservation in ledger.reservations:
        _validate_submission_slot(
            campaign=ledger.campaign,
            trial=reservation.trial,
            path=reservation.path,
        )
        slot = (reservation.trial, reservation.path)
        if slot in seen_slots:
            raise ValueError("campaign ledger contains duplicate submission slots")
        seen_slots.add(slot)
        if reservation.status not in ("reserved", "submitted", "collected"):
            raise ValueError("campaign ledger contains an invalid reservation status")
        if reservation.status == "reserved" and any(
            value is not None
            for value in (
                reservation.batch_name,
                reservation.submitted_at,
                reservation.collected_at,
            )
        ):
            raise ValueError("reserved campaign slots cannot have provider metadata")
        if reservation.status in ("submitted", "collected"):
            if not reservation.batch_name or not reservation.submitted_at:
                raise ValueError("submitted campaign reservations require batch timing")
            if reservation.batch_name in batch_names:
                raise ValueError("campaign ledger reuses a provider batch name")
            batch_names.add(reservation.batch_name)
            submitted_at = _validate_timestamp(reservation.submitted_at)
        if reservation.status == "submitted" and reservation.collected_at is not None:
            raise ValueError("submitted campaign slots cannot have collection timing")
        if reservation.status == "collected":
            if reservation.collected_at is None:
                raise ValueError("collected campaign slots require collection timing")
            if _validate_timestamp(reservation.collected_at) < submitted_at:
                raise ValueError("campaign collection cannot precede submission")
        if abs(reservation.max_cost_usd - ledger.campaign.per_path_cost_usd) > 1e-12:
            raise ValueError("campaign ledger reservation cost does not match authorization")
    reserved_cost = sum(item.max_cost_usd for item in ledger.reservations)
    if reserved_cost > ledger.campaign.max_total_cost_usd + 1e-12:
        raise ValueError("campaign ledger exceeds its explicit budget")


def _write_ledger(*, path: Path, ledger: CampaignLedger) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(campaign_ledger_as_dict(ledger=ledger), sort_keys=True),
        encoding="utf-8",
    )


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("campaign timing must use an ISO-8601 timestamp")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("campaign timing must use an ISO-8601 timestamp") from error
    if timestamp.tzinfo is None:
        raise ValueError("campaign timing must include a timezone")
    return timestamp
