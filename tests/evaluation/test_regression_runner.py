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
from quantify.evaluation import RegressionCase, run_cases
from quantify.harness import ExtractedStatement, ExtractionResult
from tests.conftest import load_snapshot


def _extraction(report: str, claim) -> ExtractionResult:
    return ExtractionResult(
        extractor_version="gold-v1",
        statements=(
            ExtractedStatement(
                statement_id="s1",
                classification=StatementClassification.CLASSIFIED,
                report_span=ReportSpan(
                    span_id="span-s1", sentence_text=report, sentence_start=0,
                    sentence_end=len(report), claim_fragment=report.rstrip("."),
                    fragment_start=0, fragment_end=len(report.rstrip(".")),
                ),
                claims=(claim,),
            ),
        ),
    )


def test_runs_frozen_real_sec_cases_deterministically() -> None:
    msft_report = "Microsoft revenue increased from fiscal 2023 to fiscal 2024."
    quantum_report = "Quantum revenue was under $415 million."
    cases = (
        RegressionCase(
            case_id="mechanical-msft-revenue-growth-v1", category="mechanical",
            report_text=msft_report, snapshot=load_snapshot("msft_revenue_regression.json"),
            extraction=_extraction(msft_report, MetricComparisonClaim(
                claim_id="msft-growth", left_evidence_id="msft-revenue-fy2024",
                relation=Relation.GREATER_THAN, right_evidence_id="msft-revenue-fy2023",
            )), disclosure_assessments=(),
            expected_verdicts=(("msft-growth", ClaimVerdict.VERIFIED),),
        ),
        RegressionCase(
            case_id="mechanical-quantum-restatement-v1", category="mechanical",
            report_text=quantum_report,
            snapshot=load_snapshot("quantum_revenue_restatement.json", allow_conflicting_evidence=True),
            extraction=_extraction(quantum_report, MetricThresholdClaim(
                claim_id="qtm-under-415m", cited_evidence_id="qtm-revenue-fy2023-as-filed",
                relation=Relation.LESS_THAN, threshold=Decimal("415000000"),
            )),
            disclosure_assessments=(DisclosureAssessment(
                claim_id="qtm-under-415m", defeating_evidence_id="qtm-revenue-fy2023-restated",
                status=DisclosureStatus.NOT_DISCLOSED,
            ),),
            expected_verdicts=(("qtm-under-415m", ClaimVerdict.DEFEATED),),
        ),
    )

    assert run_cases(cases=cases) == run_cases(cases=tuple(reversed(cases)))
