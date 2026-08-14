import copy
import json
from pathlib import Path

import pytest

from scripts.build_etf_flow_catalog import compile_catalog


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/public_data/etf_flows_2026-03-31.json"


def source() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_etf_flow_release_uses_exact_item_b6_arithmetic() -> None:
    catalog = compile_catalog(source())
    funds = {fund["ticker"]: fund for fund in catalog["funds"]}

    assert catalog["schema_version"] == "etf-flow-catalog.v2"
    assert catalog["observed_through"] == "2026-03-31"
    assert funds["SMH"]["monthly_flows"][0]["net_flow_usd"] == pytest.approx(2_262_671_883)
    assert funds["IWM"]["monthly_flows"][2]["net_flow_usd"] == pytest.approx(1_760_073_523.2)
    assert funds["QQQ"]["three_month_net_flow_usd"] == pytest.approx(-12_727_471_540.92)
    assert funds["VGT"]["report_date"] == "2026-02-28"
    assert funds["VGT"]["months"] == ["2025-12", "2026-01", "2026-02"]
    assert funds["VGT"]["three_month_net_flow_usd"] == pytest.approx(3_436_187_734.9)


def test_etf_flow_release_preserves_inputs_separately_from_net_assets() -> None:
    catalog = compile_catalog(source())
    spy = next(fund for fund in catalog["funds"] if fund["ticker"] == "SPY")

    assert spy["net_assets_usd"] == pytest.approx(651_588_269_947.59)
    assert spy["monthly_flows"][0] == {
        "month": "2026-01",
        "sales_nav_usd": pytest.approx(70_186_858_179.8),
        "reinvestment_nav_usd": 0.0,
        "redemption_nav_usd": pytest.approx(83_459_621_316),
        "net_flow_usd": pytest.approx(-13_272_763_136.2),
    }


def test_etf_flow_release_rejects_nonofficial_source() -> None:
    value = source()
    value["dataset_url"] = "https://example.com/nport.zip"
    with pytest.raises(ValueError, match="official SEC host"):
        compile_catalog(value)


def test_etf_flow_release_rejects_missing_monthly_input() -> None:
    value = source()
    del value["funds"][0]["monthly_inputs"][0]["sales_nav_usd"]
    with pytest.raises(ValueError, match="preserve the exact filed decimal string"):
        compile_catalog(value)


def test_etf_flow_release_rejects_months_that_do_not_match_fund_report_date() -> None:
    value = source()
    value["funds"][0]["months"] = ["2025-12", "2026-01", "2026-02"]
    with pytest.raises(ValueError, match="fund months must be the three report-date months"):
        compile_catalog(value)


def test_etf_flow_release_rejects_report_date_after_observation_boundary() -> None:
    value = source()
    value["funds"][0]["report_date"] = "2026-04-30"
    with pytest.raises(ValueError, match="cannot exceed observed_through"):
        compile_catalog(value)


def test_etf_flow_release_rejects_unapproved_ticker() -> None:
    value = source()
    value["funds"][0]["ticker"] = "XYZ"
    with pytest.raises(ValueError, match="unsupported or missing ticker"):
        compile_catalog(value)


def test_etf_flow_output_matches_compiler() -> None:
    output = json.loads((ROOT / "web/src/data/etfFlowCatalog.json").read_text(encoding="utf-8"))
    assert output == compile_catalog(copy.deepcopy(source()))
