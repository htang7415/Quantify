"""Versioned, network-free regression execution for frozen evidence cases."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from quantify.engine import ClaimVerdict, DisclosureAssessment, EvidenceSnapshot
from quantify.harness import ExtractionResult, verify_report


@dataclass(frozen=True, slots=True)
class RegressionCase:
    case_id: str
    category: str
    report_text: str
    snapshot: EvidenceSnapshot
    extraction: ExtractionResult
    disclosure_assessments: tuple[DisclosureAssessment, ...]
    expected_verdicts: tuple[tuple[str, ClaimVerdict], ...]
    expected_unclassified_statement_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    """Deterministic, category-separated result for one frozen case set."""

    category: str
    case_count: int
    verdict_counts: tuple[tuple[str, int], ...]
    unclassified_statement_count: int


def run_cases(*, cases: tuple[RegressionCase, ...]) -> tuple[tuple[str, tuple], ...]:
    """Run cases in canonical order and fail on any verdict-set mismatch."""

    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("regression case IDs must be unique")
    results: list[tuple[str, tuple]] = []
    for case in sorted(cases, key=lambda item: item.case_id):
        report = verify_report(
            report_text=case.report_text,
            snapshot=case.snapshot,
            extraction=case.extraction,
            disclosure_assessments=case.disclosure_assessments,
        )
        actual = tuple((item.claim_id, item.verdict) for item in report.claim_verdicts)
        if actual != case.expected_verdicts:
            raise AssertionError(
                f"{case.case_id}: expected {case.expected_verdicts}, got {actual}"
            )
        if report.unclassified_statement_ids != case.expected_unclassified_statement_ids:
            raise AssertionError(
                f"{case.case_id}: expected unclassified "
                f"{case.expected_unclassified_statement_ids}, got "
                f"{report.unclassified_statement_ids}"
            )
        results.append((case.case_id, actual))
    return tuple(results)


def summarize_cases(*, cases: tuple[RegressionCase, ...]) -> EvaluationSummary:
    """Run one homogeneous case set and return only deterministic aggregates."""

    if not cases:
        raise ValueError("cannot summarize an empty case set")
    categories = {case.category for case in cases}
    if len(categories) != 1:
        raise ValueError("evaluation summaries must not pool categories")

    results = run_cases(cases=cases)
    verdicts = Counter(
        verdict.value
        for _, case_results in results
        for _, verdict in case_results
    )
    return EvaluationSummary(
        category=next(iter(categories)),
        case_count=len(cases),
        verdict_counts=tuple(sorted(verdicts.items())),
        unclassified_statement_count=sum(
            len(case.expected_unclassified_statement_ids) for case in cases
        ),
    )
