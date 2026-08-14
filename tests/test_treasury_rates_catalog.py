import json
from pathlib import Path

import pytest

from scripts.build_treasury_rates_catalog import compile_catalog, parse_latest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/public_data/treasury_yield_curve_2026-08-13.xml"


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_treasury_release_preserves_exact_curve_and_derived_spread() -> None:
    catalog = compile_catalog(FIXTURE.read_bytes())
    curve = {point["maturity"]: point["yield_pct"] for point in catalog["curve"]}

    assert catalog["observed_at"] == "2026-08-13T00:00:00Z"
    assert curve["2Y"] == 4.15
    assert curve["10Y"] == 4.63
    assert curve["30Y"] == 5.21
    assert catalog["spreads"] == [{"name": "2s10s", "value_pp": 0.48, "derived_from": ["2Y", "10Y"]}]


def test_treasury_release_rejects_missing_required_maturity() -> None:
    payload = FIXTURE.read_text(encoding="utf-8").replace("<d:BC_10YEAR m:type=\"Edm.Double\">4.63</d:BC_10YEAR>", "")
    with pytest.raises(ValueError, match="not numeric"):
        parse_latest(payload.encode("utf-8"))


def test_treasury_release_rejects_nonofficial_source() -> None:
    with pytest.raises(ValueError, match="official host"):
        compile_catalog(FIXTURE.read_bytes(), "https://example.com/rates.xml")


def test_treasury_output_matches_the_compiler() -> None:
    assert load_json("web/src/data/treasuryRatesCatalog.json") == compile_catalog(FIXTURE.read_bytes())
