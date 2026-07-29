from __future__ import annotations

import json
from pathlib import Path

from quantify.evaluation.readiness_cli import main


ROOT = Path(__file__).parents[2]
CASE_ROOT = ROOT / "fixtures" / "cases"
SNAPSHOT_ROOT = ROOT / "fixtures" / "sec"


def _write_artifacts(tmp_path: Path, *, false_positive: bool = False) -> tuple[Path, Path]:
    payloads = [
        json.loads((CASE_ROOT / filename).read_text())
        for filename in ("mechanical_v1.json", "judgment_v1.json")
    ]
    cases = []
    for index, item in enumerate(
        case for payload in payloads for case in payload["cases"]
    ):
        expected = item.get("expected_verdict", "unclassified")
        cases.append(
            {
                "case_id": item["case_id"],
                "category": item["category"],
                "expected_outcome": expected,
                "prompt_only_outcome": (
                    "requires_agent_resolution" if index < 3 else expected
                ),
                "quantify_outcome": (
                    "defeated" if false_positive and index == 0 else expected
                ),
            }
        )
    parity_path = tmp_path / "parity.json"
    parity_path.write_text(
        json.dumps(
            {
                "artifact_version": "1.0.0",
                "run": {
                    "model": "pinned-fixture-v1",
                    "prompt_hash": "fixture-prompt-v1",
                    "temperature": 0,
                },
                "cases": cases,
            }
        )
    )
    operations_path = tmp_path / "operations.json"
    operations_path.write_text(
        json.dumps(
            {
                "artifact_version": "1.0.0",
                "measurements": {
                    "verified_defeated_flips": 0,
                    "latency_seconds": 1.0,
                    "cost_per_report": 0.01,
                    "sec_insufficiency_count": 0,
                },
            }
        )
    )
    return parity_path, operations_path


def _arguments(parity_path: Path, operations_path: Path) -> list[str]:
    return [
        "--mechanical-cases",
        str(CASE_ROOT / "mechanical_v1.json"),
        "--judgment-cases",
        str(CASE_ROOT / "judgment_v1.json"),
        "--snapshot-root",
        str(SNAPSHOT_ROOT),
        "--parity-artifact",
        str(parity_path),
        "--operations-artifact",
        str(operations_path),
    ]


def test_cli_emits_a_machine_readable_proceed_decision(tmp_path: Path, capsys) -> None:
    parity_path, operations_path = _write_artifacts(tmp_path)

    exit_code = main(_arguments(parity_path, operations_path))

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["readiness_run_version"] == "1.0.0"
    assert output["assessment"] == {
        "blockers": [],
        "decision": "proceed",
        "policy_version": "1.0.0",
    }


def test_cli_can_fail_a_release_gate_for_a_pause_decision(tmp_path: Path, capsys) -> None:
    parity_path, operations_path = _write_artifacts(tmp_path, false_positive=True)

    exit_code = main([*_arguments(parity_path, operations_path), "--fail-on-pause"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert output["assessment"]["decision"] == "pause"
    assert "mechanical_false_positive_rate" in output["assessment"]["blockers"]
