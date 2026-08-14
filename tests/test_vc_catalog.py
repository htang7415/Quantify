import copy
import json
from pathlib import Path

import pytest

from scripts.build_vc_catalog import compile_catalog


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/public_data/vc_portfolio_sources_2026-08-13.json"
CANDIDATE_SOURCE = ROOT / "tests/fixtures/public_data/vc_portfolio_sources_candidate_2026-08-14.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compile_source(value: dict) -> tuple[dict, dict]:
    return compile_catalog(json.dumps(value, separators=(",", ":")).encode())


def test_vc_pilot_is_deterministic_and_bounded() -> None:
    first_catalog, first_record = compile_catalog(SOURCE.read_bytes())
    second_catalog, second_record = compile_catalog(SOURCE.read_bytes())

    assert first_catalog == second_catalog
    assert first_record == second_record
    assert first_catalog["schema_version"] == "vc-catalog.v1"
    assert first_catalog["release_id"].startswith("vc-2026-08-14-")
    assert len(first_catalog["firms"]) == 4
    assert sum(firm["tracked_relationship_count"] for firm in first_catalog["firms"]) == 24
    assert first_record["publication_authorized"] is False
    assert first_record["firm_count"] == 4
    assert first_record["relationship_count"] == 24


def test_vc_pilot_preserves_disclosed_years_and_explicit_unknowns() -> None:
    catalog, _ = compile_catalog(SOURCE.read_bytes())
    firms = {firm["firm_id"]: firm for firm in catalog["firms"]}
    khosla = {row["company_id"]: row for row in firms["khosla-ventures"]["relationships"]}

    assert khosla["openai"]["first_partnered_year"] == 2019
    assert khosla["waabi"]["first_partnered_year"] == 2021
    assert all(row["stage"] == "undisclosed" for firm in catalog["firms"] for row in firm["relationships"])
    assert all(row["participation_role"] == "undisclosed" for firm in catalog["firms"] for row in firm["relationships"])
    assert all(row["follow_on_status"] == "undisclosed" for firm in catalog["firms"] for row in firm["relationships"])


def test_vc_contract_excludes_13f_and_invented_precision_fields() -> None:
    catalog, _ = compile_catalog(SOURCE.read_bytes())
    forbidden = {"aum", "ownership_pct", "position_value", "value_usd", "weight_pct", "valuation", "return", "shares"}

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value).union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    assert not forbidden.intersection(keys(catalog))


def test_vc_source_rejects_extra_fields_duplicate_relationships_and_wrong_hosts() -> None:
    source = load(SOURCE)
    extra = copy.deepcopy(source)
    extra["firms"][0]["relationships"][0]["ownership_pct"] = 10
    with pytest.raises(ValueError, match="relationship fields"):
        compile_source(extra)

    duplicate = copy.deepcopy(source)
    duplicate["firms"][0]["relationships"].append(copy.deepcopy(duplicate["firms"][0]["relationships"][0]))
    with pytest.raises(ValueError, match="duplicate company"):
        compile_source(duplicate)

    wrong_host = copy.deepcopy(source)
    wrong_host["firms"][0]["relationships"][0]["source_url"] = "https://a16z.com/portfolio/"
    with pytest.raises(ValueError, match="source URL"):
        compile_source(wrong_host)


def test_vc_source_rejects_cross_firm_identity_conflicts_and_future_years() -> None:
    source = load(SOURCE)
    conflict = copy.deepcopy(source)
    conflict["firms"][1]["relationships"][0]["sector"] = "space"
    with pytest.raises(ValueError, match="conflicts across firms"):
        compile_source(conflict)

    future = copy.deepcopy(source)
    future["firms"][3]["relationships"][0]["first_partnered_year"] = 2027
    with pytest.raises(ValueError, match="first-partnered year"):
        compile_source(future)


def test_checked_in_vc_outputs_match_the_compiler() -> None:
    catalog, record = compile_catalog(SOURCE.read_bytes())
    assert load(ROOT / "web/src/data/vcCatalog.json") == catalog
    assert load(ROOT / "web/src/data/vcCompilationRecord.json") == record


def test_six_firm_candidate_is_compiled_but_never_authorized() -> None:
    catalog, record = compile_catalog(CANDIDATE_SOURCE.read_bytes())

    assert len(catalog["firms"]) == 6
    assert sum(firm["tracked_relationship_count"] for firm in catalog["firms"]) == 36
    assert {firm["firm_id"] for firm in catalog["firms"]} >= {"thrive-capital", "general-catalyst"}
    assert record["publication_authorized"] is False
    thrive = next(firm for firm in catalog["firms"] if firm["firm_id"] == "thrive-capital")
    assert all(relationship["stage"] == "undisclosed" for relationship in thrive["relationships"])
    assert "six venture firms" in catalog["limitations"][0]
