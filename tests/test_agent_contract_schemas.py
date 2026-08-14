from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def schema(name: str) -> dict[str, object]:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def test_agent_plan_request_schema_keeps_question_out_and_budgets_bounded() -> None:
    document = schema("agent_plan_request.v1.schema.json")
    properties = document["properties"]

    assert properties["schema_version"]["const"] == "agent-plan-request.v1"
    assert "question" not in properties
    assert properties["budgets"]["properties"]["maximum_actions"]["maximum"] == 8
    assert properties["budgets"]["properties"]["maximum_model_calls"]["maximum"] == 8
    assert document["additionalProperties"] is False


def test_agent_plan_result_schema_has_no_arguments_or_answer_surface() -> None:
    document = schema("agent_plan_result.v1.schema.json")
    stage = document["$defs"]["stage"]

    assert set(stage["properties"]) == {
        "stage_id",
        "tool_name",
        "purpose",
        "depends_on_stage_ids",
    }
    assert "answer" not in document["properties"]
    assert "verdict" not in document["properties"]
    assert stage["additionalProperties"] is False


def test_model_attempt_schema_excludes_raw_provider_and_user_text() -> None:
    document = schema("model_attempt.v1.schema.json")
    properties = document["properties"]

    assert properties["schema_version"]["const"] == "model-attempt.v1"
    assert {
        "provider_status",
        "validation_status",
        "provider_attempt_id",
        "output_hash",
        "usage",
    }.issubset(properties)
    assert not {"question", "prompt", "output", "reasoning"}.intersection(properties)
    assert document["additionalProperties"] is False
