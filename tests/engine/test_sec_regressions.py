from __future__ import annotations

from quantify.engine import (
    MetricComparisonClaim,
    Relation,
    VerificationOutcome,
    analyze_claims,
    verify_claim,
)
from tests.conftest import load_snapshot


def test_microsoft_fy2024_revenue_exceeded_fy2023() -> None:
    snapshot = load_snapshot("msft_revenue_regression.json")
    result = verify_claim(
        snapshot=snapshot,
        claim=MetricComparisonClaim(
            claim_id="msft-fy2024-revenue-increased",
            left_evidence_id="msft-revenue-fy2024",
            relation=Relation.GREATER_THAN,
            right_evidence_id="msft-revenue-fy2023",
        ),
    )

    assert result.outcome is VerificationOutcome.VERIFIED


def test_apple_fy2024_revenue_exceeded_fy2023() -> None:
    snapshot = load_snapshot("aapl_revenue_regression.json")
    claim = MetricComparisonClaim(
        claim_id="aapl-fy2024-revenue-increased",
        left_evidence_id="aapl-revenue-fy2024",
        relation=Relation.GREATER_THAN,
        right_evidence_id="aapl-revenue-fy2023",
    )

    assert verify_claim(snapshot=snapshot, claim=claim).outcome is VerificationOutcome.VERIFIED
    assert analyze_claims(snapshot=snapshot, claims=(claim,)).counterevidence_pairs == ()
