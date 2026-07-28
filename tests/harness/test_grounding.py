from __future__ import annotations

from decimal import Decimal

from quantify.engine import MetricThresholdClaim, Relation, ReportSpan, ReviewReason
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
