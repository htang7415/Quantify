from __future__ import annotations

import json
from pathlib import Path

from quantify.evaluation import build_prompting_parity_worklist, load_frozen_case_set
from quantify.evaluation.parity_worklist_cli import main


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


def test_worklist_exposes_no_frozen_reference_answers_to_the_model() -> None:
    worklist = _worklist()

    model_input = worklist.model_input()
    serialized = json.dumps(model_input)

    assert len(model_input["items"]) == 30
    assert "case_id" not in serialized
    assert "expected_outcome" not in serialized
    assert "category" not in serialized
    assert "Microsoft revenue increased" in serialized
    assert len(worklist.reference_mapping()["items"]) == 30
    assert worklist.items == _worklist().items


def test_worklist_cli_writes_private_mapping_separately(tmp_path: Path, capsys) -> None:
    mapping_path = tmp_path / "private-reference.json"

    exit_code = main(
        [
            "--mechanical-cases",
            str(CASE_ROOT / "mechanical_v1.json"),
            "--judgment-cases",
            str(CASE_ROOT / "judgment_v1.json"),
            "--snapshot-root",
            str(SNAPSHOT_ROOT),
            "--reference-mapping-output",
            str(mapping_path),
        ]
    )

    model_input = json.loads(capsys.readouterr().out)
    reference_mapping = json.loads(mapping_path.read_text())
    assert exit_code == 0
    assert set(model_input["items"][0]) == {"request_id", "report_text"}
    assert set(reference_mapping["items"][0]) == {
        "request_id",
        "case_id",
        "category",
        "expected_outcome",
    }
