from __future__ import annotations

from pathlib import Path

import pytest

from quantify.evaluation import (
    build_prompting_parity_worklist,
    load_evaluation_model_profile,
    load_frozen_case_set,
)
from quantify.evaluation.gemini_batch import (
    GeminiBatchClient,
    prompt_only_outcome_artifact_as_dict,
)


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

    def get_json(self, *, url: str, headers: dict[str, str]) -> dict:
        self.url = url
        self.headers = headers
        return _successful_batch_response()


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
    assert submission.estimated_total_cost_usd == 0.06912
    assert len(requests) == 30
    assert transport.url.endswith("models/gemini-3.1-flash-lite:batchGenerateContent")
    assert transport.headers["x-goog-api-key"] == "test-key"
    assert "expected_outcome" not in serialized
    assert "case_id" not in serialized
    assert "private-reference" not in serialized


def test_collects_only_complete_closed_outcomes_in_submitted_order() -> None:
    worklist = build_prompting_parity_worklist(
        mechanical_cases=load_frozen_case_set(
            path=CASE_ROOT / "mechanical_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
        judgment_cases=load_frozen_case_set(
            path=CASE_ROOT / "judgment_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
    )
    profile = load_evaluation_model_profile(path=PROFILE)
    transport = _Transport()
    result = GeminiBatchClient(
        api_key="test-key", transport=transport
    ).collect_prompt_only_outcomes(
        batch_name="batches/fixture-123",
        profile=profile,
        request_ids=tuple(item.request_id for item in worklist.items),
    )

    artifact = prompt_only_outcome_artifact_as_dict(outcomes=result)
    assert transport.url.endswith("/batches/fixture-123")
    assert result.model == "gemini-3.1-flash-lite"
    assert len(result.prompt_hash) == 64
    assert artifact["path"] == "prompt_only"
    assert [item["request_id"] for item in artifact["outcomes"]] == [
        item.request_id for item in worklist.items
    ]
    assert "case_id" not in str(artifact)
    assert "expected_outcome" not in str(artifact)


def test_collect_rejects_incomplete_or_malformed_provider_results() -> None:
    worklist = build_prompting_parity_worklist(
        mechanical_cases=load_frozen_case_set(
            path=CASE_ROOT / "mechanical_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
        judgment_cases=load_frozen_case_set(
            path=CASE_ROOT / "judgment_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
    )
    profile = load_evaluation_model_profile(path=PROFILE)
    request_ids = tuple(item.request_id for item in worklist.items)

    class _RunningTransport(_Transport):
        def get_json(self, *, url: str, headers: dict[str, str]) -> dict:
            return {"metadata": {"state": "BATCH_STATE_RUNNING"}, "done": False}

    with pytest.raises(ValueError, match="has not succeeded"):
        GeminiBatchClient(
            api_key="test-key", transport=_RunningTransport()
        ).collect_prompt_only_outcomes(
            batch_name="batches/fixture-123", profile=profile, request_ids=request_ids
        )

    class _MalformedTransport(_Transport):
        def get_json(self, *, url: str, headers: dict[str, str]) -> dict:
            payload = _successful_batch_response()
            payload["response"]["inlinedResponses"][0]["response"]["candidates"][0][
                "content"
            ]["parts"][0]["text"] = '{"outcome":"invented"}'
            return payload

    with pytest.raises(ValueError, match="supported closed verdict"):
        GeminiBatchClient(
            api_key="test-key", transport=_MalformedTransport()
        ).collect_prompt_only_outcomes(
            batch_name="batches/fixture-123", profile=profile, request_ids=request_ids
        )


def _successful_batch_response() -> dict:
    worklist = build_prompting_parity_worklist(
        mechanical_cases=load_frozen_case_set(
            path=CASE_ROOT / "mechanical_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
        judgment_cases=load_frozen_case_set(
            path=CASE_ROOT / "judgment_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
    )
    return {
        "metadata": {"state": "BATCH_STATE_SUCCEEDED"},
        "done": True,
        "response": {
            "inlinedResponses": [
                {
                    "metadata": {"key": item.request_id},
                    "response": {
                        "candidates": [
                            {"content": {"parts": [{"text": '{"outcome":"unclassified"}'}]}}
                        ]
                    },
                }
                for item in worklist.items
            ]
        },
    }
