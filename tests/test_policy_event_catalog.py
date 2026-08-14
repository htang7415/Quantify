import json
from pathlib import Path

import pytest

from scripts.build_policy_event_catalog import compile_catalog


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/public_data/policy_events_2026-08-13.json"


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_policy_release_preserves_exact_typed_actions() -> None:
    catalog = compile_catalog(FIXTURE.read_bytes())
    events = {event["event_id"]: event for event in catalog["events"]}
    fomc = events["fomc-2026-07-29-target-range"]["details"]
    sec = events["sec-2026-joint-data-standards"]
    bis = events["bis-2026-00789-advanced-computing"]["details"]

    assert (fomc["target_range_low_pct"], fomc["target_range_high_pct"]) == (3.5, 3.75)
    assert (fomc["next_meeting_start"], fomc["next_meeting_end"]) == ("2026-09-15", "2026-09-16")
    assert sec["effective_at"] == "2026-10-01"
    assert sec["details"]["reporting_requirements_change_at_effective_date"] is False
    assert bis["review_policy_after"] == "case_by_case_if_conditions_met"
    assert bis["related_company_tickers"] == ["NVDA", "AMD"]


def test_policy_release_rejects_nonofficial_source() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["events"][0]["source_url"] = "https://example.com/fomc"

    with pytest.raises(ValueError, match="source URL"):
        compile_catalog(json.dumps(payload).encode("utf-8"))


def test_policy_release_rejects_missing_export_condition() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["events"][2]["details"]["conditions"].pop()

    with pytest.raises(ValueError, match="conditions are incomplete"):
        compile_catalog(json.dumps(payload).encode("utf-8"))


def test_policy_output_matches_compiler() -> None:
    assert load_json("web/src/data/policyEventCatalog.json") == compile_catalog(FIXTURE.read_bytes())
