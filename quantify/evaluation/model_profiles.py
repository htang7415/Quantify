"""Pinned, cost-bounded model profiles for scheduled evaluation only."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class EvaluationExecutionMode(StrEnum):
    BATCH = "batch"


@dataclass(frozen=True, slots=True)
class EvaluationModelProfile:
    profile_version: str
    provider: str
    model: str
    execution_mode: EvaluationExecutionMode
    temperature: float
    input_price_per_million_usd: float
    output_price_per_million_usd: float
    max_input_tokens_per_request: int
    max_output_tokens_per_request: int
    max_total_cost_usd: float
    pricing_source_url: str


@dataclass(frozen=True, slots=True)
class EvaluationCostEstimate:
    request_count: int
    input_tokens: int
    output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    within_budget: bool


def load_evaluation_model_profile(*, path: Path) -> EvaluationModelProfile:
    """Load a versioned profile before any provider request is authorized."""

    payload = json.loads(path.read_text())
    if payload.get("profile_version") != "1.0.0":
        raise ValueError("unsupported evaluation model-profile version")
    try:
        profile = EvaluationModelProfile(
            profile_version=payload["profile_version"],
            provider=payload["provider"],
            model=payload["model"],
            execution_mode=EvaluationExecutionMode(payload["execution_mode"]),
            temperature=payload["temperature"],
            input_price_per_million_usd=payload["input_price_per_million_usd"],
            output_price_per_million_usd=payload["output_price_per_million_usd"],
            max_input_tokens_per_request=payload["max_input_tokens_per_request"],
            max_output_tokens_per_request=payload["max_output_tokens_per_request"],
            max_total_cost_usd=payload["max_total_cost_usd"],
            pricing_source_url=payload["pricing_source_url"],
        )
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError("invalid evaluation model profile") from error
    if not profile.provider or not profile.model or not profile.pricing_source_url:
        raise ValueError("evaluation model profile requires provider, model, and pricing source")
    numeric_values = (
        profile.temperature,
        profile.input_price_per_million_usd,
        profile.output_price_per_million_usd,
        profile.max_total_cost_usd,
    )
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numeric_values):
        raise ValueError("evaluation model profile contains non-numeric pricing")
    if not 0.0 <= profile.temperature <= 2.0:
        raise ValueError("evaluation temperature must be between zero and two")
    if (
        profile.input_price_per_million_usd < 0
        or profile.output_price_per_million_usd < 0
        or profile.max_total_cost_usd <= 0
        or profile.max_input_tokens_per_request <= 0
        or profile.max_output_tokens_per_request <= 0
    ):
        raise ValueError("evaluation model profile requires positive limits and pricing")
    return profile


def estimate_evaluation_cost(
    *,
    profile: EvaluationModelProfile,
    case_count: int = 30,
    paths_per_case: int = 2,
) -> EvaluationCostEstimate:
    """Calculate the maximum token-price exposure before the scheduled run."""

    if case_count <= 0 or paths_per_case <= 0:
        raise ValueError("case count and paths per case must be positive")
    request_count = case_count * paths_per_case
    input_tokens = request_count * profile.max_input_tokens_per_request
    output_tokens = request_count * profile.max_output_tokens_per_request
    input_cost = input_tokens / 1_000_000 * profile.input_price_per_million_usd
    output_cost = output_tokens / 1_000_000 * profile.output_price_per_million_usd
    total_cost = input_cost + output_cost
    return EvaluationCostEstimate(
        request_count=request_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=total_cost,
        within_budget=total_cost <= profile.max_total_cost_usd,
    )


def require_cost_within_budget(*, estimate: EvaluationCostEstimate) -> None:
    """Fail before a paid run when its declared token envelope exceeds the cap."""

    if not estimate.within_budget:
        raise ValueError("evaluation token envelope exceeds the pinned cost budget")
