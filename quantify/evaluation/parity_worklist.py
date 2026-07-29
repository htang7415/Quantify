"""Benchmark-safe handoff between frozen cases and external model execution."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .regression import RegressionCase


@dataclass(frozen=True, slots=True)
class PromptingParityWorkItem:
    """The only fields intended to be visible to the evaluated model."""

    request_id: str
    report_text: str


@dataclass(frozen=True, slots=True)
class PromptingParityReference:
    """Private evaluator-side mapping; never include it in a model prompt."""

    request_id: str
    case_id: str
    category: str
    expected_outcome: str


@dataclass(frozen=True, slots=True)
class PromptingParityWorklist:
    """Separate model input from evaluator-only frozen reference metadata."""

    items: tuple[PromptingParityWorkItem, ...]
    references: tuple[PromptingParityReference, ...]

    def model_input(self) -> dict:
        """Return the safe external-model payload with no reference information."""

        return {
            "worklist_version": "1.0.0",
            "items": [
                {"request_id": item.request_id, "report_text": item.report_text}
                for item in self.items
            ],
        }

    def reference_mapping(self) -> dict:
        """Return evaluator-side data for reconciling model outcomes later."""

        return {
            "reference_mapping_version": "1.0.0",
            "items": [
                {
                    "request_id": item.request_id,
                    "case_id": item.case_id,
                    "category": item.category,
                    "expected_outcome": item.expected_outcome,
                }
                for item in self.references
            ],
        }


def load_prompting_parity_references(
    *, path: Path
) -> tuple[PromptingParityReference, ...]:
    """Load the private mapping produced by the worklist CLI."""

    payload = json.loads(path.read_text())
    if payload.get("reference_mapping_version") != "1.0.0":
        raise ValueError("unsupported parity reference-mapping version")
    try:
        references = tuple(
            PromptingParityReference(
                request_id=item["request_id"],
                case_id=item["case_id"],
                category=item["category"],
                expected_outcome=item["expected_outcome"],
            )
            for item in payload["items"]
        )
    except (KeyError, TypeError) as error:
        raise ValueError("invalid parity reference mapping") from error
    if len(references) != 30:
        raise ValueError("parity reference mapping requires exactly 30 items")
    if len({item.request_id for item in references}) != len(references):
        raise ValueError("parity reference request IDs must be unique")
    if len({item.case_id for item in references}) != len(references):
        raise ValueError("parity reference case IDs must be unique")
    if {item.category for item in references} != {"mechanical", "judgment"}:
        raise ValueError("parity reference mapping contains unsupported categories")
    return references


def build_prompting_parity_worklist(
    *,
    mechanical_cases: tuple[RegressionCase, ...],
    judgment_cases: tuple[RegressionCase, ...],
) -> PromptingParityWorklist:
    """Create the fixed 30-case external-model worklist without label leakage."""

    _validate_case_sets(mechanical_cases, judgment_cases)
    items: list[PromptingParityWorkItem] = []
    references: list[PromptingParityReference] = []
    for case in sorted((*mechanical_cases, *judgment_cases), key=lambda item: item.case_id):
        request_id = sha256(case.case_id.encode()).hexdigest()[:16]
        expected_outcome = (
            "unclassified"
            if case.expected_unclassified_statement_ids
            else case.expected_verdicts[0][1].value
        )
        items.append(
            PromptingParityWorkItem(request_id=request_id, report_text=case.report_text)
        )
        references.append(
            PromptingParityReference(
                request_id=request_id,
                case_id=case.case_id,
                category=case.category,
                expected_outcome=expected_outcome,
            )
        )
    return PromptingParityWorklist(items=tuple(items), references=tuple(references))


def _validate_case_sets(
    mechanical_cases: tuple[RegressionCase, ...],
    judgment_cases: tuple[RegressionCase, ...],
) -> None:
    if len(mechanical_cases) != 20 or {item.category for item in mechanical_cases} != {
        "mechanical"
    }:
        raise ValueError("prompting worklist requires exactly 20 mechanical cases")
    if len(judgment_cases) != 10 or {item.category for item in judgment_cases} != {
        "judgment"
    }:
        raise ValueError("prompting worklist requires exactly 10 judgment cases")
    case_ids = [item.case_id for item in (*mechanical_cases, *judgment_cases)]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("prompting worklist case IDs must be unique")
