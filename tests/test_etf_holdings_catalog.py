import copy
import json
from pathlib import Path

import pytest

from scripts.build_etf_holdings_catalog import compile_catalog


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/public_data/etf_holdings_2026q2.json"
FLOW = ROOT / "web/src/data/etfFlowCatalog.json"
METADATA = ROOT / "scripts/investor_security_metadata.json"


def inputs() -> tuple[dict, dict, dict]:
    return tuple(
        json.loads(path.read_text(encoding="utf-8"))
        for path in (SOURCE, FLOW, METADATA)
    )


def test_etf_holdings_release_preserves_exact_ranked_rows_and_scope() -> None:
    catalog = compile_catalog(*inputs())
    funds = {fund["ticker"]: fund for fund in catalog["funds"]}
    vgt = funds["VGT"]

    assert catalog["schema_version"] == "etf-holdings-catalog.v1"
    assert catalog["flow_release_id"].startswith("etf-flows-")
    assert set(funds) == {"VGT", "QQQ", "SMH"}
    assert vgt["report_date"] == "2026-02-28"
    assert vgt["total_holding_rows"] == 324
    assert vgt["published_holding_rows"] == 10
    assert vgt["top_ten_concentration_pct"] == pytest.approx(57.369031484468)
    assert vgt["holdings"][0]["ticker"] == "NVDA"
    assert vgt["holdings"][0]["currency_value"] == pytest.approx(22_242_584_685.49)
    assert vgt["holdings"][0]["filed_percentage"] == pytest.approx(17.27100788286)


def test_etf_holdings_release_leaves_missing_ticker_mappings_null() -> None:
    catalog = compile_catalog(*inputs())
    vgt = next(fund for fund in catalog["funds"] if fund["ticker"] == "VGT")
    amd = next(holding for holding in vgt["holdings"] if holding["cusip"] == "007903107")

    assert amd["issuer_name"] == "Advanced Micro Devices Inc"
    assert amd["ticker"] is None
    assert amd["theme"] is None


def test_etf_holdings_release_rejects_flow_identity_mismatch() -> None:
    source, flow, metadata = inputs()
    source["funds"][0]["report_date"] = "2026-03-31"
    with pytest.raises(ValueError, match="identity does not match"):
        compile_catalog(source, flow, metadata)


def test_etf_holdings_release_rejects_reordered_percentages() -> None:
    source, flow, metadata = inputs()
    source["funds"][0]["holdings"][0], source["funds"][0]["holdings"][1] = (
        source["funds"][0]["holdings"][1],
        source["funds"][0]["holdings"][0],
    )
    with pytest.raises(ValueError, match="ordered by filed percentage"):
        compile_catalog(source, flow, metadata)


def test_etf_holdings_release_rejects_unapproved_ticker() -> None:
    source, flow, metadata = inputs()
    source["funds"][0]["ticker"] = "XYZ"
    with pytest.raises(ValueError, match="unsupported or missing ticker"):
        compile_catalog(source, flow, metadata)


def test_etf_holdings_output_matches_compiler() -> None:
    output = json.loads((ROOT / "web/src/data/etfHoldingsCatalog.json").read_text(encoding="utf-8"))
    source, flow, metadata = inputs()
    assert output == compile_catalog(copy.deepcopy(source), copy.deepcopy(flow), copy.deepcopy(metadata))
