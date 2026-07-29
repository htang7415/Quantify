from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantify.evaluation import case_from_json, load_case_specs, run_cases
from tests.conftest import load_snapshot


PATH = Path(__file__).parents[2] / "fixtures" / "cases" / "judgment_v1.json"


def test_loads_and_runs_frozen_judgment_cases_separately() -> None:
    payload = json.loads(PATH.read_text())
    specs = load_case_specs(PATH)
    cases = tuple(
        case_from_json(
            item=item,
            snapshot=load_snapshot(
                item["snapshot_fixture"],
                allow_conflicting_evidence=item.get("allow_conflicting_evidence", False),
            ),
        )
        for item in payload["cases"]
    )

    assert len(specs) == 10
    assert {spec.category for spec in specs} == {"judgment"}
    assert {spec.resolution_status for spec in specs} == {"not_required"}
    assert all(spec.resolution_rationale for spec in specs)
    assert all(spec.resolved_at is None and spec.resolution_agent is None for spec in specs)
    assert all(case.expected_unclassified_statement_ids == ("s1",) for case in cases)
    assert run_cases(cases=cases) == run_cases(cases=tuple(reversed(cases)))


def test_agent_resolved_status_requires_versioned_provenance(tmp_path: Path) -> None:
    payload = json.loads(PATH.read_text())
    payload["cases"][0]["resolution_status"] = "agent_resolved"
    review_path = tmp_path / "judgment.json"
    review_path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="require date and agent version"):
        load_case_specs(review_path)

    payload["cases"][0]["resolved_at"] = "2026-07-28"
    payload["cases"][0]["resolution_agent"] = "fixture-resolution-agent-v1"
    review_path.write_text(json.dumps(payload))

    resolved = load_case_specs(review_path)[0]
    assert resolved.resolution_status == "agent_resolved"
    assert resolved.resolution_agent == "fixture-resolution-agent-v1"
