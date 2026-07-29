from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantify.evaluation import (
    PromptingParityArtifact,
    PromptingParityCase,
    compile_scheduled_operational_measurements,
    evaluate_repeated_run_stability,
    load_campaign_ledger,
    load_evaluation_model_profile,
    plan_scheduled_evaluation_campaign,
    record_campaign_collection,
    record_campaign_submission,
    reserve_campaign_submission,
    scheduled_evaluation_campaign_as_dict,
    scheduled_operational_measurements_as_dict,
)
from quantify.evaluation.operations_cli import main
from quantify.evaluation.readiness_run import load_operational_measurements
from quantify.evaluation.stability import repeated_run_stability_as_dict


ROOT = Path(__file__).parents[2]
PROFILE = ROOT / "fixtures" / "evaluation" / "gemini_3_1_flash_lite_batch_v1.json"


def _stability():
    cases = tuple(
        PromptingParityCase(
            case_id=f"mechanical-{index}",
            category="mechanical",
            expected_outcome="verified",
            prompt_only_outcome="verified",
            quantify_outcome="verified",
        )
        for index in range(20)
    ) + tuple(
        PromptingParityCase(
            case_id=f"judgment-{index}",
            category="judgment",
            expected_outcome="unclassified",
            prompt_only_outcome="unclassified",
            quantify_outcome="unclassified",
        )
        for index in range(10)
    )
    trial = PromptingParityArtifact(
        artifact_version="1.1.0",
        model="gemini-3.1-flash-lite",
        prompt_hash="prompt-hash",
        temperature=0.0,
        quantify_model="gemini-3.1-flash-lite",
        quantify_prompt_hash="quantify-hash",
        quantify_temperature=0.0,
        cases=cases,
    )
    return evaluate_repeated_run_stability(first_trial=trial, second_trial=trial)


def _completed_campaign(tmp_path: Path):
    campaign = plan_scheduled_evaluation_campaign(
        profile=load_evaluation_model_profile(path=PROFILE),
        trial_count=2,
        max_total_cost_usd=0.10,
    )
    ledger_path = tmp_path / "ledger.json"
    for trial in (1, 2):
        for path in ("prompt_only", "quantify"):
            reserve_campaign_submission(
                campaign=campaign, ledger_path=ledger_path, trial=trial, path=path
            )
            record_campaign_submission(
                campaign=campaign,
                ledger_path=ledger_path,
                trial=trial,
                path=path,
                batch_name=f"batches/{trial}-{path}",
                recorded_at="2026-07-29T00:00:00+00:00",
            )
            record_campaign_collection(
                campaign=campaign,
                ledger_path=ledger_path,
                trial=trial,
                path=path,
                batch_name=f"batches/{trial}-{path}",
                recorded_at="2026-07-29T00:00:12+00:00",
            )
    return campaign, ledger_path


def test_operations_are_derived_from_all_completed_authorized_batches(
    tmp_path: Path,
) -> None:
    campaign, ledger_path = _completed_campaign(tmp_path)
    measurements = compile_scheduled_operational_measurements(
        campaign=campaign,
        ledger=load_campaign_ledger(campaign=campaign, ledger_path=ledger_path),
        stability=_stability(),
        sec_insufficiency_count=0,
    )

    assert measurements.completed_batch_count == 4
    assert measurements.mean_batch_elapsed_seconds == 12.0
    assert measurements.quantify_max_cost_per_report == pytest.approx(0.000704)
    payload = scheduled_operational_measurements_as_dict(measurements=measurements)
    path = tmp_path / "operations.json"
    path.write_text(json.dumps(payload))
    assert load_operational_measurements(path=path).cost_per_report == pytest.approx(
        0.000704
    )


def test_operations_refuse_incomplete_campaigns(tmp_path: Path) -> None:
    campaign = plan_scheduled_evaluation_campaign(
        profile=load_evaluation_model_profile(path=PROFILE),
        trial_count=2,
        max_total_cost_usd=0.10,
    )
    ledger_path = tmp_path / "ledger.json"
    reserve_campaign_submission(
        campaign=campaign, ledger_path=ledger_path, trial=1, path="prompt_only"
    )

    with pytest.raises(ValueError, match="all campaign batches collected"):
        compile_scheduled_operational_measurements(
            campaign=campaign,
            ledger=load_campaign_ledger(campaign=campaign, ledger_path=ledger_path),
            stability=_stability(),
            sec_insufficiency_count=0,
        )


def test_operations_cli_writes_a_readiness_compatible_artifact(tmp_path: Path) -> None:
    campaign, ledger_path = _completed_campaign(tmp_path)
    campaign_path = tmp_path / "campaign.json"
    campaign_path.write_text(
        json.dumps(scheduled_evaluation_campaign_as_dict(campaign=campaign))
    )
    stability_path = tmp_path / "stability.json"
    stability_path.write_text(
        json.dumps(repeated_run_stability_as_dict(stability=_stability()))
    )
    output = tmp_path / "operations.json"

    assert main([
        "--campaign", str(campaign_path),
        "--ledger", str(ledger_path),
        "--stability-artifact", str(stability_path),
        "--sec-insufficiency-count", "0",
        "--output", str(output),
    ]) == 0

    assert json.loads(output.read_text())["artifact_version"] == "1.1.0"
