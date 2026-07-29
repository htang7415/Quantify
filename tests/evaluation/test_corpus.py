from __future__ import annotations

import json
from pathlib import Path

from quantify.evaluation import case_from_json, load_case_specs, run_cases
from tests.conftest import load_snapshot


PATH = Path(__file__).parents[2] / "fixtures" / "cases" / "mechanical_v1.json"


def test_loads_and_runs_versioned_frozen_mechanical_cases() -> None:
    payload = json.loads(PATH.read_text())
    specs = load_case_specs(PATH)
    cases = tuple(
        case_from_json(
            item=item,
            snapshot=load_snapshot(item["snapshot_fixture"], allow_conflicting_evidence=item.get("allow_conflicting_evidence", False)),
        )
        for item in payload["cases"]
    )

    assert [spec.case_id for spec in specs] == [case.case_id for case in cases]
    assert len(specs) == 20
    assert {spec.category for spec in specs} == {"mechanical"}
    assert run_cases(cases=cases) == run_cases(cases=tuple(reversed(cases)))
