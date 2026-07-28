from __future__ import annotations
from quantify.harness import EvidenceRequestType, assess_coverage
from tests.conftest import load_snapshot

def test_revenue_only_snapshot_requests_only_closed_missing_families() -> None:
    requests = assess_coverage(snapshot=load_snapshot("msft_revenue_regression.json"))
    assert requests == (EvidenceRequestType.PROFITABILITY_METRICS, EvidenceRequestType.CASH_FLOW_METRICS, EvidenceRequestType.BALANCE_SHEET_METRICS, EvidenceRequestType.DILUTION_METRICS)
