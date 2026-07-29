from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from quantify.evaluation import (
    PromptingParityArtifact,
    PromptingParityCase,
    evaluate_repeated_run_stability,
    load_repeated_run_stability,
    repeated_run_stability_as_dict,
)
from quantify.evaluation.stability_cli import main


def _trial(*, quantify_first_outcome: str = "verified") -> PromptingParityArtifact:
    cases = tuple(
        PromptingParityCase(
            case_id=f"mechanical-{index:02d}",
            category="mechanical",
            expected_outcome="verified",
            prompt_only_outcome="verified",
            quantify_outcome=(quantify_first_outcome if index == 0 else "verified"),
        )
        for index in range(20)
    ) + tuple(
        PromptingParityCase(
            case_id=f"judgment-{index:02d}",
            category="judgment",
            expected_outcome="unclassified",
            prompt_only_outcome="unclassified",
            quantify_outcome="unclassified",
        )
        for index in range(10)
    )
    return PromptingParityArtifact(
        artifact_version="1.1.0",
        model="gemini-3.1-flash-lite",
        prompt_hash="prompt-only-hash",
        temperature=0.0,
        quantify_model="gemini-3.1-flash-lite",
        quantify_prompt_hash="quantify-hash",
        quantify_temperature=0.0,
        cases=cases,
    )


def test_stability_scores_identical_pinned_trials_and_round_trips(tmp_path: Path) -> None:
    stability = evaluate_repeated_run_stability(
        first_trial=_trial(), second_trial=_trial()
    )
    path = tmp_path / "stability.json"
    path.write_text(json.dumps(repeated_run_stability_as_dict(stability=stability)))

    loaded = load_repeated_run_stability(path=path)

    assert loaded.quantify.exact_report_level_agreement is True
    assert loaded.quantify.statement_level_agreement == 1.0
    assert loaded.quantify.classified_unclassified_transitions == 0
    assert loaded.quantify.mechanical_verified_defeated_flips == 0


def test_stability_exposes_a_mechanical_verified_defeated_flip() -> None:
    stability = evaluate_repeated_run_stability(
        first_trial=_trial(), second_trial=_trial(quantify_first_outcome="defeated")
    )

    assert stability.quantify.exact_report_level_agreement is False
    assert stability.quantify.statement_level_agreement == pytest.approx(29 / 30)
    assert stability.quantify.verified_defeated_flips == 1
    assert stability.quantify.mechanical_verified_defeated_flips == 1


def test_stability_rejects_changed_pinned_path_metadata() -> None:
    second = replace(_trial(), quantify_prompt_hash="changed-quantify-hash")

    with pytest.raises(ValueError, match="identical quantify metadata"):
        evaluate_repeated_run_stability(first_trial=_trial(), second_trial=second)


def test_stability_cli_writes_a_versioned_artifact(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    output = tmp_path / "stability.json"
    first.write_text(json.dumps({
        "artifact_version": "1.1.0",
        "run": {
            "prompt_only": {"model": "gemini-3.1-flash-lite", "prompt_hash": "prompt-only-hash", "temperature": 0.0},
            "quantify": {"model": "gemini-3.1-flash-lite", "prompt_hash": "quantify-hash", "temperature": 0.0},
        },
        "cases": [
            {
                "case_id": item.case_id,
                "category": item.category,
                "expected_outcome": item.expected_outcome,
                "prompt_only_outcome": item.prompt_only_outcome,
                "quantify_outcome": item.quantify_outcome,
            }
            for item in _trial().cases
        ],
    }))
    second.write_text(first.read_text())

    assert main(["--first-trial", str(first), "--second-trial", str(second), "--output", str(output)]) == 0

    assert json.loads(output.read_text())["quantify"]["statement_level_agreement"] == 1.0
