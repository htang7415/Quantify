from __future__ import annotations

from quantify.engine import MetricComparisonClaim, Relation, ReportSpan, StatementClassification
from quantify.harness import ExtractedStatement, ExtractionResult, verify_report
from tests.conftest import load_snapshot


def _verify(report_text: str, fragment_start: int) -> tuple[str, ...]:
    fragment = "Microsoft revenue increased from fiscal 2023 to fiscal 2024"
    extraction = ExtractionResult(
        extractor_version="gold-v1",
        statements=(
            ExtractedStatement(
                statement_id="growth",
                classification=StatementClassification.CLASSIFIED,
                report_span=ReportSpan(
                    span_id="growth-span",
                    sentence_text=report_text[fragment_start : fragment_start + len(fragment) + 1],
                    sentence_start=fragment_start,
                    sentence_end=fragment_start + len(fragment) + 1,
                    claim_fragment=fragment,
                    fragment_start=fragment_start,
                    fragment_end=fragment_start + len(fragment),
                ),
                claims=(MetricComparisonClaim(
                    claim_id="msft-growth",
                    left_evidence_id="msft-revenue-fy2024",
                    relation=Relation.GREATER_THAN,
                    right_evidence_id="msft-revenue-fy2023",
                ),),
            ),
        ),
    )
    result = verify_report(
        report_text=report_text,
        snapshot=load_snapshot("msft_revenue_regression.json"),
        extraction=extraction,
    )
    return tuple(item.verdict.value for item in result.claim_verdicts)


def test_whitespace_and_punctuation_preserve_mechanical_verdict() -> None:
    base = "Microsoft revenue increased from fiscal 2023 to fiscal 2024."
    whitespace = "Microsoft revenue increased from fiscal 2023 to fiscal 2024.\n"

    assert _verify(base, 0) == ("verified",)
    assert _verify(whitespace, 0) == ("verified",)


def test_sentence_reordering_preserves_matched_statement_verdict() -> None:
    reordered = "This is an introductory sentence. Microsoft revenue increased from fiscal 2023 to fiscal 2024."
    assert _verify(reordered, len("This is an introductory sentence. ")) == ("verified",)


def test_minor_synonym_change_cannot_create_a_false_omission_or_flip() -> None:
    report = "Microsoft revenue rose from fiscal 2023 to fiscal 2024."
    fragment = "Microsoft revenue rose from fiscal 2023 to fiscal 2024"
    extraction = ExtractionResult(
        extractor_version="gold-v1",
        statements=(ExtractedStatement(
            statement_id="growth", classification=StatementClassification.CLASSIFIED,
            report_span=ReportSpan("growth-span", report, 0, len(report), fragment, 0, len(fragment)),
            claims=(MetricComparisonClaim(
                claim_id="msft-growth", left_evidence_id="msft-revenue-fy2024",
                relation=Relation.GREATER_THAN, right_evidence_id="msft-revenue-fy2023",
            ),),
        ),),
    )

    result = verify_report(
        report_text=report, snapshot=load_snapshot("msft_revenue_regression.json"), extraction=extraction
    )
    assert tuple(item.verdict.value for item in result.claim_verdicts) == ("verified",)
    assert result.material_omissions == ()
