"""Compose frozen regression evidence and a pinned parity artifact into readiness."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
import json
from pathlib import Path

from quantify.engine import ClaimVerdict

from .parity import (
    PromptingParityArtifact,
    PromptingParityCase,
    PromptingParitySummary,
    evaluate_prompting_parity,
)
from .readiness import (
    ReadinessAssessment,
    ReadinessInputs,
    ReadinessPolicy,
    assess_readiness,
)
from .regression import RegressionCase, run_cases
from .stability import RepeatedRunStability
from .interactive import (
    repeated_run_stability_hash,
    validate_interactive_runtime_artifact,
)


@dataclass(frozen=True, slots=True)
class OperationalMeasurements:
    """Measured outside the frozen corpus during a pinned scheduled evaluation."""

    verified_defeated_flips: int
    latency_seconds: float
    cost_per_report: float
    sec_insufficiency_count: int
    stability_artifact_hash: str | None = None
    normal_prompt_stability: bool = False


@dataclass(frozen=True, slots=True)
class ReadinessRun:
    """Replayable Week 6 decision report with its source metrics exposed."""

    parity: PromptingParitySummary
    stability: RepeatedRunStability
    inputs: ReadinessInputs
    assessment: ReadinessAssessment


def load_operational_measurements(*, path: Path) -> OperationalMeasurements:
    """Load recorded operational measurements from a versioned artifact."""

    payload = json.loads(path.read_text())
    artifact_version = payload.get("artifact_version")
    if artifact_version not in {"1.0.0", "1.1.0", "1.2.0"}:
        raise ValueError("unsupported operational-measurements artifact version")
    if artifact_version == "1.1.0":
        raise ValueError(
            "Batch quality measurements cannot satisfy interactive latency readiness"
        )
    if artifact_version == "1.2.0":
        validate_interactive_runtime_artifact(payload=payload)
    measurements = payload.get("measurements")
    if not isinstance(measurements, dict):
        raise ValueError("operational-measurements artifact requires measurements")
    try:
        values = OperationalMeasurements(
            verified_defeated_flips=measurements["verified_defeated_flips"],
            latency_seconds=measurements["latency_seconds"],
            cost_per_report=measurements["cost_per_report"],
            sec_insufficiency_count=measurements["sec_insufficiency_count"],
            stability_artifact_hash=(
                payload["stability_artifact_hash"]
                if artifact_version == "1.2.0"
                else None
            ),
            normal_prompt_stability=(
                artifact_version == "1.2.0" and "normal_prompt_stability" in payload
            ),
        )
    except KeyError as error:
        raise ValueError("operational-measurements artifact is incomplete") from error
    numeric_values = (
        values.verified_defeated_flips,
        values.latency_seconds,
        values.cost_per_report,
        values.sec_insufficiency_count,
    )
    if any(isinstance(value, bool) for value in numeric_values):
        raise ValueError("operational measurements must be numeric")
    if not all(isinstance(value, (int, float)) for value in numeric_values):
        raise ValueError("operational measurements must be numeric")
    return values


def readiness_run_as_dict(*, run: ReadinessRun) -> dict:
    """Canonical JSON-ready result; callers decide whether and where to persist it."""

    parity = asdict(run.parity)
    parity["decision"] = run.parity.decision.value
    inputs = asdict(run.inputs)
    inputs["prompting_parity"] = run.inputs.prompting_parity.value
    assessment = asdict(run.assessment)
    assessment["decision"] = run.assessment.decision.value
    return {
        "readiness_run_version": "1.1.0",
        "parity": parity,
        "stability": asdict(run.stability),
        "inputs": inputs,
        "assessment": assessment,
    }


def run_readiness_evaluation(
    *,
    mechanical_cases: tuple[RegressionCase, ...],
    judgment_cases: tuple[RegressionCase, ...],
    parity_artifact: PromptingParityArtifact,
    stability: RepeatedRunStability,
    operations: OperationalMeasurements,
    policy: ReadinessPolicy = ReadinessPolicy(),
) -> ReadinessRun:
    """Evaluate exactly the frozen corpus and never fabricate model measurements.

    The deterministic cases are re-run twice before their expected outcomes are
    matched against the externally generated parity artifact.  Latency, cost,
    SEC coverage, and repeat-run instability are explicit scheduled-evaluation
    measurements because a pure offline regression run cannot truthfully infer
    them.
    """

    _validate_case_sets(mechanical_cases, judgment_cases)
    if (
        operations.verified_defeated_flips
        != stability.quantify.mechanical_verified_defeated_flips
    ):
        raise ValueError(
            "operational verified-defeated flips must match the scheduled stability artifact"
        )
    if (
        not operations.normal_prompt_stability
        and
        operations.stability_artifact_hash is not None
        and operations.stability_artifact_hash
        != repeated_run_stability_hash(stability=stability)
    ):
        raise ValueError("interactive operations do not match the scheduled stability artifact")
    first_pass = run_cases(cases=mechanical_cases) + run_cases(cases=judgment_cases)
    second_pass = run_cases(cases=mechanical_cases) + run_cases(cases=judgment_cases)
    if first_pass != second_pass:
        raise AssertionError("frozen regression outcomes are not replay-stable")

    expected_by_case = _expected_outcomes(
        mechanical_cases=mechanical_cases, judgment_cases=judgment_cases
    )
    artifact_by_case = {item.case_id: item for item in parity_artifact.cases}
    if set(artifact_by_case) != set(expected_by_case):
        raise ValueError("parity artifact case IDs do not match the frozen corpus")
    for case_id, (category, expected) in expected_by_case.items():
        artifact_case = artifact_by_case[case_id]
        if artifact_case.category != category or artifact_case.expected_outcome != expected:
            raise ValueError("parity artifact does not match frozen case expectations")

    parity = evaluate_prompting_parity(cases=parity_artifact.cases)
    mechanical = tuple(
        item for item in parity_artifact.cases if item.category == "mechanical"
    )
    judgment = tuple(
        item for item in parity_artifact.cases if item.category == "judgment"
    )
    inputs = ReadinessInputs(
        mechanical_false_positive_rate=_false_positive_defeat_rate(mechanical),
        verified_defeated_flips=operations.verified_defeated_flips,
        judgment_false_positive_rate=_false_positive_defeat_rate(judgment),
        unclassified_fraction=(
            sum(item.quantify_outcome == "unclassified" for item in parity_artifact.cases)
            / len(parity_artifact.cases)
        ),
        agent_resolution_rate=(
            sum(
                item.quantify_outcome
                == ClaimVerdict.REQUIRES_AGENT_RESOLUTION.value
                for item in parity_artifact.cases
            )
            / len(parity_artifact.cases)
        ),
        latency_seconds=operations.latency_seconds,
        cost_per_report=operations.cost_per_report,
        prompting_parity=parity.decision,
        sec_insufficiency_count=operations.sec_insufficiency_count,
    )
    return ReadinessRun(
        parity=parity,
        stability=stability,
        inputs=inputs,
        assessment=assess_readiness(inputs=inputs, policy=policy),
    )


def _validate_case_sets(
    mechanical_cases: tuple[RegressionCase, ...],
    judgment_cases: tuple[RegressionCase, ...],
) -> None:
    if len(mechanical_cases) != 20 or {item.category for item in mechanical_cases} != {
        "mechanical"
    }:
        raise ValueError("readiness evaluation requires exactly 20 mechanical cases")
    if len(judgment_cases) != 10 or {item.category for item in judgment_cases} != {
        "judgment"
    }:
        raise ValueError("readiness evaluation requires exactly 10 judgment cases")
    case_ids = [item.case_id for item in (*mechanical_cases, *judgment_cases)]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("readiness evaluation case IDs must be unique")


def _expected_outcomes(
    *,
    mechanical_cases: tuple[RegressionCase, ...],
    judgment_cases: tuple[RegressionCase, ...],
) -> dict[str, tuple[str, str]]:
    expected: dict[str, tuple[str, str]] = {}
    for case in (*mechanical_cases, *judgment_cases):
        if case.expected_unclassified_statement_ids:
            outcome = "unclassified"
        elif len(case.expected_verdicts) == 1:
            outcome = case.expected_verdicts[0][1].value
        else:
            raise ValueError("each readiness case must have one expected outcome")
        expected[case.case_id] = (case.category, outcome)
    return expected


def _false_positive_defeat_rate(cases: tuple[PromptingParityCase, ...]) -> float:
    return sum(
        item.quantify_outcome == ClaimVerdict.DEFEATED.value
        and item.expected_outcome != ClaimVerdict.DEFEATED.value
        for item in cases
    ) / len(cases)
