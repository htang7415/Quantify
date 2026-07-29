from __future__ import annotations

import json

import pytest

from quantify.evaluation import (
    PromptingParityCase,
    PromptingParityDecision,
    evaluate_prompting_parity,
    load_prompting_parity_artifact,
)


def _cases(*, quantify_extra_correct: int = 0) -> tuple[PromptingParityCase, ...]:
    cases = []
    for index in range(20):
        expected = "verified"
        prompt_only = "unsupported" if index < quantify_extra_correct else expected
        cases.append(
            PromptingParityCase(
                case_id=f"mechanical-{index}",
                category="mechanical",
                expected_outcome=expected,
                prompt_only_outcome=prompt_only,
                quantify_outcome=expected,
            )
        )
    for index in range(10):
        cases.append(
            PromptingParityCase(
                case_id=f"judgment-{index}",
                category="judgment",
                expected_outcome="unclassified",
                prompt_only_outcome="unclassified",
                quantify_outcome="unclassified",
            )
        )
    return tuple(cases)


def test_parity_scores_the_exact_frozen_corpus_and_detects_quantify_advantage() -> None:
    summary = evaluate_prompting_parity(cases=_cases(quantify_extra_correct=3))

    assert summary.case_count == 30
    assert summary.quantify_unique_catches == 3
    assert summary.prompt_only_unique_catches == 0
    assert summary.decision is PromptingParityDecision.QUANTIFY_ADVANTAGE


def test_parity_rejects_partial_or_pooled_case_sets() -> None:
    with pytest.raises(ValueError, match="exactly 30"):
        evaluate_prompting_parity(cases=_cases()[:-1])


def test_parity_artifact_requires_pinned_replay_metadata(tmp_path) -> None:
    payload = {
        "artifact_version": "1.0.0",
        "run": {"model": "pinned-fixture-v1", "prompt_hash": "abc", "temperature": 0},
        "cases": [
            {
                "case_id": item.case_id,
                "category": item.category,
                "expected_outcome": item.expected_outcome,
                "prompt_only_outcome": item.prompt_only_outcome,
                "quantify_outcome": item.quantify_outcome,
            }
            for item in _cases()
        ],
    }
    path = tmp_path / "parity.json"
    path.write_text(json.dumps(payload))

    artifact = load_prompting_parity_artifact(path)

    assert artifact.model == "pinned-fixture-v1"
    assert evaluate_prompting_parity(cases=artifact.cases).decision is PromptingParityDecision.PRACTICAL_PARITY

    payload["run"]["model"] = ""
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="pinned model"):
        load_prompting_parity_artifact(path)
