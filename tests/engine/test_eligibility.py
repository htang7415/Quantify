from __future__ import annotations

from dataclasses import replace
from datetime import date

from quantify.engine import EvidenceEligibilityReason, evaluate_eligibility
from tests.conftest import load_snapshot


def test_returns_explicit_eligibility_reasons() -> None:
    baseline = load_snapshot("msft_companyfacts.json").evidence[0]
    evidence = (
        baseline,
        replace(baseline, evidence_id="wrong-entity", entity_cik="0000320193"),
        replace(baseline, evidence_id="future", filed_at=date(2025, 1, 1)),
        replace(baseline, evidence_id="missing-unit", unit=""),
        replace(baseline, evidence_id="bad-period", period_start=date(2024, 7, 1)),
    )

    decisions = {
        item.evidence_id: item.reason
        for item in evaluate_eligibility(
            evidence=evidence, expected_cik="0000789019", as_of_date=date(2024, 7, 30)
        )
    }

    assert decisions == {
        "msft-revenue-fy2023": EvidenceEligibilityReason.ELIGIBLE,
        "wrong-entity": EvidenceEligibilityReason.ENTITY_SCOPE_MISMATCH,
        "future": EvidenceEligibilityReason.FUTURE_FILING,
        "missing-unit": EvidenceEligibilityReason.UNIT_MISMATCH,
        "bad-period": EvidenceEligibilityReason.PERIOD_ALIGNMENT_MISMATCH,
    }
