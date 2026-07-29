from __future__ import annotations
import pytest

from quantify.harness import (
    EvidenceRequestType,
    approve_acquisition_requests,
    assess_coverage,
)
from tests.conftest import load_snapshot


def test_revenue_only_snapshot_requests_only_closed_missing_families() -> None:
    requests = assess_coverage(snapshot=load_snapshot("msft_revenue_regression.json"))
    assert requests == (
        EvidenceRequestType.PRIOR_QUARTER,
        EvidenceRequestType.PROFITABILITY_METRICS,
        EvidenceRequestType.CASH_FLOW_METRICS,
        EvidenceRequestType.BALANCE_SHEET_METRICS,
        EvidenceRequestType.DILUTION_METRICS,
    )


def test_approves_only_unmet_unique_requests_in_canonical_order() -> None:
    records = approve_acquisition_requests(
        snapshot=load_snapshot("msft_revenue_regression.json"),
        requested=(
            EvidenceRequestType.DILUTION_METRICS,
            EvidenceRequestType.PROFITABILITY_METRICS,
        ),
    )

    assert [record.request_type for record in records] == [
        EvidenceRequestType.DILUTION_METRICS,
        EvidenceRequestType.PROFITABILITY_METRICS,
    ]
    assert all(record.reason.startswith("deterministic coverage gap") for record in records)


def test_rejects_unbounded_duplicate_or_irrelevant_acquisition_requests() -> None:
    snapshot = load_snapshot("msft_revenue_regression.json")

    with pytest.raises(ValueError, match="two-round"):
        approve_acquisition_requests(
            snapshot=snapshot,
            requested=(
                EvidenceRequestType.PRIOR_QUARTER,
                EvidenceRequestType.PROFITABILITY_METRICS,
                EvidenceRequestType.CASH_FLOW_METRICS,
            ),
        )
    with pytest.raises(ValueError, match="unique"):
        approve_acquisition_requests(
            snapshot=snapshot,
            requested=(
                EvidenceRequestType.PROFITABILITY_METRICS,
                EvidenceRequestType.PROFITABILITY_METRICS,
            ),
        )
    with pytest.raises(ValueError, match="coverage gap"):
        approve_acquisition_requests(
            snapshot=snapshot,
            requested=(EvidenceRequestType.PRIOR_ANNUAL_PERIOD,),
        )
