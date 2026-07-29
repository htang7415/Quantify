"""Offline repeated-run stability scoring for scheduled parity artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from quantify.engine import ClaimVerdict

from .parity import PromptingParityArtifact, PromptingParityCase


_PATHS = ("prompt_only", "quantify")
_CATEGORY_COUNTS = {"mechanical": 20, "judgment": 10}


@dataclass(frozen=True, slots=True)
class RepeatedRunPathStability:
    """Outcome stability for one identically pinned path across two trials."""

    model: str
    prompt_hash: str
    temperature: float
    exact_report_level_agreement: bool
    statement_level_agreement: float
    classified_unclassified_transitions: int
    verified_defeated_flips: int
    mechanical_verified_defeated_flips: int


@dataclass(frozen=True, slots=True)
class RepeatedRunStability:
    """Replayable two-trial result for the fixed 20 mechanical + 10 judgment corpus."""

    artifact_version: str
    case_count: int
    trial_count: int
    prompt_only: RepeatedRunPathStability
    quantify: RepeatedRunPathStability


def evaluate_repeated_run_stability(
    *, first_trial: PromptingParityArtifact, second_trial: PromptingParityArtifact
) -> RepeatedRunStability:
    """Compare exact same-corpus parity artifacts without invoking a provider."""

    first_cases = _indexed_cases(artifact=first_trial)
    second_cases = _indexed_cases(artifact=second_trial)
    if set(first_cases) != set(second_cases):
        raise ValueError("stability trials must contain the same frozen case IDs")
    if any(
        first_cases[case_id].category != second_cases[case_id].category
        or first_cases[case_id].expected_outcome
        != second_cases[case_id].expected_outcome
        for case_id in first_cases
    ):
        raise ValueError("stability trials disagree about frozen case metadata")

    return RepeatedRunStability(
        artifact_version="1.0.0",
        case_count=len(first_cases),
        trial_count=2,
        prompt_only=_evaluate_path(
            path="prompt_only", first_trial=first_trial, second_trial=second_trial
        ),
        quantify=_evaluate_path(
            path="quantify", first_trial=first_trial, second_trial=second_trial
        ),
    )


def repeated_run_stability_as_dict(*, stability: RepeatedRunStability) -> dict:
    """Return the versioned scheduled-evaluation artifact in canonical JSON form."""

    return asdict(stability)


def load_repeated_run_stability(*, path: Path) -> RepeatedRunStability:
    """Load a strict, provider-free stability measurement artifact."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        stability = RepeatedRunStability(
            artifact_version=payload["artifact_version"],
            case_count=payload["case_count"],
            trial_count=payload["trial_count"],
            prompt_only=_path_stability_from_payload(payload["prompt_only"]),
            quantify=_path_stability_from_payload(payload["quantify"]),
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid repeated-run stability artifact") from error
    _validate_stability(stability=stability)
    return stability


def _indexed_cases(*, artifact: PromptingParityArtifact) -> dict[str, PromptingParityCase]:
    cases = {item.case_id: item for item in artifact.cases}
    if len(cases) != 30 or len(cases) != len(artifact.cases):
        raise ValueError("stability trials require exactly 30 unique cases")
    actual_counts = {
        category: sum(item.category == category for item in cases.values())
        for category in _CATEGORY_COUNTS
    }
    if actual_counts != _CATEGORY_COUNTS:
        raise ValueError("stability trials require 20 mechanical and 10 judgment cases")
    return cases


def _evaluate_path(
    *,
    path: str,
    first_trial: PromptingParityArtifact,
    second_trial: PromptingParityArtifact,
) -> RepeatedRunPathStability:
    first_metadata = _path_metadata(artifact=first_trial, path=path)
    second_metadata = _path_metadata(artifact=second_trial, path=path)
    if first_metadata != second_metadata:
        raise ValueError(f"stability trials must pin identical {path} metadata")
    first_cases = _indexed_cases(artifact=first_trial)
    second_cases = _indexed_cases(artifact=second_trial)
    first_outcomes = {
        case_id: _outcome(case=case, path=path) for case_id, case in first_cases.items()
    }
    second_outcomes = {
        case_id: _outcome(case=case, path=path)
        for case_id, case in second_cases.items()
    }
    matching = sum(
        first_outcomes[case_id] == second_outcomes[case_id]
        for case_id in first_outcomes
    )
    transitions = sum(
        (first_outcomes[case_id] == "unclassified")
        != (second_outcomes[case_id] == "unclassified")
        for case_id in first_outcomes
    )
    flips = sum(
        _is_verified_defeated_flip(
            first=first_outcomes[case_id], second=second_outcomes[case_id]
        )
        for case_id in first_outcomes
    )
    mechanical_flips = sum(
        _is_verified_defeated_flip(
            first=first_outcomes[case_id], second=second_outcomes[case_id]
        )
        for case_id in first_outcomes
        if first_cases[case_id].category == "mechanical"
    )
    return RepeatedRunPathStability(
        model=first_metadata[0],
        prompt_hash=first_metadata[1],
        temperature=first_metadata[2],
        exact_report_level_agreement=matching == len(first_outcomes),
        statement_level_agreement=matching / len(first_outcomes),
        classified_unclassified_transitions=transitions,
        verified_defeated_flips=flips,
        mechanical_verified_defeated_flips=mechanical_flips,
    )


def _path_metadata(
    *, artifact: PromptingParityArtifact, path: str
) -> tuple[str, str, float]:
    if path == "prompt_only":
        return artifact.model, artifact.prompt_hash, artifact.temperature
    if path == "quantify":
        return (
            artifact.quantify_model or artifact.model,
            artifact.quantify_prompt_hash or artifact.prompt_hash,
            artifact.quantify_temperature
            if artifact.quantify_temperature is not None
            else artifact.temperature,
        )
    raise AssertionError(f"unknown stability path: {path}")


def _outcome(*, case: PromptingParityCase, path: str) -> str:
    if path == "prompt_only":
        return case.prompt_only_outcome
    if path == "quantify":
        return case.quantify_outcome
    raise AssertionError(f"unknown stability path: {path}")


def _is_verified_defeated_flip(*, first: str, second: str) -> bool:
    return {first, second} == {
        ClaimVerdict.VERIFIED.value,
        ClaimVerdict.DEFEATED.value,
    }


def _path_stability_from_payload(payload: object) -> RepeatedRunPathStability:
    if not isinstance(payload, dict):
        raise ValueError("stability path must be an object")
    return RepeatedRunPathStability(
        model=payload["model"],
        prompt_hash=payload["prompt_hash"],
        temperature=payload["temperature"],
        exact_report_level_agreement=payload["exact_report_level_agreement"],
        statement_level_agreement=payload["statement_level_agreement"],
        classified_unclassified_transitions=payload[
            "classified_unclassified_transitions"
        ],
        verified_defeated_flips=payload["verified_defeated_flips"],
        mechanical_verified_defeated_flips=payload[
            "mechanical_verified_defeated_flips"
        ],
    )


def _validate_stability(*, stability: RepeatedRunStability) -> None:
    if stability.artifact_version != "1.0.0":
        raise ValueError("unsupported repeated-run stability artifact version")
    if stability.case_count != 30 or stability.trial_count != 2:
        raise ValueError("stability artifact requires two trials of 30 cases")
    for path in _PATHS:
        measurement = getattr(stability, path)
        if not measurement.model or not measurement.prompt_hash:
            raise ValueError("stability artifact requires pinned path metadata")
        if isinstance(measurement.temperature, bool) or not isinstance(
            measurement.temperature, (int, float)
        ):
            raise ValueError("stability artifact requires numeric temperature")
        if not isinstance(measurement.exact_report_level_agreement, bool):
            raise ValueError("stability artifact requires boolean exact agreement")
        if isinstance(measurement.statement_level_agreement, bool) or not isinstance(
            measurement.statement_level_agreement, (int, float)
        ):
            raise ValueError("stability artifact requires numeric measurements")
        counts = (
            measurement.classified_unclassified_transitions,
            measurement.verified_defeated_flips,
            measurement.mechanical_verified_defeated_flips,
        )
        if any(isinstance(item, bool) or not isinstance(item, int) for item in counts):
            raise ValueError("stability artifact requires integer transition counts")
        if not 0.0 <= measurement.statement_level_agreement <= 1.0:
            raise ValueError("stability statement agreement must be between zero and one")
        if measurement.exact_report_level_agreement != (
            measurement.statement_level_agreement == 1.0
        ):
            raise ValueError("stability exact agreement must match statement agreement")
        if any(item < 0 or item > stability.case_count for item in counts):
            raise ValueError("stability transition counts are outside the case range")
        if not (
            0
            <= measurement.mechanical_verified_defeated_flips
            <= measurement.verified_defeated_flips
            and measurement.mechanical_verified_defeated_flips
            <= _CATEGORY_COUNTS["mechanical"]
        ):
            raise ValueError("stability mechanical flips must be within total flips")
