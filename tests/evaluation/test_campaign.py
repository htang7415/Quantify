from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantify.evaluation import (
    campaign_ledger_as_dict,
    load_evaluation_model_profile,
    load_scheduled_evaluation_campaign,
    plan_scheduled_evaluation_campaign,
    record_campaign_submission,
    reserve_campaign_submission,
)
from quantify.evaluation.campaign_cli import main


ROOT = Path(__file__).parents[2]
PROFILE = ROOT / "fixtures" / "evaluation" / "gemini_3_1_flash_lite_batch_v1.json"


def test_two_trial_campaign_requires_an_explicit_budget_for_all_four_batches() -> None:
    campaign = plan_scheduled_evaluation_campaign(
        profile=load_evaluation_model_profile(path=PROFILE),
        trial_count=2,
        max_total_cost_usd=0.30,
    )

    assert campaign.paths == ("prompt_only", "quantify")
    assert campaign.per_path_cost_usd == pytest.approx(0.06912)
    assert campaign.estimated_total_cost_usd == pytest.approx(0.27648)


def test_campaign_refuses_a_budget_that_only_covers_one_trial() -> None:
    with pytest.raises(ValueError, match="explicit campaign budget"):
        plan_scheduled_evaluation_campaign(
            profile=load_evaluation_model_profile(path=PROFILE),
            trial_count=2,
            max_total_cost_usd=0.05,
        )


def test_campaign_cli_writes_a_no_secret_authorization_artifact(tmp_path: Path) -> None:
    output = tmp_path / "campaign.json"

    assert (
        main(
            [
                "--profile",
                str(PROFILE),
                "--max-total-cost-usd",
                "0.30",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    payload = json.loads(output.read_text())
    assert payload["campaign_version"] == "1.0.0"
    assert payload["estimated_total_cost_usd"] == pytest.approx(0.27648)
    assert "api_key" not in json.dumps(payload)


def test_ledger_reserves_each_authorized_slot_once_and_records_the_batch(
    tmp_path: Path,
) -> None:
    campaign = plan_scheduled_evaluation_campaign(
        profile=load_evaluation_model_profile(path=PROFILE),
        trial_count=2,
        max_total_cost_usd=0.30,
    )
    ledger_path = tmp_path / "campaign-ledger.json"

    reserved = reserve_campaign_submission(
        campaign=campaign,
        ledger_path=ledger_path,
        trial=1,
        path="prompt_only",
    )
    submitted = record_campaign_submission(
        campaign=campaign,
        ledger_path=ledger_path,
        trial=1,
        path="prompt_only",
        batch_name="batches/prompt-fixture",
    )

    assert reserved.reservations[0].status == "reserved"
    assert submitted.reservations[0].status == "submitted"
    assert submitted.reservations[0].batch_name == "batches/prompt-fixture"
    assert (
        json.loads(ledger_path.read_text())
        == campaign_ledger_as_dict(ledger=submitted)
    )
    with pytest.raises(ValueError, match="already reserved"):
        reserve_campaign_submission(
            campaign=campaign,
            ledger_path=ledger_path,
            trial=1,
            path="prompt_only",
        )


def test_ledger_refuses_a_tampered_or_different_campaign_authorization(
    tmp_path: Path,
) -> None:
    campaign_path = tmp_path / "campaign.json"
    campaign_path.write_text(
        json.dumps(
            {
                **{
                    "campaign_version": "1.0.0",
                    "provider": "google",
                    "model": "gemini-3.1-flash-lite",
                    "temperature": 0,
                    "case_count": 30,
                    "trial_count": 2,
                    "paths": ["prompt_only", "quantify"],
                    "per_path_cost_usd": 0.02112,
                    "estimated_total_cost_usd": 0.08448,
                    "max_total_cost_usd": 0.10,
                }
            }
        )
    )
    campaign = load_scheduled_evaluation_campaign(path=campaign_path)
    ledger_path = tmp_path / "campaign-ledger.json"
    reserve_campaign_submission(
        campaign=campaign,
        ledger_path=ledger_path,
        trial=1,
        path="prompt_only",
    )
    changed_campaign = plan_scheduled_evaluation_campaign(
        profile=load_evaluation_model_profile(path=PROFILE),
        trial_count=2,
        max_total_cost_usd=0.31,
    )

    with pytest.raises(ValueError, match="different authorization"):
        reserve_campaign_submission(
            campaign=changed_campaign,
            ledger_path=ledger_path,
            trial=1,
            path="quantify",
        )
