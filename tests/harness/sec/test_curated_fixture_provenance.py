from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from quantify.engine import RestatementPolicy, SourceType, freeze_selected_snapshot
from quantify.harness.sec import normalize_company_facts
from tests.conftest import load_snapshot


FIXTURE_ROOT = Path(__file__).parents[3] / "fixtures" / "sec"
MSFT_SOURCE_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json"


def test_curated_microsoft_fundamentals_are_selected_from_the_frozen_raw_payload() -> None:
    raw = json.loads((FIXTURE_ROOT / "msft_companyfacts.json").read_bytes())
    normalized = normalize_company_facts(
        company_facts=raw,
        source_url=MSFT_SOURCE_URL,
    )
    raw_snapshot, _ = freeze_selected_snapshot(
        snapshot_id="msft-raw-fy2024",
        evidence=normalized,
        policy=RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
        as_of_date=date(2024, 7, 30),
        source_type=SourceType.SEC_COMPANY_FACTS,
    )
    curated = load_snapshot("msft_fundamentals_regression.json")

    raw_facts = {
        (
            item.entity_cik,
            item.metric,
            item.value,
            item.unit,
            item.period_start,
            item.period_end,
            item.accession,
            item.filed_at,
        )
        for item in raw_snapshot.evidence
    }
    curated_facts = {
        (
            item.entity_cik,
            item.metric,
            item.value,
            item.unit,
            item.period_start,
            item.period_end,
            item.accession,
            item.filed_at,
        )
        for item in curated.evidence
    }

    assert curated_facts <= raw_facts
    assert len(curated_facts) == 15
