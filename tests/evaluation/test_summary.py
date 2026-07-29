from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantify.evaluation import case_from_json, summarize_cases
from tests.conftest import load_snapshot


CASE_ROOT = Path(__file__).parents[2] / "fixtures" / "cases"


def _load_cases(filename: str):
    payload = json.loads((CASE_ROOT / filename).read_text())
    return tuple(
        case_from_json(
            item=item,
            snapshot=load_snapshot(
                item["snapshot_fixture"],
                allow_conflicting_evidence=item.get("allow_conflicting_evidence", False),
            ),
        )
        for item in payload["cases"]
    )


def test_summaries_keep_mechanical_and_judgment_cases_separate() -> None:
    mechanical = summarize_cases(cases=_load_cases("mechanical_v1.json"))
    judgment = summarize_cases(cases=_load_cases("judgment_v1.json"))

    assert mechanical.category == "mechanical"
    assert mechanical.case_count == 20
    assert dict(mechanical.verdict_counts) == {
        "defeated": 1,
        "qualified": 1,
        "unsupported": 8,
        "verified": 10,
    }
    assert mechanical.unclassified_statement_count == 0
    assert judgment.category == "judgment"
    assert judgment.case_count == 10
    assert judgment.verdict_counts == ()
    assert judgment.unclassified_statement_count == 10


def test_summary_rejects_mixed_categories() -> None:
    with pytest.raises(ValueError, match="must not pool"):
        summarize_cases(
            cases=(
                _load_cases("mechanical_v1.json")[0],
                _load_cases("judgment_v1.json")[0],
            )
        )
