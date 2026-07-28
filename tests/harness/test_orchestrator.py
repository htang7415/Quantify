from __future__ import annotations

from decimal import Decimal

from quantify.engine import (
    ClaimVerdict,
    DisclosureAssessment,
    DisclosureStatus,
    MetricComparisonClaim,
    MetricThresholdClaim,
    Relation,
    ReportSpan,
    StatementClassification,
)
from quantify.harness import ExtractedStatement, ExtractionResult, verify_report
from tests.conftest import load_snapshot


def test_verifies_a_grounded_microsoft_report_end_to_end() -> None:
    report_text = "Microsoft revenue increased from fiscal 2023 to fiscal 2024."
    extraction = ExtractionResult(
        extractor_version="fixture-v1",
        statements=(
            ExtractedStatement(
                statement_id="s1",
                classification=StatementClassification.CLASSIFIED,
                report_span=ReportSpan(
                    span_id="span-s1",
                    sentence_text=report_text,
                    sentence_start=0,
                    sentence_end=len(report_text),
                    claim_fragment="Microsoft revenue increased",
                    fragment_start=0,
                    fragment_end=len("Microsoft revenue increased"),
                ),
                claims=(
                    MetricComparisonClaim(
                        claim_id="msft-revenue-growth",
                        left_evidence_id="msft-revenue-fy2024",
                        relation=Relation.GREATER_THAN,
                        right_evidence_id="msft-revenue-fy2023",
                    ),
                ),
            ),
        ),
    )

    result = verify_report(
        report_text=report_text,
        snapshot=load_snapshot("msft_revenue_regression.json"),
        extraction=extraction,
    )

    assert result.claim_verdicts[0].verdict is ClaimVerdict.VERIFIED
    assert result.review_items == ()
    assert result.material_omissions == ()


def test_marks_a_real_undisclosed_restatement_as_defeated_end_to_end() -> None:
    report_text = "Quantum revenue was under $415 million."
    extraction = ExtractionResult(
        extractor_version="fixture-v1",
        statements=(
            ExtractedStatement(
                statement_id="s1",
                classification=StatementClassification.CLASSIFIED,
                report_span=ReportSpan(
                    span_id="span-s1",
                    sentence_text=report_text,
                    sentence_start=0,
                    sentence_end=len(report_text),
                    claim_fragment="Quantum revenue was under $415 million",
                    fragment_start=0,
                    fragment_end=len("Quantum revenue was under $415 million"),
                ),
                claims=(
                    MetricThresholdClaim(
                        claim_id="qtm-under-415m",
                        cited_evidence_id="qtm-revenue-fy2023-as-filed",
                        relation=Relation.LESS_THAN,
                        threshold=Decimal("415000000"),
                    ),
                ),
            ),
        ),
    )

    result = verify_report(
        report_text=report_text,
        snapshot=load_snapshot(
            "quantum_revenue_restatement.json", allow_conflicting_evidence=True
        ),
        extraction=extraction,
        disclosure_assessments=(
            DisclosureAssessment(
                claim_id="qtm-under-415m",
                defeating_evidence_id="qtm-revenue-fy2023-restated",
                status=DisclosureStatus.NOT_DISCLOSED,
            ),
        ),
    )

    assert result.claim_verdicts[0].verdict is ClaimVerdict.DEFEATED
    assert result.material_omissions[0].evidence_id == "qtm-revenue-fy2023-restated"
