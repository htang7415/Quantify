from __future__ import annotations

from decimal import Decimal

from datetime import date

from quantify.engine import (
    MetricBaselineClaim,
    MetricThresholdClaim,
    Relation,
    ReportSpan,
    ReviewReason,
    build_upper_baseline_calibration,
)
from quantify.harness import validate_claim_references, validate_report_span
from tests.conftest import load_snapshot


def test_validates_exact_report_span() -> None:
    report = "Revenue increased from the prior year."
    span = ReportSpan(
        span_id="s1",
        sentence_text=report,
        sentence_start=0,
        sentence_end=len(report),
        claim_fragment="Revenue increased",
        fragment_start=0,
        fragment_end=len("Revenue increased"),
    )

    assert validate_report_span(report_text=report, span=span) is None


def test_routes_partial_contrastive_sentence_to_review() -> None:
    report = "Revenue increased; however, operating income declined."
    span = ReportSpan(
        span_id="s1",
        sentence_text=report,
        sentence_start=0,
        sentence_end=len(report),
        claim_fragment="Revenue increased",
        fragment_start=0,
        fragment_end=len("Revenue increased"),
    )

    review = validate_report_span(report_text=report, span=span)

    assert review is not None
    assert review.reason is ReviewReason.PARTIAL_CONTRASTIVE_EXTRACTION


def test_routes_missing_evidence_reference_to_review() -> None:
    review = validate_claim_references(
        snapshot=load_snapshot("msft_revenue_regression.json"),
        claim=MetricThresholdClaim(
            claim_id="unknown-evidence",
            cited_evidence_id="not-in-snapshot",
            relation=Relation.GREATER_THAN,
            threshold=Decimal("0"),
        ),
    )

    assert review is not None
    assert review.reason is ReviewReason.INVALID_EVIDENCE_REFERENCE


def test_routes_missing_baseline_history_to_review() -> None:
    snapshot = load_snapshot("msft_revenue_regression.json")
    calibration = build_upper_baseline_calibration(
        snapshot=snapshot,
        historical_evidence_ids=("msft-revenue-fy2023", "msft-revenue-fy2024"),
        historical_cutoff=date(2024, 6, 30),
    )
    claim = MetricBaselineClaim(
        claim_id="missing-baseline-history",
        cited_evidence_id="msft-revenue-fy2024",
        relation=Relation.OUTSIDE_UPPER_BASELINE,
        calibration=calibration,
    )

    # The stored calibration is deliberately tampered only after construction,
    # so grounding—not calibration construction—must catch the unknown ID.
    from dataclasses import replace

    review = validate_claim_references(
        snapshot=snapshot,
        claim=replace(
            claim,
            calibration=replace(
                calibration,
                historical_evidence_ids=("missing", "msft-revenue-fy2023"),
            ),
        ),
    )

    assert review is not None
    assert review.reason is ReviewReason.INVALID_EVIDENCE_REFERENCE
