from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantify.evaluation import (
    plan_scheduled_evaluation_campaign,
    record_campaign_submission,
    reserve_campaign_submission,
    scheduled_evaluation_campaign_as_dict,
)
from quantify.evaluation import gemini_batch_cli
from quantify.evaluation.model_profiles import load_evaluation_model_profile


ROOT = Path(__file__).parents[2]
CASE_ROOT = ROOT / "fixtures" / "cases"
SNAPSHOT_ROOT = ROOT / "fixtures" / "sec"
PROFILE = ROOT / "fixtures" / "evaluation" / "gemini_3_1_flash_lite_batch_v1.json"


def _arguments(action: str, output: Path, *extra: str) -> list[str]:
    return [
        action,
        "--profile",
        str(PROFILE),
        "--mechanical-cases",
        str(CASE_ROOT / "mechanical_v1.json"),
        "--judgment-cases",
        str(CASE_ROOT / "judgment_v1.json"),
        "--snapshot-root",
        str(SNAPSHOT_ROOT),
        "--output",
        str(output),
        *extra,
    ]


def _campaign_arguments(tmp_path: Path, *, trial: int = 1) -> list[str]:
    campaign = plan_scheduled_evaluation_campaign(
        profile=load_evaluation_model_profile(path=PROFILE),
        trial_count=2,
        max_total_cost_usd=0.10,
    )
    campaign_path = tmp_path / "campaign.json"
    campaign_path.write_text(
        json.dumps(scheduled_evaluation_campaign_as_dict(campaign=campaign))
    )
    return [
        "--campaign",
        str(campaign_path),
        "--ledger",
        str(tmp_path / "campaign-ledger.json"),
        "--trial",
        str(trial),
    ]


def test_submit_prompt_only_writes_only_opaque_batch_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    class _PromptClient:
        def __init__(self, *, api_key: str) -> None:
            calls.append(api_key)

        def submit_prompt_only(self, *, profile, worklist):
            return SimpleNamespace(
                batch_name="batches/prompt-fixture",
                request_ids=tuple(item.request_id for item in worklist.items),
                estimated_total_cost_usd=0.02112,
            )

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemini_batch_cli, "GeminiBatchClient", _PromptClient)
    output = tmp_path / "prompt-submission.json"

    assert (
        gemini_batch_cli.main(
            _arguments("submit-prompt-only", output, *_campaign_arguments(tmp_path))
        )
        == 0
    )

    payload = json.loads(output.read_text())
    assert calls == ["test-key"]
    assert payload["path"] == "prompt_only"
    assert len(payload["request_ids"]) == 30
    assert "case_id" not in json.dumps(payload)
    assert "expected_outcome" not in json.dumps(payload)
    ledger = json.loads((tmp_path / "campaign-ledger.json").read_text())
    reservation = ledger["reservations"][0]
    assert reservation["batch_name"] == "batches/prompt-fixture"
    assert reservation["max_cost_usd"] == pytest.approx(0.02112)
    assert reservation["path"] == "prompt_only"
    assert reservation["status"] == "submitted"
    assert reservation["trial"] == 1
    assert reservation["submitted_at"]
    assert reservation["collected_at"] is None
    assert "test-key" not in json.dumps(ledger)


def test_collect_quantify_writes_the_compiler_input_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _QuantifyClient:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "test-key"

        def collect(self, *, batch_name: str, profile, worklist):
            assert batch_name == "batches/quantify-fixture"
            return SimpleNamespace(
                model=profile.model,
                temperature=profile.temperature,
                prompt_hash="a" * 64,
                outcomes=tuple(
                    (item.request_id, "unclassified") for item in worklist.items
                ),
            )

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        gemini_batch_cli, "GeminiQuantifyBatchClient", _QuantifyClient
    )
    output = tmp_path / "quantify-outcomes.json"
    campaign_options = _campaign_arguments(tmp_path)
    campaign = plan_scheduled_evaluation_campaign(
        profile=load_evaluation_model_profile(path=PROFILE),
        trial_count=2,
        max_total_cost_usd=0.10,
    )
    ledger_path = tmp_path / "campaign-ledger.json"
    reserve_campaign_submission(
        campaign=campaign,
        ledger_path=ledger_path,
        trial=1,
        path="quantify",
    )
    record_campaign_submission(
        campaign=campaign,
        ledger_path=ledger_path,
        trial=1,
        path="quantify",
        batch_name="batches/quantify-fixture",
    )

    assert (
        gemini_batch_cli.main(
            _arguments(
                "collect-quantify",
                output,
                *campaign_options,
                "--batch-name",
                "batches/quantify-fixture",
            )
        )
        == 0
    )

    payload = json.loads(output.read_text())
    assert payload["artifact_version"] == "1.0.0"
    assert payload["path"] == "quantify"
    assert len(payload["outcomes"]) == 30
    assert "case_id" not in json.dumps(payload)
    assert payload["trial"] == 1
    assert json.loads(ledger_path.read_text())["reservations"][0]["status"] == "collected"


def test_cli_requires_an_environment_only_api_key(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as error:
        gemini_batch_cli.main(_arguments("submit-prompt-only", tmp_path / "out.json"))

    assert error.value.code == 2


def test_cli_refuses_an_unmanaged_or_duplicate_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _PromptClient:
        def __init__(self, *, api_key: str) -> None:
            raise AssertionError("duplicate submission must not reach Gemini")

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemini_batch_cli, "GeminiBatchClient", _PromptClient)
    output = tmp_path / "prompt-submission.json"

    with pytest.raises(SystemExit) as missing_campaign:
        gemini_batch_cli.main(_arguments("submit-prompt-only", output))
    assert missing_campaign.value.code == 2

    campaign_options = _campaign_arguments(tmp_path)
    ledger_path = tmp_path / "campaign-ledger.json"
    campaign = plan_scheduled_evaluation_campaign(
        profile=load_evaluation_model_profile(path=PROFILE),
        trial_count=2,
        max_total_cost_usd=0.10,
    )
    reserve_campaign_submission(
        campaign=campaign,
        ledger_path=ledger_path,
        trial=1,
        path="prompt_only",
    )
    with pytest.raises(ValueError, match="already reserved"):
        gemini_batch_cli.main(
            _arguments("submit-prompt-only", output, *campaign_options)
        )
