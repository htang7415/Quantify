"""Strict reconciliation of opaque provider outputs into a parity artifact."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .parity import PromptingParityArtifact, PromptingParityCase, evaluate_prompting_parity
from .parity_worklist import PromptingParityReference


@dataclass(frozen=True, slots=True)
class ModelOutcomeArtifact:
    path: str
    model: str
    prompt_hash: str
    temperature: float
    outcomes: tuple[tuple[str, str], ...]


def load_model_outcome_artifact(*, path: Path) -> ModelOutcomeArtifact:
    """Load one external result file without reference labels or case IDs."""

    payload = json.loads(path.read_text())
    if payload.get("artifact_version") != "1.0.0":
        raise ValueError("unsupported model-outcome artifact version")
    execution_path = payload.get("path")
    run = payload.get("run")
    if execution_path not in {"prompt_only", "quantify"}:
        raise ValueError("model-outcome artifact has an unsupported path")
    if not isinstance(run, dict):
        raise ValueError("model-outcome artifact requires run metadata")
    model = run.get("model")
    prompt_hash = run.get("prompt_hash")
    temperature = run.get("temperature")
    if not isinstance(model, str) or not model:
        raise ValueError("model-outcome artifact requires a pinned model")
    if not isinstance(prompt_hash, str) or not prompt_hash:
        raise ValueError("model-outcome artifact requires a prompt hash")
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        raise ValueError("model-outcome artifact requires numeric temperature")
    try:
        outcomes = tuple(
            (item["request_id"], item["outcome"]) for item in payload["outcomes"]
        )
    except (KeyError, TypeError) as error:
        raise ValueError("invalid model-outcome artifact") from error
    if len(outcomes) != 30:
        raise ValueError("model-outcome artifact requires exactly 30 outcomes")
    if len({request_id for request_id, _ in outcomes}) != len(outcomes):
        raise ValueError("model-outcome request IDs must be unique")
    if any(not isinstance(request_id, str) or not isinstance(outcome, str) for request_id, outcome in outcomes):
        raise ValueError("model outcomes must contain string request IDs and outcomes")
    return ModelOutcomeArtifact(
        path=execution_path,
        model=model,
        prompt_hash=prompt_hash,
        temperature=float(temperature),
        outcomes=outcomes,
    )


def compile_prompting_parity_artifact(
    *,
    references: tuple[PromptingParityReference, ...],
    prompt_only: ModelOutcomeArtifact,
    quantify: ModelOutcomeArtifact,
) -> PromptingParityArtifact:
    """Join private references to complete provider outputs and validate all 30 cases."""

    if prompt_only.path != "prompt_only" or quantify.path != "quantify":
        raise ValueError("outcome artifacts must be supplied in their named paths")
    if prompt_only.model != quantify.model or prompt_only.temperature != quantify.temperature:
        raise ValueError("parity paths must use the same pinned model and temperature")
    if prompt_only.prompt_hash == quantify.prompt_hash:
        raise ValueError("parity paths must use distinct prompt hashes")
    expected_request_ids = {item.request_id for item in references}
    prompt_by_id = dict(prompt_only.outcomes)
    quantify_by_id = dict(quantify.outcomes)
    if set(prompt_by_id) != expected_request_ids or set(quantify_by_id) != expected_request_ids:
        raise ValueError("model outcomes do not match the private reference mapping")
    artifact = PromptingParityArtifact(
        artifact_version="1.1.0",
        model=prompt_only.model,
        prompt_hash=prompt_only.prompt_hash,
        temperature=prompt_only.temperature,
        quantify_model=quantify.model,
        quantify_prompt_hash=quantify.prompt_hash,
        quantify_temperature=quantify.temperature,
        cases=tuple(
            PromptingParityCase(
                case_id=item.case_id,
                category=item.category,
                expected_outcome=item.expected_outcome,
                prompt_only_outcome=prompt_by_id[item.request_id],
                quantify_outcome=quantify_by_id[item.request_id],
            )
            for item in sorted(references, key=lambda item: item.case_id)
        ),
    )
    evaluate_prompting_parity(cases=artifact.cases)
    return artifact


def prompting_parity_artifact_as_dict(*, artifact: PromptingParityArtifact) -> dict:
    """Canonical JSON-ready v1.1 artifact with provenance for both paths."""

    return {
        "artifact_version": "1.1.0",
        "run": {
            "prompt_only": {
                "model": artifact.model,
                "prompt_hash": artifact.prompt_hash,
                "temperature": artifact.temperature,
            },
            "quantify": {
                "model": artifact.quantify_model,
                "prompt_hash": artifact.quantify_prompt_hash,
                "temperature": artifact.quantify_temperature,
            },
        },
        "cases": [
            {
                "case_id": item.case_id,
                "category": item.category,
                "expected_outcome": item.expected_outcome,
                "prompt_only_outcome": item.prompt_only_outcome,
                "quantify_outcome": item.quantify_outcome,
            }
            for item in artifact.cases
        ],
    }
