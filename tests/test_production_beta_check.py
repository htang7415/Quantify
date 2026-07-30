from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "check_production_beta.py"
spec = importlib.util.spec_from_file_location("check_production_beta", SCRIPT)
check_production_beta = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(check_production_beta)


def _environment_file(path: Path) -> Path:
    path.write_text(
        "\n".join(
            (
                "AWS_REGION=us-east-2",
                "PRODUCTION_CORE_STACK_NAME=quantify-production-core",
                "PUBLIC_AGENT_STACK_NAME=quantify-public-agent",
                "MONTHLY_COST_LIMIT_MICRO_USD=9000000",
            )
        )
    )
    return path


def test_production_beta_check_reports_only_aggregate_health(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    def fake_aws(*arguments: str, environment: dict[str, str]) -> str:
        command = " ".join(arguments)
        if "StackStatus" in command:
            return "UPDATE_COMPLETE"
        if "MetricAlarms[].StateValue" in command:
            return json.dumps(["OK", "OK"])
        if "Outputs[]." in command:
            return json.dumps(
                [
                    {"key": "AuditManifestBucketName", "value": "private-audit-bucket"},
                    {"key": "MonthlyCostLedgerName", "value": "private-cost-ledger"},
                ]
            )
        if "list-objects-v2" in command:
            return "3"
        if "dynamodb get-item" in command:
            return json.dumps({"Item": {"reserved_micro_usd": {"N": "12384"}}})
        raise AssertionError(command)

    monkeypatch.setattr(check_production_beta, "_aws", fake_aws)
    check_production_beta.main(["--env-file", str(_environment_file(tmp_path / "production.env"))])

    assert json.loads(capsys.readouterr().out) == {
        "audit_manifest_count": 3,
        "core_alarm_count": 2,
        "core_stack": "quantify-production-core",
        "month": check_production_beta.dt.datetime.now(check_production_beta.dt.UTC).strftime("%Y-%m"),
        "public_alarm_count": 2,
        "public_stack": "quantify-public-agent",
        "remaining_micro_usd": 8987616,
        "reserved_micro_usd": 12384,
    }


def test_production_beta_check_rejects_non_ok_alarm(tmp_path: Path, monkeypatch) -> None:
    def fake_aws(*arguments: str, environment: dict[str, str]) -> str:
        if "StackStatus" in " ".join(arguments):
            return "UPDATE_COMPLETE"
        if "MetricAlarms[].StateValue" in " ".join(arguments):
            return json.dumps(["ALARM"])
        raise AssertionError("remaining checks must not run after an alarm")

    monkeypatch.setattr(check_production_beta, "_aws", fake_aws)
    with pytest.raises(RuntimeError, match="non-OK alarm"):
        check_production_beta.main(["--env-file", str(_environment_file(tmp_path / "production.env"))])
