"""Versioned, deterministic technical readiness gate for Quantify Core."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .parity import PromptingParityDecision


class ReadinessDecision(StrEnum):
    PROCEED = "proceed"
    PAUSE = "pause"


@dataclass(frozen=True, slots=True)
class ReadinessPolicy:
    """Explicit acceptance criteria; adjust only through a versioned policy change."""

    policy_version: str = "1.1.0"
    max_mechanical_false_positive_rate: float = 0.0
    max_verified_defeated_flips: int = 0
    max_judgment_false_positive_rate: float = 0.05
    max_unclassified_fraction: float = 0.50
    max_agent_resolution_rate: float = 0.10
    max_latency_seconds: float = 5.0
    max_cost_per_report: float = 0.05
    max_sec_insufficiency_count: int = 0


@dataclass(frozen=True, slots=True)
class ReadinessInputs:
    mechanical_false_positive_rate: float
    verified_defeated_flips: int
    judgment_false_positive_rate: float
    unclassified_fraction: float
    agent_resolution_rate: float
    latency_seconds: float
    cost_per_report: float
    prompting_parity: PromptingParityDecision
    sec_insufficiency_count: int


@dataclass(frozen=True, slots=True)
class ReadinessAssessment:
    decision: ReadinessDecision
    policy_version: str
    blockers: tuple[str, ...]


def assess_readiness(
    *, inputs: ReadinessInputs, policy: ReadinessPolicy = ReadinessPolicy()
) -> ReadinessAssessment:
    """Return a conservative commercial decision from complete measured inputs."""

    _validate_inputs(inputs)
    blockers: list[str] = []
    if inputs.mechanical_false_positive_rate > policy.max_mechanical_false_positive_rate:
        blockers.append("mechanical_false_positive_rate")
    if inputs.verified_defeated_flips > policy.max_verified_defeated_flips:
        blockers.append("verified_defeated_instability")
    if inputs.judgment_false_positive_rate > policy.max_judgment_false_positive_rate:
        blockers.append("judgment_false_positive_rate")
    if inputs.unclassified_fraction > policy.max_unclassified_fraction:
        blockers.append("unclassified_fraction")
    if inputs.agent_resolution_rate > policy.max_agent_resolution_rate:
        blockers.append("agent_resolution_rate")
    if inputs.latency_seconds > policy.max_latency_seconds:
        blockers.append("latency_seconds")
    if inputs.cost_per_report > policy.max_cost_per_report:
        blockers.append("cost_per_report")
    if inputs.prompting_parity is PromptingParityDecision.PROMPTING_ADVANTAGE:
        blockers.append("prompting_advantage")
    if inputs.sec_insufficiency_count > policy.max_sec_insufficiency_count:
        blockers.append("sec_entity_fact_insufficiency")
    return ReadinessAssessment(
        decision=ReadinessDecision.PAUSE if blockers else ReadinessDecision.PROCEED,
        policy_version=policy.policy_version,
        blockers=tuple(blockers),
    )


def _validate_inputs(inputs: ReadinessInputs) -> None:
    for value in (
        inputs.mechanical_false_positive_rate,
        inputs.judgment_false_positive_rate,
        inputs.unclassified_fraction,
        inputs.agent_resolution_rate,
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError("rates must be between zero and one")
    if min(
        inputs.verified_defeated_flips,
        inputs.latency_seconds,
        inputs.cost_per_report,
        inputs.sec_insufficiency_count,
    ) < 0:
        raise ValueError("readiness counts, latency, and cost cannot be negative")
