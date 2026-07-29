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
    assert {spec.reviewer_status for spec in specs} == {"not_required"}
    assert all(spec.reviewer_rationale for spec in specs)
    assert all(spec.reviewed_at is None and spec.reviewer_role is None for spec in specs)
    assert all(case.expected_unclassified_statement_ids == ("s1",) for case in cases)
    assert run_cases(cases=cases) == run_cases(cases=tuple(reversed(cases)))


def test_finance_reviewed_status_requires_anonymous_provenance(tmp_path: Path) -> None:
    payload = json.loads(PATH.read_text())
    payload["cases"][0]["reviewer_status"] = "finance_reviewed"
    review_path = tmp_path / "judgment.json"
    review_path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="require date and reviewer role"):
        load_case_specs(review_path)

    payload["cases"][0]["reviewed_at"] = "2026-07-28"
    payload["cases"][0]["reviewer_role"] = "finance_literate_reviewer"
    review_path.write_text(json.dumps(payload))

    reviewed = load_case_specs(review_path)[0]
    assert reviewed.reviewer_status == "finance_reviewed"
    assert reviewed.reviewer_role == "finance_literate_reviewer"
