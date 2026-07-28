"""Versioned, network-free regression execution for frozen evidence cases."""

from __future__ import annotations

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
        results.append((case.case_id, actual))
    return tuple(results)
