from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "deploy" / "aws" / "monitor_anonymous_trial.py"


def _module():
    spec = importlib.util.spec_from_file_location("anonymous_trial_monitor", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_monitor_reports_remaining_capacity_without_report_content(monkeypatch, capsys) -> None:
    module = _module()
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    monkeypatch.setenv("PUBLIC_AGENT_STACK_NAME", "quantify-public-agent")
    monkeypatch.setattr(
        module,
        "_parameters",
        lambda **kwargs: {
            "TrialEnabled": "true",
            "TrialExpiresAt": "2099-08-14T23:59:59Z",
            "TrialDailyRequestLimit": "100",
            "TrialDailyCostLimitMicroUsd": "250000",
        },
    )
    monkeypatch.setattr(module, "_ledger_name", lambda **kwargs: "trial-ledger")
    monkeypatch.setattr(module, "_daily_usage", lambda **kwargs: (2, 5000))

    module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["request_count"] == 2
    assert payload["remaining_daily_requests"] == 98
    assert payload["remaining_daily_cost_micro_usd"] == 245000
    assert "analysis" not in json.dumps(payload)


def test_monitor_rejects_an_expired_trial(monkeypatch) -> None:
    module = _module()
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    monkeypatch.setenv("PUBLIC_AGENT_STACK_NAME", "quantify-public-agent")
    monkeypatch.setattr(
        module,
        "_parameters",
        lambda **kwargs: {
            "TrialEnabled": "true",
            "TrialExpiresAt": "2020-01-01T00:00:00Z",
            "TrialDailyRequestLimit": "100",
            "TrialDailyCostLimitMicroUsd": "250000",
        },
    )

    try:
        module.main()
    except RuntimeError as error:
        assert "disabled or expired" in str(error)
    else:
        raise AssertionError("expected an expired trial to be rejected")


def test_daily_usage_treats_a_missing_current_day_item_as_zero(monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "_aws", lambda *arguments: "")

    assert module._daily_usage(table_name="trial-ledger", day="2026-08-01", region="us-east-2") == (0, 0)
