from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from quantify.policy_control import ReleaseGatePolicy


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "deploy" / "aws" / "gate_research_task_release.py"
spec = importlib.util.spec_from_file_location("gate_research_task_release", SCRIPT)
gate_research_task_release = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(gate_research_task_release)


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value))
    return path


def test_release_gate_binds_policy_measurements_sources_and_reviewer(tmp_path: Path, capsys) -> None:
    policy = ReleaseGatePolicy("1.0.0", "gate-v1", 9900, 100, 25, 30, True, True)
    sources = _write(tmp_path / "sources.json", {"schema_version": "1.0.0", "sources": [{"source_id": "sec-company-facts", "licensed_or_public": True, "frozen_payload_hash": "a" * 64, "freshness_days": 2}]})
    evaluation = _write(tmp_path / "evaluation.json", {"automated_pass_rate_basis_points": 9950, "review_exception_rate_basis_points": 50, "correction_rate_basis_points": 10})
    policy_path = _write(tmp_path / "policy.json", policy.payload())
    reviewer = _write(tmp_path / "reviewer.json", {"reviewer_id": "reviewer", "approval_record_hash": "b" * 64})

    gate_research_task_release.main([
        "--fixtures-directory", str(ROOT / "fixtures" / "sec"),
        "--release-declaration", str(ROOT / "fixtures" / "sec" / "release_v1.json"),
        "--source-validations", str(sources), "--evaluation", str(evaluation),
        "--release-gate-policy", str(policy_path), "--lane", "lane_a",
        "--reviewer-approval", str(reviewer),
    ])
    record = json.loads(capsys.readouterr().out)
    assert record["approved"] is True
    assert record["lane"] == "lane_a"
    assert record["reviewer_approval_record_hash"] == "b" * 64
    assert len(record["manifest_hash"]) == 64


def test_release_gate_returns_nonzero_record_for_a_failed_gate(tmp_path: Path, capsys) -> None:
    policy = ReleaseGatePolicy("1.0.0", "gate-v1", 9900, 100, 25, 30, True, True)
    sources = _write(tmp_path / "sources.json", {"schema_version": "1.0.0", "sources": [{"source_id": "stale", "licensed_or_public": True, "frozen_payload_hash": "a" * 64, "freshness_days": 99}]})
    evaluation = _write(tmp_path / "evaluation.json", {"automated_pass_rate_basis_points": 9950, "review_exception_rate_basis_points": 50, "correction_rate_basis_points": 10})
    policy_path = _write(tmp_path / "policy.json", policy.payload())
    try:
        gate_research_task_release.main([
            "--fixtures-directory", str(ROOT / "fixtures" / "sec"),
            "--release-declaration", str(ROOT / "fixtures" / "sec" / "release_v1.json"),
            "--source-validations", str(sources), "--evaluation", str(evaluation),
            "--release-gate-policy", str(policy_path), "--lane", "lane_a",
        ])
    except SystemExit as error:
        assert error.code == 2
    else:  # pragma: no cover - makes the required fail-closed exit explicit.
        raise AssertionError("failed release gate unexpectedly succeeded")
    record = json.loads(capsys.readouterr().out)
    assert record["approved"] is False
    assert "source_stale" in record["reasons"]
