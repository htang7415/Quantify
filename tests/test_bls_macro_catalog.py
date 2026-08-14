import json
from pathlib import Path

import pytest

from scripts.build_bls_macro_catalog import compile_catalog


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/public_data/bls_macro_2026-07.json"


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_macro_release_calculates_exact_cpi_and_preserves_unemployment() -> None:
    catalog = compile_catalog(FIXTURE.read_bytes())
    metrics = {item["metric_id"]: item for item in catalog["observations"]}

    assert catalog["observed_period"] == "2026-07"
    assert metrics["headline_cpi_yoy"]["value_pct"] == 3.4
    assert metrics["headline_cpi_yoy"]["previous_value_pct"] == 3.5
    assert metrics["core_cpi_yoy"]["value_pct"] == 2.5
    assert metrics["unemployment_rate"]["value_pct"] == 4.1
    assert metrics["unemployment_rate"]["derivation"] == "published_value"


def test_macro_release_fails_closed_without_prior_year_cpi_input() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["series"][0]["data"] = [row for row in payload["series"][0]["data"] if not (row["year"] == "2025" and row["period"] == "M07")]

    with pytest.raises(ValueError, match="year-over-year inputs"):
        compile_catalog(json.dumps(payload).encode("utf-8"))


def test_macro_release_rejects_nonofficial_series_endpoint() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["series"][0]["source_url"] = "https://example.com/cpi"

    with pytest.raises(ValueError, match="official series endpoint"):
        compile_catalog(json.dumps(payload).encode("utf-8"))


def test_macro_release_ignores_bls_annual_and_missing_month_rows() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["series"][0]["data"].extend([
        {"year": "2025", "period": "M13", "periodName": "Annual", "value": "321.943"},
        {"year": "2025", "period": "M10", "periodName": "October", "value": "-"},
    ])

    assert compile_catalog(json.dumps(payload).encode("utf-8"))["observed_period"] == "2026-07"


def test_macro_output_matches_the_compiler() -> None:
    assert load_json("web/src/data/blsMacroCatalog.json") == compile_catalog(FIXTURE.read_bytes())
