from __future__ import annotations

from dataclasses import replace
from datetime import date

from quantify.engine import EvidenceEligibilityReason, evaluate_eligibility
from tests.conftest import load_snapshot


def test_returns_explicit_eligibility_reasons() -> None:
    baseline = load_snapshot("msft_revenue_regression.json").evidence[0]
    evidence = (
        baseline,
        replace(baseline, evidence_id="wrong-entity", entity_cik="0000320193"),
        replace(baseline, evidence_id="future", filed_at=date(2025, 1, 1)),
        replace(baseline, evidence_id="missing-unit", unit=""),
        replace(baseline, evidence_id="missing-provenance", accession=""),
        replace(baseline, evidence_id="bad-period", period_start=date(2024, 7, 1)),
        replace(baseline, evidence_id="failed-transformation", eligible=False),
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
        "missing-provenance": EvidenceEligibilityReason.MISSING_PROVENANCE,
        "bad-period": EvidenceEligibilityReason.PERIOD_ALIGNMENT_MISMATCH,
        "failed-transformation": EvidenceEligibilityReason.TRANSFORMATION_FAILURE,
    }


def test_rejects_custom_tags_duplicates_and_unresolved_restatements() -> None:
    baseline = load_snapshot("msft_revenue_regression.json").evidence[0]
    evidence = (
        baseline,
        replace(
            baseline,
            evidence_id="custom-tag",
            period_end=date(2022, 6, 30),
            is_standard_tag=False,
        ),
        replace(baseline, evidence_id="duplicate"),
        replace(
            baseline,
            evidence_id="restated",
            accession="0000789019-25-000001",
            filed_at=date(2025, 1, 1),
            value=baseline.value + 1,
        ),
    )

    decisions = {
        item.evidence_id: item.reason
        for item in evaluate_eligibility(
            evidence=evidence, expected_cik="0000789019", as_of_date=date(2025, 1, 1)
        )
    }

    assert decisions == {
        "custom-tag": EvidenceEligibilityReason.CUSTOM_TAG_UNSUPPORTED,
        "duplicate": EvidenceEligibilityReason.UNRESOLVED_RESTATEMENT,
        "msft-revenue-fy2023": EvidenceEligibilityReason.UNRESOLVED_RESTATEMENT,
        "restated": EvidenceEligibilityReason.UNRESOLVED_RESTATEMENT,
    }


def test_marks_identical_semantic_facts_as_duplicates() -> None:
    baseline = load_snapshot("msft_revenue_regression.json").evidence[0]
    decisions = {
        item.evidence_id: item.reason
        for item in evaluate_eligibility(
            evidence=(baseline, replace(baseline, evidence_id="duplicate")),
            expected_cik="0000789019",
            as_of_date=date(2024, 7, 30),
        )
    }

    assert decisions == {
        "duplicate": EvidenceEligibilityReason.DUPLICATE_FACT,
        "msft-revenue-fy2023": EvidenceEligibilityReason.DUPLICATE_FACT,
    }
