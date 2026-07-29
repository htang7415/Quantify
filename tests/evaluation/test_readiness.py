from __future__ import annotations

from quantify.evaluation import (
    PromptingParityDecision,
    ReadinessDecision,
    ReadinessInputs,
    assess_readiness,
)


def _inputs(**changes) -> ReadinessInputs:
    values = {
        "mechanical_false_positive_rate": 0.0,
        "verified_defeated_flips": 0,
        "judgment_false_positive_rate": 0.0,
        "unclassified_fraction": 0.25,
        "agent_resolution_rate": 0.05,
        "latency_seconds": 1.0,
        "cost_per_report": 0.01,
        "prompting_parity": PromptingParityDecision.QUANTIFY_ADVANTAGE,
        "sec_insufficiency_count": 0,
    }
    values.update(changes)
    return ReadinessInputs(**values)


def test_readiness_proceeds_only_when_every_gate_is_green() -> None:
    assessment = assess_readiness(inputs=_inputs())

    assert assessment.decision is ReadinessDecision.PROCEED
    assert assessment.blockers == ()
    assert assessment.policy_version == "1.0.0"


def test_readiness_pauses_for_material_blockers() -> None:
    assessment = assess_readiness(
        inputs=_inputs(
            mechanical_false_positive_rate=0.01,
            prompting_parity=PromptingParityDecision.PROMPTING_ADVANTAGE,
            sec_insufficiency_count=1,
        )
    )

    assert assessment.decision is ReadinessDecision.PAUSE
    assert assessment.blockers == (
        "mechanical_false_positive_rate",
        "prompting_advantage",
        "sec_entity_fact_insufficiency",
    )
