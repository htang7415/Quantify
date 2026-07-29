from __future__ import annotations

from pathlib import Path

from quantify.evaluation import (
    build_prompting_parity_worklist,
    load_evaluation_model_profile,
    load_frozen_case_set,
)
from quantify.evaluation.gemini_batch import GeminiBatchClient


ROOT = Path(__file__).parents[2]
CASE_ROOT = ROOT / "fixtures" / "cases"
SNAPSHOT_ROOT = ROOT / "fixtures" / "sec"
PROFILE = ROOT / "fixtures" / "evaluation" / "gemini_3_1_flash_lite_batch_v1.json"


class _Transport:
    def __init__(self) -> None:
        self.url = ""
        self.headers: dict[str, str] = {}
        self.body: dict = {}

    def post_json(self, *, url: str, headers: dict[str, str], body: dict) -> dict:
        self.url = url
        self.headers = headers
        self.body = body
        return {"name": "batches/fixture-123"}


def test_submits_only_safe_worklist_data_after_cost_preflight() -> None:
    worklist = build_prompting_parity_worklist(
        mechanical_cases=load_frozen_case_set(
            path=CASE_ROOT / "mechanical_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
        judgment_cases=load_frozen_case_set(
            path=CASE_ROOT / "judgment_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
    )
    transport = _Transport()
    submission = GeminiBatchClient(
        api_key="test-key", transport=transport
    ).submit_prompt_only(
        profile=load_evaluation_model_profile(path=PROFILE), worklist=worklist
    )

    serialized = str(transport.body)
    requests = transport.body["batch"]["input_config"]["requests"]["requests"]
    assert submission.batch_name == "batches/fixture-123"
    assert submission.estimated_total_cost_usd == 0.02112
    assert len(requests) == 30
    assert transport.url.endswith("models/gemini-3.1-flash-lite:batchGenerateContent")
    assert transport.headers["x-goog-api-key"] == "test-key"
    assert "expected_outcome" not in serialized
    assert "case_id" not in serialized
    assert "private-reference" not in serialized
