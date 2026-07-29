"""Offline scoring for a pinned prompt-only versus Quantify comparison."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from quantify.engine import ClaimVerdict


_OUTCOMES = {*(item.value for item in ClaimVerdict), "unclassified"}
_CATEGORY_COUNTS = {"mechanical": 20, "judgment": 10}


class PromptingParityDecision(StrEnum):
    QUANTIFY_ADVANTAGE = "quantify_advantage"
    PRACTICAL_PARITY = "practical_parity"
    PROMPTING_ADVANTAGE = "prompting_advantage"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class PromptingParityCase:
    """One frozen case with results from both independently pinned paths."""

    case_id: str
    category: str
    expected_outcome: str
    prompt_only_outcome: str
    quantify_outcome: str


@dataclass(frozen=True, slots=True)
class PromptingParityArtifact:
    artifact_version: str
    model: str
    prompt_hash: str
    temperature: float
    cases: tuple[PromptingParityCase, ...]
    quantify_model: str | None = None
    quantify_prompt_hash: str | None = None
    quantify_temperature: float | None = None


@dataclass(frozen=True, slots=True)
class PromptingParitySummary:
    case_count: int
    quantify_unique_catches: int
    prompt_only_unique_catches: int
    quantify_false_positive_defeats: int
    prompt_only_false_positive_defeats: int
    decision: PromptingParityDecision


def load_prompting_parity_artifact(path: Path) -> PromptingParityArtifact:
    """Load a manually/scheduled generated artifact; this function never calls a model."""

    payload = json.loads(path.read_text())
    artifact_version = payload.get("artifact_version")
    if artifact_version not in {"1.0.0", "1.1.0"}:
        raise ValueError("unsupported prompting-parity artifact version")
    run = payload.get("run")
    if not isinstance(run, dict):
        raise ValueError("prompting-parity artifact requires run metadata")
    if artifact_version == "1.0.0":
        prompt_only_run = run
        quantify_run = run
    else:
        prompt_only_run = run.get("prompt_only")
        quantify_run = run.get("quantify")
        if not isinstance(prompt_only_run, dict) or not isinstance(quantify_run, dict):
            raise ValueError("1.1.0 parity artifact requires both path run metadata")
    model, prompt_hash, temperature = _validate_run_metadata(prompt_only_run)
    quantify_model, quantify_prompt_hash, quantify_temperature = _validate_run_metadata(
        quantify_run
    )
    try:
        cases = tuple(
            PromptingParityCase(
                case_id=item["case_id"],
                category=item["category"],
                expected_outcome=item["expected_outcome"],
                prompt_only_outcome=item["prompt_only_outcome"],
                quantify_outcome=item["quantify_outcome"],
            )
            for item in payload["cases"]
        )
    except (KeyError, TypeError) as error:
        raise ValueError("invalid prompting-parity case") from error
    _validate_cases(cases)
    return PromptingParityArtifact(
        artifact_version=artifact_version,
        model=model,
        prompt_hash=prompt_hash,
        temperature=float(temperature),
        cases=cases,
        quantify_model=quantify_model,
        quantify_prompt_hash=quantify_prompt_hash,
        quantify_temperature=float(quantify_temperature),
    )


def evaluate_prompting_parity(
    *, cases: tuple[PromptingParityCase, ...]
) -> PromptingParitySummary:
    """Score the exact 20 mechanical + 10 judgment comparison without pooling it."""

    _validate_cases(cases)
    quantify_unique = sum(
        item.quantify_outcome == item.expected_outcome
        and item.prompt_only_outcome != item.expected_outcome
        for item in cases
    )
    prompt_unique = sum(
        item.prompt_only_outcome == item.expected_outcome
        and item.quantify_outcome != item.expected_outcome
        for item in cases
    )
    quantify_fp = sum(
        item.quantify_outcome == ClaimVerdict.DEFEATED.value
        and item.expected_outcome != ClaimVerdict.DEFEATED.value
        for item in cases
    )
    prompt_fp = sum(
        item.prompt_only_outcome == ClaimVerdict.DEFEATED.value
        and item.expected_outcome != ClaimVerdict.DEFEATED.value
        for item in cases
    )
    if quantify_unique >= 3 and quantify_fp <= prompt_fp + 1:
        decision = PromptingParityDecision.QUANTIFY_ADVANTAGE
    elif prompt_unique >= quantify_unique + 3 and prompt_fp <= quantify_fp:
        decision = PromptingParityDecision.PROMPTING_ADVANTAGE
    elif abs(quantify_unique - prompt_unique) <= 1:
        decision = PromptingParityDecision.PRACTICAL_PARITY
    else:
        decision = PromptingParityDecision.INCONCLUSIVE
    return PromptingParitySummary(
        case_count=len(cases),
        quantify_unique_catches=quantify_unique,
        prompt_only_unique_catches=prompt_unique,
        quantify_false_positive_defeats=quantify_fp,
        prompt_only_false_positive_defeats=prompt_fp,
        decision=decision,
    )


def _validate_cases(cases: tuple[PromptingParityCase, ...]) -> None:
    if len(cases) != sum(_CATEGORY_COUNTS.values()):
        raise ValueError("prompting parity requires exactly 30 frozen cases")
    if len({item.case_id for item in cases}) != len(cases):
        raise ValueError("prompting parity case IDs must be unique")
    actual_counts = {
        category: sum(item.category == category for item in cases)
        for category in _CATEGORY_COUNTS
    }
    if actual_counts != _CATEGORY_COUNTS:
        raise ValueError("prompting parity requires 20 mechanical and 10 judgment cases")
    for item in cases:
        if (
            item.expected_outcome not in _OUTCOMES
            or item.prompt_only_outcome not in _OUTCOMES
            or item.quantify_outcome not in _OUTCOMES
        ):
            raise ValueError("prompting parity contains an unsupported outcome")


def _validate_run_metadata(run: object) -> tuple[str, str, float]:
    if not isinstance(run, dict):
        raise ValueError("prompting-parity artifact requires run metadata")
    model = run.get("model")
    prompt_hash = run.get("prompt_hash")
    temperature = run.get("temperature")
    if not isinstance(model, str) or not model:
        raise ValueError("prompting-parity artifact requires a pinned model")
    if not isinstance(prompt_hash, str) or not prompt_hash:
        raise ValueError("prompting-parity artifact requires a prompt hash")
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        raise ValueError("prompting-parity artifact requires numeric temperature")
    return model, prompt_hash, float(temperature)
