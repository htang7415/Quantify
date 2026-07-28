from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


FIXTURE_ROOT = Path(__file__).parents[3] / "fixtures" / "sec"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
RAW_COMPANY_FACTS = {
    "aapl_companyfacts.json": "0000320193",
    "msft_companyfacts.json": "0000789019",
}


def test_frozen_raw_company_facts_match_the_manifest() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = {entry["path"]: entry for entry in manifest["fixtures"]}

    for filename, expected_cik in RAW_COMPANY_FACTS.items():
        entry = entries[filename]
        payload = (FIXTURE_ROOT / filename).read_bytes()
        document = json.loads(payload)

        assert hashlib.sha256(payload).hexdigest() == entry["payload_sha256"]
        assert str(document["cik"]).zfill(10) == expected_cik == entry["cik"]
        assert entry["source_url"] == (
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{expected_cik}.json"
        )
        assert len(payload) > 1_000_000


@pytest.mark.parametrize("filename", RAW_COMPANY_FACTS)
def test_raw_company_facts_are_not_curated_evidence_fixtures(filename: str) -> None:
    document = json.loads((FIXTURE_ROOT / filename).read_bytes())

    assert "facts" in document
    assert "evidence" not in document
