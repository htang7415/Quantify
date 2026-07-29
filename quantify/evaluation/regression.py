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


@dataclass(frozen=True, slots=True)
class FalsePositiveAnalysis:
    """Category-specific count of unsupported omission accusations."""

    category: str
    case_count: int
    false_positive_defeats: tuple[tuple[str, str], ...]

    @property
    def false_positive_rate(self) -> float:
        return len(self.false_positive_defeats) / self.case_count


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


def analyze_false_positives(*, cases: tuple[RegressionCase, ...]) -> FalsePositiveAnalysis:
    """Report DEFEATED claims that are not defeated in frozen reference answers.

    A mechanical false positive is especially serious because it would create a
    material-omission accusation without support from the frozen reference
    case. Categories are deliberately not pooled.
    """

    if not cases:
        raise ValueError("cannot analyze an empty case set")
    categories = {case.category for case in cases}
    if len(categories) != 1:
        raise ValueError("false-positive analysis must not pool categories")
    false_positives: list[tuple[str, str]] = []
    for case in sorted(cases, key=lambda item: item.case_id):
        report = verify_report(
            report_text=case.report_text,
            snapshot=case.snapshot,
            extraction=case.extraction,
            disclosure_assessments=case.disclosure_assessments,
        )
        expected = dict(case.expected_verdicts)
        for verdict in report.claim_verdicts:
            if (
                verdict.verdict is ClaimVerdict.DEFEATED
                and expected.get(verdict.claim_id) is not ClaimVerdict.DEFEATED
            ):
                false_positives.append((case.case_id, verdict.claim_id))
    return FalsePositiveAnalysis(
        category=next(iter(categories)),
        case_count=len(cases),
        false_positive_defeats=tuple(false_positives),
    )
