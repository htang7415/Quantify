from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantify.evaluation import (
    build_prompting_parity_worklist,
    compile_prompting_parity_artifact,
    load_frozen_case_set,
    load_model_outcome_artifact,
    load_prompting_parity_artifact,
    load_prompting_parity_references,
    prompting_parity_artifact_as_dict,
)
from quantify.evaluation.parity_compile_cli import main


ROOT = Path(__file__).parents[2]
CASE_ROOT = ROOT / "fixtures" / "cases"
SNAPSHOT_ROOT = ROOT / "fixtures" / "sec"


def _worklist():
    return build_prompting_parity_worklist(
        mechanical_cases=load_frozen_case_set(
            path=CASE_ROOT / "mechanical_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
        judgment_cases=load_frozen_case_set(
            path=CASE_ROOT / "judgment_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
    )


def _write_outcomes(
    tmp_path: Path, *, worklist, path: str, unknown_request_id: bool = False
) -> Path:
    reference_by_id = {item.request_id: item for item in worklist.references}
    payload = {
        "artifact_version": "1.0.0",
        "path": path,
        "run": {
            "model": "pinned-fixture-v1",
            "prompt_hash": f"{path}-prompt-v1",
            "temperature": 0,
        },
        "outcomes": [
            {
                "request_id": (
                    "unknown-request-id" if unknown_request_id and index == 0 else item.request_id
                ),
                "outcome": reference_by_id[item.request_id].expected_outcome,
            }
            for index, item in enumerate(worklist.items)
        ],
    }
    output = tmp_path / f"{path}.json"
    output.write_text(json.dumps(payload))
    return output


def test_compiler_joins_opaque_outcomes_to_private_references(tmp_path: Path) -> None:
    worklist = _worklist()
    mapping_path = tmp_path / "reference.json"
    mapping_path.write_text(json.dumps(worklist.reference_mapping()))
    prompt_path = _write_outcomes(tmp_path, worklist=worklist, path="prompt_only")
    quantify_path = _write_outcomes(tmp_path, worklist=worklist, path="quantify")

    artifact = compile_prompting_parity_artifact(
        references=load_prompting_parity_references(path=mapping_path),
        prompt_only=load_model_outcome_artifact(path=prompt_path),
        quantify=load_model_outcome_artifact(path=quantify_path),
    )
    artifact_path = tmp_path / "parity.json"
    artifact_path.write_text(
        json.dumps(prompting_parity_artifact_as_dict(artifact=artifact))
    )

    replayable = load_prompting_parity_artifact(artifact_path)
    assert replayable.artifact_version == "1.1.0"
    assert replayable.model == replayable.quantify_model == "pinned-fixture-v1"
    assert replayable.prompt_hash != replayable.quantify_prompt_hash
    assert len(replayable.cases) == 30


def test_compiler_rejects_an_outcome_not_in_the_private_mapping(tmp_path: Path) -> None:
    worklist = _worklist()
    mapping_path = tmp_path / "reference.json"
    mapping_path.write_text(json.dumps(worklist.reference_mapping()))
    prompt_path = _write_outcomes(
        tmp_path, worklist=worklist, path="prompt_only", unknown_request_id=True
    )
    quantify_path = _write_outcomes(tmp_path, worklist=worklist, path="quantify")

    with pytest.raises(ValueError, match="do not match"):
        compile_prompting_parity_artifact(
            references=load_prompting_parity_references(path=mapping_path),
            prompt_only=load_model_outcome_artifact(path=prompt_path),
            quantify=load_model_outcome_artifact(path=quantify_path),
        )


def test_compiler_cli_writes_the_artifact_consumed_by_readiness(tmp_path: Path) -> None:
    worklist = _worklist()
    mapping_path = tmp_path / "reference.json"
    mapping_path.write_text(json.dumps(worklist.reference_mapping()))
    prompt_path = _write_outcomes(tmp_path, worklist=worklist, path="prompt_only")
    quantify_path = _write_outcomes(tmp_path, worklist=worklist, path="quantify")
    output_path = tmp_path / "parity.json"

    exit_code = main(
        [
            "--reference-mapping",
            str(mapping_path),
            "--prompt-only-outcomes",
            str(prompt_path),
            "--quantify-outcomes",
            str(quantify_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert load_prompting_parity_artifact(output_path).artifact_version == "1.1.0"
