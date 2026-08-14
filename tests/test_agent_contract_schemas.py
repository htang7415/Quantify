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


def test_agent_execution_schema_exposes_metadata_not_raw_tool_results() -> None:
    document = schema("agent_execution_result.v1.schema.json")
    properties = document["properties"]
    artifact = document["$defs"]["artifact"]

    assert properties["schema_version"]["const"] == "agent-execution-result.v1"
    assert set(artifact["properties"]) == {
        "stage_id",
        "tool_name",
        "request_hash",
        "result_hash",
        "dependency_result_hashes",
        "status",
        "statement_ids",
        "citation_ids",
        "claim_ids",
    }
    assert not {"result", "facts", "contexts", "verdicts"}.intersection(
        artifact["properties"]
    )
    assert document["additionalProperties"] is False


def test_shared_agent_presentation_keeps_one_short_message_and_action() -> None:
    document = schema("agent_presentation.v1.schema.json")
    properties = document["properties"]
    message = properties["message"]

    assert properties["schema_version"]["const"] == "agent-presentation.v1"
    assert properties["progress_labels"]["const"] == [
        "Understand",
        "Research",
        "Check",
    ]
    assert message["properties"]["title"]["maxLength"] == 64
    assert message["properties"]["summary"]["maxLength"] == 600
    assert set(properties["primary_action"]["properties"]) == {"action", "label"}
    assert not {"provider", "policy", "token_usage", "tool_name"}.intersection(
        properties
    )
