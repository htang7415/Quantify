from __future__ import annotations

from decimal import Decimal

from quantify.engine import DisclosureAssessment, DisclosureStatus, MetricThresholdClaim, Relation, ReportSpan, ReviewReason, StatementClassification
from quantify.harness import ExtractedStatement, ExtractionResult, verify_report
from tests.conftest import load_snapshot


class FixtureDetector:
    def __init__(self, assessments): self.assessments, self.calls = assessments, []
    def assess(self, *, report_text, counterevidence_pairs, contexts):
        self.calls.append(counterevidence_pairs)
        return self.assessments


def _extraction() -> ExtractionResult:
    report = "Quantum revenue was under $415 million."
    return ExtractionResult(extractor_version="gold-v1", statements=(ExtractedStatement(
        "s1", StatementClassification.CLASSIFIED,
        ReportSpan("span", report, 0, len(report), report.rstrip("."), 0, len(report.rstrip("."))),
        (MetricThresholdClaim("qtm", "qtm-revenue-fy2023-as-filed", Relation.LESS_THAN, Decimal("415000000")),),
    ),))


def test_detector_receives_each_ce1_pair_and_ambiguous_routes_to_review() -> None:
    detector = FixtureDetector((DisclosureAssessment("qtm", "qtm-revenue-fy2023-restated", DisclosureStatus.AMBIGUOUS),))
    result = verify_report(report_text="Quantum revenue was under $415 million.", snapshot=load_snapshot("quantum_revenue_restatement.json", allow_conflicting_evidence=True), extraction=_extraction(), disclosure_detector=detector)
    assert len(detector.calls[0]) == 1
    assert result.review_items[0].reason is ReviewReason.DISCLOSURE_AMBIGUOUS


def test_missing_assessment_routes_to_review() -> None:
    result = verify_report(report_text="Quantum revenue was under $415 million.", snapshot=load_snapshot("quantum_revenue_restatement.json", allow_conflicting_evidence=True), extraction=_extraction())
    assert result.review_items[0].reason is ReviewReason.MISSING_DISCLOSURE_ASSESSMENT
