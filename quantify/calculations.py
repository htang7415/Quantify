"""Provider-free deterministic calculations over admitted released facts.

The adapter accepts no caller-supplied values, formulas, source text, model
output, or narrative. Every operand must resolve to an exact fact in one
independently validated ``ApprovedEvidenceSearchResult``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from enum import StrEnum
from hashlib import sha256
import json
import re

from quantify.evidence_search import (
    ApprovedEvidenceFact,
    ApprovedEvidenceSearchResult,
    canonical_decimal,
)


_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_CALCULATION_ID_PATTERN = re.compile(r"^calc-[A-Za-z0-9._:-]+$")
_FACT_STATEMENT_ID_PATTERN = re.compile(r"^fact-[a-f0-9]{64}$")
_UNIT_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_./-]{0,31}$")
_LIMITATION = (
    "Direct numeric facts from one approved evidence-search result only; "
    "no model values, narrative inputs, predictions, recommendations, or verdicts."
)


class CalculationError(ValueError):
    """A calculation request, input binding, or result failed closed."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class CalculationOperation(StrEnum):
    SUM = "sum"
    DIFFERENCE = "difference"
    PERCENT_CHANGE = "percent_change"
    PERCENTAGE_POINT_CHANGE = "percentage_point_change"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _require_hash(value: str, *, field: str, code: str = "invalid_request") -> None:
    if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value):
        raise CalculationError(code, f"{field} must be a lowercase SHA-256 hash")


@dataclass(frozen=True, slots=True)
class ApprovedCalculationInstruction:
    result_statement_id: str
    operation: CalculationOperation
    input_statement_ids: tuple[str, ...]
    decimal_places: int

    def __post_init__(self) -> None:
        if not isinstance(self.result_statement_id, str) or not _CALCULATION_ID_PATTERN.fullmatch(
            self.result_statement_id
        ):
            raise CalculationError(
                "invalid_request", "result_statement_id must use the calc- namespace"
            )
        if not isinstance(self.operation, CalculationOperation):
            raise CalculationError("invalid_request", "operation is invalid")
        if (
            not isinstance(self.input_statement_ids, tuple)
            or not 2 <= len(self.input_statement_ids) <= 32
            or not all(
                isinstance(item, str) and _FACT_STATEMENT_ID_PATTERN.fullmatch(item)
                for item in self.input_statement_ids
            )
        ):
            raise CalculationError(
                "invalid_request", "inputs must contain 2 to 32 released-fact statement IDs"
            )
        if len(set(self.input_statement_ids)) != len(self.input_statement_ids):
            raise CalculationError("invalid_request", "input statement IDs must be unique")
        if self.operation is not CalculationOperation.SUM and len(self.input_statement_ids) != 2:
            raise CalculationError(
                "invalid_request", "comparison operations require current then baseline"
            )
        if (
            not isinstance(self.decimal_places, int)
            or isinstance(self.decimal_places, bool)
            or not 0 <= self.decimal_places <= 12
        ):
            raise CalculationError("invalid_request", "decimal_places must be from 0 to 12")

    def to_document(self) -> dict[str, object]:
        return {
            "result_statement_id": self.result_statement_id,
            "operation": self.operation.value,
            "input_statement_ids": list(self.input_statement_ids),
            "decimal_places": self.decimal_places,
        }


@dataclass(frozen=True, slots=True)
class ApprovedCalculationRequest:
    evidence_search_result_hash: str
    release_manifest_hash: str
    calculations: tuple[ApprovedCalculationInstruction, ...]
    schema_version: str = "approved-calculation-request.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "approved-calculation-request.v1":
            raise CalculationError("invalid_request", "request schema version is invalid")
        _require_hash(
            self.evidence_search_result_hash, field="evidence_search_result_hash"
        )
        _require_hash(self.release_manifest_hash, field="release_manifest_hash")
        if (
            not isinstance(self.calculations, tuple)
            or not 1 <= len(self.calculations) <= 32
            or not all(
                isinstance(item, ApprovedCalculationInstruction)
                for item in self.calculations
            )
        ):
            raise CalculationError(
                "invalid_request", "calculations must contain 1 to 32 instructions"
            )
        statement_ids = [item.result_statement_id for item in self.calculations]
        if len(set(statement_ids)) != len(statement_ids):
            raise CalculationError(
                "invalid_request", "result statement IDs must be unique"
            )

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "evidence_search_result_hash": self.evidence_search_result_hash,
            "release_manifest_hash": self.release_manifest_hash,
            "calculations": [item.to_document() for item in self.calculations],
        }

    @property
    def request_hash(self) -> str:
        return sha256(_canonical_json(self.to_document())).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovedCalculation:
    statement_id: str
    statement_text: str
    derived_from_statement_ids: tuple[str, ...]
    operation: CalculationOperation
    value: Decimal
    unit: str
    decimal_places: int

    def __post_init__(self) -> None:
        if not isinstance(self.statement_id, str) or not _CALCULATION_ID_PATTERN.fullmatch(
            self.statement_id
        ):
            raise CalculationError("invalid_result", "calculation statement ID is invalid")
        if not isinstance(self.operation, CalculationOperation):
            raise CalculationError("invalid_result", "calculation operation is invalid")
        if (
            not isinstance(self.derived_from_statement_ids, tuple)
            or not 2 <= len(self.derived_from_statement_ids) <= 32
            or len(set(self.derived_from_statement_ids))
            != len(self.derived_from_statement_ids)
            or not all(
                isinstance(item, str) and _FACT_STATEMENT_ID_PATTERN.fullmatch(item)
                for item in self.derived_from_statement_ids
            )
        ):
            raise CalculationError("invalid_result", "calculation derivation is invalid")
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise CalculationError("invalid_result", "calculation value is invalid")
        if not isinstance(self.unit, str) or not _UNIT_PATTERN.fullmatch(self.unit):
            raise CalculationError("invalid_result", "calculation unit is invalid")
        if (
            not isinstance(self.decimal_places, int)
            or isinstance(self.decimal_places, bool)
            or not 0 <= self.decimal_places <= 12
        ):
            raise CalculationError("invalid_result", "calculation precision is invalid")
        if self.statement_text != _calculation_text(
            operation=self.operation,
            value=self.value,
            unit=self.unit,
            decimal_places=self.decimal_places,
        ):
            raise CalculationError("invalid_result", "calculation text does not replay")

    def to_document(self) -> dict[str, object]:
        return {
            "statement_id": self.statement_id,
            "kind": "deterministic_calculation",
            "text": self.statement_text,
            "citation_ids": [],
            "derived_from_statement_ids": list(self.derived_from_statement_ids),
            "measurement": None,
            "calculation": {
                "operation": self.operation.value,
                "inputs": [
                    {"statement_id": statement_id}
                    for statement_id in self.derived_from_statement_ids
                ],
                "value": canonical_decimal(self.value),
                "unit": self.unit,
                "decimal_places": self.decimal_places,
            },
        }


@dataclass(frozen=True, slots=True)
class ApprovedCalculationResult:
    request: ApprovedCalculationRequest
    evidence_search_result: ApprovedEvidenceSearchResult
    calculations: tuple[ApprovedCalculation, ...]
    schema_version: str = "approved-calculation-result.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "approved-calculation-result.v1":
            raise CalculationError("invalid_result", "result schema version is invalid")
        if not isinstance(self.request, ApprovedCalculationRequest) or not isinstance(
            self.evidence_search_result, ApprovedEvidenceSearchResult
        ):
            raise CalculationError("invalid_result", "result bindings are invalid")
        _validate_binding(self.request, self.evidence_search_result)
        if not isinstance(self.calculations, tuple) or not all(
            isinstance(item, ApprovedCalculation) for item in self.calculations
        ):
            raise CalculationError("invalid_result", "calculations are invalid")
        if self.calculations != _evaluate(self.request, self.evidence_search_result):
            raise CalculationError("invalid_result", "calculation result does not replay")

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_hash": self.request.request_hash,
            "evidence_search_result_hash": self.request.evidence_search_result_hash,
            "release_manifest_hash": self.request.release_manifest_hash,
            "status": "completed",
            "calculations": [item.to_document() for item in self.calculations],
            "limitation": _LIMITATION,
        }

    @property
    def result_hash(self) -> str:
        return sha256(_canonical_json(self.to_document())).hexdigest()


class DeterministicCalculationAdapter:
    """Calculate only from exact facts in one admitted search result."""

    def calculate(
        self,
        *,
        request: ApprovedCalculationRequest,
        evidence_search_result: ApprovedEvidenceSearchResult,
    ) -> ApprovedCalculationResult:
        if not isinstance(request, ApprovedCalculationRequest) or not isinstance(
            evidence_search_result, ApprovedEvidenceSearchResult
        ):
            raise CalculationError("invalid_request", "calculation bindings are invalid")
        _validate_binding(request, evidence_search_result)
        return ApprovedCalculationResult(
            request=request,
            evidence_search_result=evidence_search_result,
            calculations=_evaluate(request, evidence_search_result),
        )


def _validate_binding(
    request: ApprovedCalculationRequest,
    evidence_search_result: ApprovedEvidenceSearchResult,
) -> None:
    if request.evidence_search_result_hash != evidence_search_result.result_hash:
        raise CalculationError(
            "input_binding_mismatch", "evidence search result hash does not match"
        )
    if (
        request.release_manifest_hash
        != evidence_search_result.request.release_manifest_hash
    ):
        raise CalculationError(
            "input_binding_mismatch", "release manifest hash does not match"
        )


def _evaluate(
    request: ApprovedCalculationRequest,
    evidence_search_result: ApprovedEvidenceSearchResult,
) -> tuple[ApprovedCalculation, ...]:
    facts = {fact.statement_id: fact for fact in evidence_search_result.facts}
    calculations: list[ApprovedCalculation] = []
    for instruction in request.calculations:
        try:
            inputs = tuple(facts[item] for item in instruction.input_statement_ids)
        except KeyError as error:
            raise CalculationError(
                "input_unavailable",
                "every calculation input must be an exact resolved fact in the bound search result",
            ) from error
        value, unit = _calculate(instruction, inputs)
        calculations.append(
            ApprovedCalculation(
                statement_id=instruction.result_statement_id,
                statement_text=_calculation_text(
                    operation=instruction.operation,
                    value=value,
                    unit=unit,
                    decimal_places=instruction.decimal_places,
                ),
                derived_from_statement_ids=instruction.input_statement_ids,
                operation=instruction.operation,
                value=value,
                unit=unit,
                decimal_places=instruction.decimal_places,
            )
        )
    return tuple(calculations)


def _calculate(
    instruction: ApprovedCalculationInstruction,
    inputs: tuple[ApprovedEvidenceFact, ...],
) -> tuple[Decimal, str]:
    operation = instruction.operation
    units = {item.unit for item in inputs}
    precision = max(
        80,
        sum(len(item.value.as_tuple().digits) for item in inputs)
        + instruction.decimal_places
        + 16,
    )
    quantum = Decimal(1).scaleb(-instruction.decimal_places)
    if operation is CalculationOperation.SUM:
        periods = {(item.period_start, item.period_end) for item in inputs}
        if len(units) != 1 or len(periods) != 1:
            raise CalculationError(
                "incompatible_inputs",
                "sum requires one unit and one exact reporting period",
            )
        unit = inputs[0].unit
    else:
        current, baseline = inputs
        _validate_comparison_inputs(current=current, baseline=baseline)
        if operation is CalculationOperation.PERCENTAGE_POINT_CHANGE:
            if units != {"percent"}:
                raise CalculationError(
                    "incompatible_inputs",
                    "percentage-point change requires percent inputs",
                )
            unit = "percentage_points"
        elif operation is CalculationOperation.PERCENT_CHANGE:
            if len(units) != 1 or baseline.value == 0:
                raise CalculationError(
                    "incompatible_inputs",
                    "percent change requires one unit and a non-zero baseline",
                )
            unit = "percent"
        else:
            if len(units) != 1:
                raise CalculationError(
                    "incompatible_inputs", "difference requires one unit"
                )
            unit = current.unit

    try:
        with localcontext() as context:
            context.prec = precision
            if operation is CalculationOperation.SUM:
                raw_value = sum((item.value for item in inputs), Decimal(0))
            elif operation is CalculationOperation.PERCENT_CHANGE:
                raw_value = (
                    (inputs[0].value - inputs[1].value)
                    / abs(inputs[1].value)
                    * Decimal(100)
                )
            else:
                raw_value = inputs[0].value - inputs[1].value
            value = raw_value.quantize(quantum, rounding=ROUND_HALF_EVEN)
    except InvalidOperation as error:
        raise CalculationError(
            "calculation_unavailable", "decimal result cannot be represented safely"
        ) from error
    return value, unit


def _validate_comparison_inputs(
    *, current: ApprovedEvidenceFact, baseline: ApprovedEvidenceFact
) -> None:
    current_duration = (current.period_end - current.period_start).days
    baseline_duration = (baseline.period_end - baseline.period_start).days
    if (
        current.entity_cik != baseline.entity_cik
        or current.release_manifest_hash != baseline.release_manifest_hash
        or current.metric != baseline.metric
        or current.period_start <= baseline.period_start
        or current.period_end <= baseline.period_end
        or abs(current_duration - baseline_duration) > 1
    ):
        raise CalculationError(
            "incompatible_inputs",
            "comparison requires current then baseline for one metric and compatible periods",
        )


def _calculation_text(
    *,
    operation: CalculationOperation,
    value: Decimal,
    unit: str,
    decimal_places: int,
) -> str:
    rendered = f"{value:.{decimal_places}f}"
    if operation is CalculationOperation.SUM:
        return f"Calculated sum: {rendered} {unit}."
    if operation is CalculationOperation.DIFFERENCE:
        return f"Calculated difference: {rendered} {unit}."
    if operation is CalculationOperation.PERCENT_CHANGE:
        return f"Calculated percent change: {rendered}%."
    return f"Calculated percentage-point change: {rendered} percentage points."
