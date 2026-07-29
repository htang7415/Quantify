"""Measured, one-call interactive-runtime evaluation for the frozen corpus.

This module deliberately does not execute an evaluation at import time.  A
caller must supply an explicit authorization cap and an extractor configured
for the normal ``generateContent`` path.  Batch measurements are intentionally
not accepted here: their queue time is not user-facing request latency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from time import monotonic
from typing import Callable

from quantify.engine import ClaimVerdict, ReviewReason
from quantify.harness import StructuredExtractor, verify_report

from .regression import RegressionCase
from .stability import RepeatedRunStability, repeated_run_stability_as_dict


_CATEGORY_COUNTS = {"mechanical": 20, "judgment": 10}


@dataclass(frozen=True, slots=True)
class InteractiveRuntimeAuthorization:
    """Explicit no-secret cost and latency envelope for one 30-case run."""

    authorization_version: str
    provider: str
    model: str
    temperature: float
    prompt_hash: str
    request_timeout_seconds: float
    max_total_cost_usd: float
    max_request_cost_usd: float
    max_input_tokens: int = 6144

    def __post_init__(self) -> None:
        numeric_values = (
            self.temperature,
            self.request_timeout_seconds,
            self.max_total_cost_usd,
            self.max_request_cost_usd,
        )
        if (
            self.authorization_version != "1.0.0"
            or not self.provider
            or not self.model
            or len(self.prompt_hash) != 64
            or any(character not in "0123456789abcdef" for character in self.prompt_hash)
            or any(not math.isfinite(value) for value in numeric_values)
            or not 0.0 <= self.temperature <= 2.0
            or not 0.1 <= self.request_timeout_seconds <= 30.0
            or self.max_total_cost_usd <= 0.0
            or self.max_request_cost_usd < 0.0
            or self.max_input_tokens <= 0
        ):
            raise ValueError("interactive runtime authorization is invalid")
        if 30 * self.max_request_cost_usd > self.max_total_cost_usd:
            raise ValueError(
                "interactive runtime authorization cannot cover all 30 requests"
            )


@dataclass(frozen=True, slots=True)
class InteractiveRuntimeCaseMeasurement:
    """No-secret outcome and usage metadata for one frozen report."""

    case_id: str
    category: str
    end_to_end_request_seconds: float
    input_tokens: int
    output_tokens: int
    total_cost_usd: float
    extractor_version: str
    verdicts: tuple[tuple[str, str], ...]
    unclassified_statement_count: int
    agent_resolution_count: int
    failed_closed: bool
    missing_disclosure_assessment_count: int
    sec_insufficient: bool


@dataclass(frozen=True, slots=True)
class InteractiveRuntimeMeasurement:
    """Complete measured output used by the readiness artifact compiler."""

    authorization: InteractiveRuntimeAuthorization
    stability_artifact_hash: str
    verified_defeated_flips: int
    cases: tuple[InteractiveRuntimeCaseMeasurement, ...]


@dataclass(frozen=True, slots=True)
class InteractiveRuntimeTrial:
    """One no-cache 30-case execution of the normal extraction prompt."""

    authorization: InteractiveRuntimeAuthorization
    cases: tuple[InteractiveRuntimeCaseMeasurement, ...]


@dataclass(frozen=True, slots=True)
class InteractiveRepeatedRunStability:
    """Stability measured from two normal-prompt interactive trials."""

    artifact_version: str
    model: str
    prompt_hash: str
    temperature: float
    case_count: int
    trial_count: int
    exact_report_level_agreement: bool
    statement_level_agreement: float
    classified_unclassified_transitions: int
    verified_defeated_flips: int
    mechanical_verified_defeated_flips: int


Clock = Callable[[], float]


def run_interactive_runtime_evaluation(
    *,
    mechanical_cases: tuple[RegressionCase, ...],
    judgment_cases: tuple[RegressionCase, ...],
    extractor: StructuredExtractor,
    authorization: InteractiveRuntimeAuthorization,
    stability: RepeatedRunStability,
    clock: Clock = monotonic,
) -> InteractiveRuntimeMeasurement:
    """Run exactly 30 frozen cases through one extractor call each.

    The supplied extractor is called once for each report.  Verification then
    runs locally and no disclosure model call, retry, or evidence acquisition
    is introduced by this evaluator.  A request failure aborts without an
    artifact, so an incomplete run cannot be used as readiness evidence.
    """

    cases = validate_interactive_runtime_inputs(
        mechanical_cases=mechanical_cases,
        judgment_cases=judgment_cases,
        authorization=authorization,
        stability=stability,
    )
    trial = run_interactive_runtime_trial(
        mechanical_cases=mechanical_cases,
        judgment_cases=judgment_cases,
        extractor=extractor,
        authorization=authorization,
        clock=clock,
    )
    return InteractiveRuntimeMeasurement(
        authorization=authorization,
        stability_artifact_hash=repeated_run_stability_hash(stability=stability),
        verified_defeated_flips=stability.quantify.mechanical_verified_defeated_flips,
        cases=trial.cases,
    )


def run_interactive_runtime_trial(
    *,
    mechanical_cases: tuple[RegressionCase, ...],
    judgment_cases: tuple[RegressionCase, ...],
    extractor: StructuredExtractor,
    authorization: InteractiveRuntimeAuthorization,
    clock: Clock = monotonic,
) -> InteractiveRuntimeTrial:
    """Execute one independent normal-prompt trial without stability input."""

    cases = _validate_case_sets(
        mechanical_cases=mechanical_cases, judgment_cases=judgment_cases
    )
    measurements: list[InteractiveRuntimeCaseMeasurement] = []
    for case in cases:
        started = clock()
        extraction = extractor.extract(report_text=case.report_text, snapshot=case.snapshot)
        elapsed = clock() - started
        if not math.isfinite(elapsed) or elapsed < 0.0:
            raise ValueError("interactive request clock returned an invalid duration")
        _validate_extraction_usage(extraction=extraction, authorization=authorization)
        report = verify_report(
            report_text=case.report_text,
            snapshot=case.snapshot,
            extraction=extraction,
        )
        extraction_failed_closed = any(
            item.reason is ReviewReason.EXTRACTION_SCHEMA_FAILURE
            for item in report.review_items
        )
        measurements.append(
            InteractiveRuntimeCaseMeasurement(
                case_id=case.case_id,
                category=case.category,
                end_to_end_request_seconds=elapsed,
                input_tokens=extraction.input_tokens,
                output_tokens=extraction.output_tokens,
                total_cost_usd=extraction.total_cost,
                extractor_version=extraction.extractor_version,
                verdicts=tuple(
                    (item.claim_id, item.verdict.value) for item in report.claim_verdicts
                ),
                unclassified_statement_count=len(report.unclassified_statement_ids),
                agent_resolution_count=sum(
                    item.verdict is ClaimVerdict.REQUIRES_AGENT_RESOLUTION
                    for item in report.claim_verdicts
                ) + extraction_failed_closed,
                failed_closed=extraction_failed_closed,
                missing_disclosure_assessment_count=sum(
                    item.reason is ReviewReason.MISSING_DISCLOSURE_ASSESSMENT
                    for item in report.review_items
                ),
                sec_insufficient=_sec_insufficient(case=case),
            )
        )
    if sum(item.total_cost_usd for item in measurements) > authorization.max_total_cost_usd:
        raise ValueError("interactive runtime exceeded its explicit total cost cap")
    return InteractiveRuntimeTrial(
        authorization=authorization,
        cases=tuple(measurements),
    )


def evaluate_interactive_repeated_run_stability(
    *, first_trial: InteractiveRuntimeTrial, second_trial: InteractiveRuntimeTrial
) -> InteractiveRepeatedRunStability:
    """Compare two independent normal-prompt trials without a provider call."""

    if first_trial.authorization != second_trial.authorization:
        raise ValueError("interactive trials must use identical authorization metadata")
    first = {item.case_id: item for item in first_trial.cases}
    second = {item.case_id: item for item in second_trial.cases}
    if len(first) != 30 or set(first) != set(second):
        raise ValueError("interactive trials must contain the same 30 case IDs")
    if any(first[key].category != second[key].category for key in first):
        raise ValueError("interactive trials disagree about case categories")
    matches = sum(_trial_outcome(first[key]) == _trial_outcome(second[key]) for key in first)
    transitions = sum(
        (first[key].unclassified_statement_count > 0)
        != (second[key].unclassified_statement_count > 0)
        for key in first
    )
    flips = tuple(
        key for key in first if _verified_defeated_flip(first[key], second[key])
    )
    return InteractiveRepeatedRunStability(
        artifact_version="1.0.0",
        model=first_trial.authorization.model,
        prompt_hash=first_trial.authorization.prompt_hash,
        temperature=first_trial.authorization.temperature,
        case_count=30,
        trial_count=2,
        exact_report_level_agreement=matches == 30,
        statement_level_agreement=matches / 30,
        classified_unclassified_transitions=transitions,
        verified_defeated_flips=len(flips),
        mechanical_verified_defeated_flips=sum(
            first[key].category == "mechanical" for key in flips
        ),
    )


def interactive_runtime_trial_as_dict(*, trial: InteractiveRuntimeTrial) -> dict:
    """Serialize one normal-prompt trial without credentials or gold labels."""

    _validate_trial(trial=trial)
    payload = {
        "artifact_version": "1.0.0",
        "authorization": asdict(trial.authorization),
        "cases": [_case_record(item=item) for item in trial.cases],
    }
    return {"trial_hash": _canonical_hash(payload), **payload}


def load_interactive_runtime_trial(*, path: Path) -> InteractiveRuntimeTrial:
    """Load a complete, hash-validated normal-prompt trial artifact."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("invalid interactive runtime trial artifact") from error
    if not isinstance(payload, dict) or payload.get("artifact_version") != "1.0.0":
        raise ValueError("unsupported interactive runtime trial artifact")
    trial_hash = payload.get("trial_hash")
    unsigned = {key: value for key, value in payload.items() if key != "trial_hash"}
    if not isinstance(trial_hash, str) or trial_hash != _canonical_hash(unsigned):
        raise ValueError("interactive runtime trial artifact has an invalid hash")
    try:
        authorization = InteractiveRuntimeAuthorization(**payload["authorization"])
        cases = tuple(_case_measurement_from_record(item) for item in payload["cases"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("interactive runtime trial artifact is invalid") from error
    trial = InteractiveRuntimeTrial(authorization=authorization, cases=cases)
    _validate_trial(trial=trial)
    return trial


def interactive_repeated_run_stability_as_dict(
    *, stability: InteractiveRepeatedRunStability
) -> dict:
    """Serialize a normal-prompt repeated-run result with a stable identity."""

    _validate_interactive_stability(stability=stability)
    payload = {"artifact_version": stability.artifact_version, "stability": asdict(stability)}
    return {"stability_hash": _canonical_hash(payload), **payload}


def load_interactive_repeated_run_stability(*, path: Path) -> InteractiveRepeatedRunStability:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("invalid interactive stability artifact") from error
    if not isinstance(payload, dict):
        raise ValueError("invalid interactive stability artifact")
    return _interactive_stability_from_artifact(payload=payload)


def compile_interactive_runtime_artifact(
    *, trial: InteractiveRuntimeTrial, stability: InteractiveRepeatedRunStability
) -> dict:
    """Compile measured normal-prompt trial and stability into readiness input."""

    _validate_trial(trial=trial)
    _validate_interactive_stability(stability=stability)
    authorization = trial.authorization
    if (
        stability.model != authorization.model
        or stability.prompt_hash != authorization.prompt_hash
        or stability.temperature != authorization.temperature
    ):
        raise ValueError("interactive trial and stability metadata do not match")
    stability_payload = interactive_repeated_run_stability_as_dict(stability=stability)
    payload = {
        "artifact_version": "1.2.0",
        "provenance": {
            "execution_mode": "interactive_runtime",
            "sample_count": 30,
            "latency_kind": "mean_end_to_end_request_seconds",
            "cost_kind": "observed_provider_usage_per_report",
        },
        "authorization": asdict(authorization),
        "stability_artifact_hash": stability_payload["stability_hash"],
        "normal_prompt_stability": stability_payload,
        "cases": [_case_record(item=item) for item in trial.cases],
        "measurements": {
            "verified_defeated_flips": stability.mechanical_verified_defeated_flips,
            "latency_seconds": sum(item.end_to_end_request_seconds for item in trial.cases) / 30,
            "cost_per_report": sum(item.total_cost_usd for item in trial.cases) / 30,
            "sec_insufficiency_count": sum(item.sec_insufficient for item in trial.cases),
        },
    }
    return {"run_hash": _canonical_hash(payload), **payload}


def validate_interactive_runtime_inputs(
    *,
    mechanical_cases: tuple[RegressionCase, ...],
    judgment_cases: tuple[RegressionCase, ...],
    authorization: InteractiveRuntimeAuthorization,
    stability: RepeatedRunStability,
) -> tuple[RegressionCase, ...]:
    """Validate the complete no-network preflight for a paid interactive run.

    Stability must come from the same model, temperature, prompt, and schema
    as the normal extractor.  A Batch artifact produced from another prompt is
    useful for its own offline evaluation, but cannot stand in for this check.
    """

    cases = _validate_case_sets(
        mechanical_cases=mechanical_cases, judgment_cases=judgment_cases
    )
    _validate_stability(stability=stability, authorization=authorization)
    return cases


def interactive_runtime_artifact_as_dict(
    *, measurement: InteractiveRuntimeMeasurement
) -> dict:
    """Create canonical v1.2 readiness input without credentials or gold labels."""

    _validate_measurement(measurement=measurement)
    records = [
        {
            "case_id": item.case_id,
            "category": item.category,
            "end_to_end_request_seconds": item.end_to_end_request_seconds,
            "input_tokens": item.input_tokens,
            "output_tokens": item.output_tokens,
            "total_cost_usd": item.total_cost_usd,
            "extractor_version": item.extractor_version,
            "verdicts": [list(verdict) for verdict in item.verdicts],
            "unclassified_statement_count": item.unclassified_statement_count,
            "agent_resolution_count": item.agent_resolution_count,
            "failed_closed": item.failed_closed,
            "missing_disclosure_assessment_count": item.missing_disclosure_assessment_count,
            "sec_insufficient": item.sec_insufficient,
        }
        for item in measurement.cases
    ]
    payload = {
        "artifact_version": "1.2.0",
        "provenance": {
            "execution_mode": "interactive_runtime",
            "sample_count": 30,
            "latency_kind": "mean_end_to_end_request_seconds",
            "cost_kind": "observed_provider_usage_per_report",
        },
        "authorization": asdict(measurement.authorization),
        "stability_artifact_hash": measurement.stability_artifact_hash,
        "cases": records,
        "measurements": {
            "verified_defeated_flips": measurement.verified_defeated_flips,
            "latency_seconds": sum(
                item.end_to_end_request_seconds for item in measurement.cases
            )
            / len(measurement.cases),
            "cost_per_report": sum(item.total_cost_usd for item in measurement.cases)
            / len(measurement.cases),
            "sec_insufficiency_count": sum(
                item.sec_insufficient for item in measurement.cases
            ),
        },
    }
    return {"run_hash": _canonical_hash(payload), **payload}


def validate_interactive_runtime_artifact(*, payload: object) -> None:
    """Reject altered, incomplete, or non-interactive readiness evidence."""

    if not isinstance(payload, dict) or payload.get("artifact_version") != "1.2.0":
        raise ValueError("unsupported interactive operations artifact version")
    run_hash = payload.get("run_hash")
    unsigned = {key: value for key, value in payload.items() if key != "run_hash"}
    if not isinstance(run_hash, str) or run_hash != _canonical_hash(unsigned):
        raise ValueError("interactive operations artifact has an invalid run hash")
    if payload.get("provenance") != {
        "execution_mode": "interactive_runtime",
        "sample_count": 30,
        "latency_kind": "mean_end_to_end_request_seconds",
        "cost_kind": "observed_provider_usage_per_report",
    }:
        raise ValueError("interactive operations artifact has unsupported provenance")
    cases = payload.get("cases")
    measurements = payload.get("measurements")
    authorization_payload = payload.get("authorization")
    stability_artifact_hash = payload.get("stability_artifact_hash")
    normal_stability = payload.get("normal_prompt_stability")
    if (
        not isinstance(cases, list)
        or not isinstance(measurements, dict)
        or not isinstance(authorization_payload, dict)
        or not isinstance(stability_artifact_hash, str)
        or len(stability_artifact_hash) != 64
        or any(character not in "0123456789abcdef" for character in stability_artifact_hash)
    ):
        raise ValueError("interactive operations artifact is incomplete")
    try:
        authorization = InteractiveRuntimeAuthorization(**authorization_payload)
    except (TypeError, ValueError) as error:
        raise ValueError("interactive operations artifact has invalid authorization") from error
    if authorization_payload != asdict(authorization):
        raise ValueError("interactive operations artifact has invalid authorization")
    stability = None
    if normal_stability is not None:
        if not isinstance(normal_stability, dict):
            raise ValueError("interactive operations artifact has invalid normal stability")
        stability = _interactive_stability_from_artifact(payload=normal_stability)
        if (
            normal_stability.get("stability_hash") != stability_artifact_hash
            or stability.model != authorization.model
            or stability.prompt_hash != authorization.prompt_hash
            or stability.temperature != authorization.temperature
        ):
            raise ValueError("interactive operations artifact has invalid normal stability")
    if len(cases) != 30 or any(not isinstance(item, dict) for item in cases):
        raise ValueError("interactive operations artifact requires exactly 30 case records")
    case_ids = [item.get("case_id") for item in cases]
    if any(not isinstance(case_id, str) or not case_id for case_id in case_ids) or len(
        set(case_ids)
    ) != 30:
        raise ValueError("interactive operations artifact case IDs must be unique")
    _validate_artifact_case_records(cases=cases, authorization=authorization)
    _validate_artifact_measurements(cases=cases, measurements=measurements)
    if stability is not None and measurements["verified_defeated_flips"] != stability.mechanical_verified_defeated_flips:
        raise ValueError("interactive operations artifact has inconsistent stability flips")


def _validate_case_sets(
    *,
    mechanical_cases: tuple[RegressionCase, ...],
    judgment_cases: tuple[RegressionCase, ...],
) -> tuple[RegressionCase, ...]:
    cases = tuple(sorted((*mechanical_cases, *judgment_cases), key=lambda item: item.case_id))
    if len(cases) != 30 or len({item.case_id for item in cases}) != 30:
        raise ValueError("interactive runtime evaluation requires exactly 30 unique cases")
    counts = {
        category: sum(item.category == category for item in cases)
        for category in _CATEGORY_COUNTS
    }
    if counts != _CATEGORY_COUNTS:
        raise ValueError("interactive runtime evaluation requires 20 mechanical and 10 judgment cases")
    return cases


def _validate_stability(
    *, stability: RepeatedRunStability, authorization: InteractiveRuntimeAuthorization
) -> None:
    if stability.case_count != 30 or stability.trial_count < 2:
        raise ValueError("interactive runtime evaluation requires 30-case repeated-run stability")
    if (
        stability.quantify.model != authorization.model
        or stability.quantify.temperature != authorization.temperature
        or stability.quantify.prompt_hash != authorization.prompt_hash
    ):
        raise ValueError("interactive runtime authorization must match stability metadata")


def _validate_extraction_usage(*, extraction: object, authorization: InteractiveRuntimeAuthorization) -> None:
    input_tokens = getattr(extraction, "input_tokens", None)
    output_tokens = getattr(extraction, "output_tokens", None)
    total_cost = getattr(extraction, "total_cost", None)
    if total_cost is None:
        total_cost = getattr(extraction, "total_cost_usd", None)
    if (
        isinstance(input_tokens, bool)
        or isinstance(output_tokens, bool)
        or not isinstance(input_tokens, int)
        or not isinstance(output_tokens, int)
        or input_tokens < 0
        or input_tokens > authorization.max_input_tokens
        or output_tokens < 0
        or isinstance(total_cost, bool)
        or not isinstance(total_cost, (int, float))
        or not math.isfinite(total_cost)
        or total_cost < 0.0
        or total_cost > authorization.max_request_cost_usd
    ):
        raise ValueError("interactive extraction usage exceeds its authorization")


def _sec_insufficient(*, case: RegressionCase) -> bool:
    visible_ids = case.snapshot.visible_evidence_ids
    return not any(
        evidence.eligible
        and (visible_ids is None or evidence.evidence_id in visible_ids)
        for evidence in case.snapshot.evidence
    )


def _validate_measurement(*, measurement: InteractiveRuntimeMeasurement) -> None:
    if len(measurement.cases) != 30 or len({item.case_id for item in measurement.cases}) != 30:
        raise ValueError("interactive runtime measurement requires 30 unique cases")
    if not isinstance(measurement.verified_defeated_flips, int) or measurement.verified_defeated_flips < 0:
        raise ValueError("interactive runtime measurement has invalid stability")
    for item in measurement.cases:
        _validate_extraction_usage(extraction=item, authorization=measurement.authorization)
        if (
            not math.isfinite(item.end_to_end_request_seconds)
            or item.end_to_end_request_seconds < 0.0
            or not item.extractor_version
        ):
            raise ValueError("interactive runtime measurement has invalid case timing")


def _validate_trial(*, trial: InteractiveRuntimeTrial) -> None:
    if len(trial.cases) != 30 or len({item.case_id for item in trial.cases}) != 30:
        raise ValueError("interactive runtime trial requires 30 unique cases")
    counts = {category: sum(item.category == category for item in trial.cases) for category in _CATEGORY_COUNTS}
    if counts != _CATEGORY_COUNTS:
        raise ValueError("interactive runtime trial requires 20 mechanical and 10 judgment cases")
    for item in trial.cases:
        _validate_extraction_usage(extraction=item, authorization=trial.authorization)


def _validate_interactive_stability(*, stability: InteractiveRepeatedRunStability) -> None:
    if (
        stability.artifact_version != "1.0.0"
        or not stability.model
        or len(stability.prompt_hash) != 64
        or not 0.0 <= stability.temperature <= 2.0
        or stability.case_count != 30
        or stability.trial_count != 2
        or not 0.0 <= stability.statement_level_agreement <= 1.0
        or min(
            stability.classified_unclassified_transitions,
            stability.verified_defeated_flips,
            stability.mechanical_verified_defeated_flips,
        ) < 0
    ):
        raise ValueError("interactive repeated-run stability artifact is invalid")


def _interactive_stability_from_artifact(*, payload: dict) -> InteractiveRepeatedRunStability:
    try:
        unsigned = {"artifact_version": payload["artifact_version"], "stability": payload["stability"]}
        if payload.get("stability_hash") != _canonical_hash(unsigned):
            raise ValueError("interactive stability hash is invalid")
        stability = InteractiveRepeatedRunStability(**payload["stability"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("interactive stability artifact is invalid") from error
    _validate_interactive_stability(stability=stability)
    return stability


def _validate_artifact_measurements(*, cases: list[dict], measurements: dict) -> None:
    try:
        latency = measurements["latency_seconds"]
        cost = measurements["cost_per_report"]
        flips = measurements["verified_defeated_flips"]
        insufficiency = measurements["sec_insufficiency_count"]
    except KeyError as error:
        raise ValueError("interactive operations artifact is incomplete") from error
    expected_latency = sum(item["end_to_end_request_seconds"] for item in cases) / 30
    expected_cost = sum(item["total_cost_usd"] for item in cases) / 30
    expected_insufficiency = sum(item.get("sec_insufficient") is True for item in cases)
    if (
        any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (latency, cost, flips, insufficiency))
        or not all(math.isfinite(value) and value >= 0 for value in (latency, cost, flips, insufficiency))
        or not isinstance(flips, int)
        or not isinstance(insufficiency, int)
        or abs(latency - expected_latency) > 1e-12
        or abs(cost - expected_cost) > 1e-12
        or insufficiency != expected_insufficiency
    ):
        raise ValueError("interactive operations artifact measurements are invalid")


def _validate_artifact_case_records(
    *, cases: list[dict], authorization: InteractiveRuntimeAuthorization
) -> None:
    for item in cases:
        required = {
            "case_id",
            "category",
            "end_to_end_request_seconds",
            "input_tokens",
            "output_tokens",
            "total_cost_usd",
            "extractor_version",
            "verdicts",
            "unclassified_statement_count",
            "agent_resolution_count",
            "failed_closed",
            "missing_disclosure_assessment_count",
            "sec_insufficient",
        }
        if set(item) != required:
            raise ValueError("interactive operations artifact case record is invalid")


def _case_record(*, item: InteractiveRuntimeCaseMeasurement) -> dict:
    return {
        "case_id": item.case_id,
        "category": item.category,
        "end_to_end_request_seconds": item.end_to_end_request_seconds,
        "input_tokens": item.input_tokens,
        "output_tokens": item.output_tokens,
        "total_cost_usd": item.total_cost_usd,
        "extractor_version": item.extractor_version,
        "verdicts": [list(verdict) for verdict in item.verdicts],
        "unclassified_statement_count": item.unclassified_statement_count,
        "agent_resolution_count": item.agent_resolution_count,
        "failed_closed": item.failed_closed,
        "missing_disclosure_assessment_count": item.missing_disclosure_assessment_count,
        "sec_insufficient": item.sec_insufficient,
    }


def _case_measurement_from_record(item: object) -> InteractiveRuntimeCaseMeasurement:
    if not isinstance(item, dict):
        raise ValueError("interactive trial case record is invalid")
    required = set(_case_record(item=InteractiveRuntimeCaseMeasurement(
        case_id="x", category="mechanical", end_to_end_request_seconds=0.0,
        input_tokens=0, output_tokens=0, total_cost_usd=0.0, extractor_version="x",
        verdicts=(), unclassified_statement_count=0, agent_resolution_count=0,
        failed_closed=False, missing_disclosure_assessment_count=0, sec_insufficient=False,
    )))
    if set(item) != required:
        raise ValueError("interactive trial case record is invalid")
    return InteractiveRuntimeCaseMeasurement(
        case_id=item["case_id"], category=item["category"],
        end_to_end_request_seconds=item["end_to_end_request_seconds"],
        input_tokens=item["input_tokens"], output_tokens=item["output_tokens"],
        total_cost_usd=item["total_cost_usd"], extractor_version=item["extractor_version"],
        verdicts=tuple(tuple(value) for value in item["verdicts"]),
        unclassified_statement_count=item["unclassified_statement_count"],
        agent_resolution_count=item["agent_resolution_count"], failed_closed=item["failed_closed"],
        missing_disclosure_assessment_count=item["missing_disclosure_assessment_count"],
        sec_insufficient=item["sec_insufficient"],
    )
def repeated_run_stability_hash(*, stability: RepeatedRunStability) -> str:
    """Canonical identity of the no-secret stability input used by a run."""

    return _canonical_hash(repeated_run_stability_as_dict(stability=stability))


def _trial_outcome(item: InteractiveRuntimeCaseMeasurement) -> tuple:
    return (
        item.verdicts,
        item.unclassified_statement_count,
        item.agent_resolution_count,
        item.failed_closed,
        item.missing_disclosure_assessment_count,
    )


def _verified_defeated_flip(
    first: InteractiveRuntimeCaseMeasurement, second: InteractiveRuntimeCaseMeasurement
) -> bool:
    first_verdicts = dict(first.verdicts)
    second_verdicts = dict(second.verdicts)
    return any(
        {first_verdicts.get(claim_id), second_verdicts.get(claim_id)}
        == {ClaimVerdict.VERIFIED.value, ClaimVerdict.DEFEATED.value}
        for claim_id in set(first_verdicts) | set(second_verdicts)
    )


def _canonical_hash(payload: object) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
