import json
from pathlib import Path

import pytest

from scripts.build_earnings_catalog import compile_catalog


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures/sec"
METADATA = ROOT / "scripts/earnings_company_metadata.json"


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_earnings_release_uses_same_accession_comparatives() -> None:
    catalog = compile_catalog(FIXTURES, METADATA)
    companies = {company["ticker"]: company for company in catalog["companies"]}

    assert companies["AAPL"]["accession"] == "0000320193-26-000013"
    assert companies["AAPL"]["revenue"]["value"] == 111_184_000_000
    assert companies["AAPL"]["revenue"]["yoy_change_pct"] == 16.6
    assert companies["AAPL"]["diluted_eps"]["value"] == 2.01
    assert companies["AAPL"]["diluted_eps"]["yoy_change_pct"] == 21.8
    assert companies["MSFT"]["revenue"]["value"] == 82_886_000_000
    assert companies["MSFT"]["revenue"]["yoy_change_pct"] == 18.3
    assert companies["MSFT"]["diluted_eps"]["yoy_change_pct"] == 23.4


def test_earnings_release_rejects_fixture_hash_mismatch(tmp_path: Path) -> None:
    copied = tmp_path / "sec"
    copied.mkdir()
    for source in FIXTURES.iterdir():
        if source.is_file():
            (copied / source.name).write_bytes(source.read_bytes())
    with (copied / "aapl_companyfacts.json").open("ab") as handle:
        handle.write(b" ")

    with pytest.raises(ValueError, match="hash mismatch"):
        compile_catalog(copied, METADATA)


def test_earnings_output_matches_compiler() -> None:
    assert load_json("web/src/data/earningsCatalog.json") == compile_catalog(FIXTURES, METADATA)
