from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantify.evaluation import (
    OperationalMeasurements,
    PromptingParityArtifact,
    PromptingParityCase,
    ReadinessDecision,
    run_readiness_evaluation,
)
from quantify.evaluation import case_from_json
from tests.conftest import load_snapshot


CASE_ROOT = Path(__file__).parents[2] / "fixtures" / "cases"


def _load_cases(filename: str):
    payload = json.loads((CASE_ROOT / filename).read_text())
    return tuple(
        case_from_json(
            item=item,
            snapshot=load_snapshot(
                item["snapshot_fixture"],
                allow_conflicting_evidence=item.get("allow_conflicting_evidence", False),
            ),
        )
        for item in payload["cases"]
    )


def _artifact(*, false_positive: bool = False) -> PromptingParityArtifact:
    cases = (*_load_cases("mechanical_v1.json"), *_load_cases("judgment_v1.json"))
    parity_cases = []
    for index, case in enumerate(cases):
        expected = (
            "unclassified"
            if case.expected_unclassified_statement_ids
            else case.expected_verdicts[0][1].value
        )
        parity_cases.append(
            PromptingParityCase(
                case_id=case.case_id,
                category=case.category,
                expected_outcome=expected,
                prompt_only_outcome=(
                    "requires_agent_resolution" if index < 3 else expected
                ),
                quantify_outcome=(
                    "defeated" if false_positive and index == 0 else expected
                ),
            )
        )
    return PromptingParityArtifact(
        artifact_version="1.0.0",
        model="pinned-fixture-v1",
        prompt_hash="fixture-prompt-v1",
        temperature=0.0,
        cases=tuple(parity_cases),
    )


def _operations() -> OperationalMeasurements:
    return OperationalMeasurements(
        verified_defeated_flips=0,
        latency_seconds=1.0,
        cost_per_report=0.01,
        sec_insufficiency_count=0,
    )


def test_readiness_run_joins_real_frozen_cases_to_pinned_parity_artifact() -> None:
    run = run_readiness_evaluation(
        mechanical_cases=_load_cases("mechanical_v1.json"),
        judgment_cases=_load_cases("judgment_v1.json"),
        parity_artifact=_artifact(),
        operations=_operations(),
    )

    assert run.parity.case_count == 30
    assert run.parity.quantify_unique_catches == 3
    assert run.inputs.mechanical_false_positive_rate == 0.0
    assert run.inputs.unclassified_fraction == pytest.approx(10 / 30)
    assert run.inputs.agent_resolution_rate == 0.0
    assert run.assessment.decision is ReadinessDecision.PROCEED


def test_readiness_run_fails_closed_when_artifact_mismatches_the_frozen_corpus() -> None:
    artifact = _artifact()
    bad_artifact = PromptingParityArtifact(
        artifact_version=artifact.artifact_version,
        model=artifact.model,
        prompt_hash=artifact.prompt_hash,
        temperature=artifact.temperature,
        cases=(
            PromptingParityCase(
                case_id="wrong-case-id",
                category=artifact.cases[0].category,
                expected_outcome=artifact.cases[0].expected_outcome,
                prompt_only_outcome=artifact.cases[0].prompt_only_outcome,
                quantify_outcome=artifact.cases[0].quantify_outcome,
            ),
            *artifact.cases[1:],
        ),
    )

    with pytest.raises(ValueError, match="case IDs"):
        run_readiness_evaluation(
            mechanical_cases=_load_cases("mechanical_v1.json"),
            judgment_cases=_load_cases("judgment_v1.json"),
            parity_artifact=bad_artifact,
            operations=_operations(),
        )


def test_readiness_run_turns_a_model_path_false_accusation_into_a_pause() -> None:
    run = run_readiness_evaluation(
        mechanical_cases=_load_cases("mechanical_v1.json"),
        judgment_cases=_load_cases("judgment_v1.json"),
        parity_artifact=_artifact(false_positive=True),
        operations=_operations(),
    )

    assert run.inputs.mechanical_false_positive_rate == pytest.approx(1 / 20)
    assert run.assessment.decision is ReadinessDecision.PAUSE
    assert "mechanical_false_positive_rate" in run.assessment.blockers
