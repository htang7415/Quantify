from __future__ import annotations

import pytest

from quantify.evidence_search import EvidenceSearchTask
from quantify.narrative_context import NarrativeContextTask
from quantify.research_intents import (
    AgentToolName,
    ResearchIntent,
    effective_tools_for_intent,
    tools_for_intent,
)
from quantify.review_tasks import ReviewTaskType


def test_all_research_contracts_share_one_canonical_intent() -> None:
    assert EvidenceSearchTask is ResearchIntent
    assert NarrativeContextTask is ResearchIntent
    assert ReviewTaskType is ResearchIntent


def test_intent_matrix_keeps_verdict_authority_out_of_analysis() -> None:
    analyze = tools_for_intent(ResearchIntent.ANALYZE)
    verify = tools_for_intent(ResearchIntent.VERIFY)

    assert AgentToolName.VERIFY_CLAIMS not in analyze
    assert AgentToolName.CALCULATE_APPROVED_EVIDENCE in analyze
    assert verify == (
        AgentToolName.VERIFY_CLAIMS,
        AgentToolName.CREATE_REVIEW_TASK,
    )


def test_runtime_policy_can_only_narrow_an_intent() -> None:
    effective = effective_tools_for_intent(
        ResearchIntent.ANALYZE,
        runtime_allowed_tools=(
            "verify_claims",
            "search_approved_evidence_release",
            "calculate_approved_evidence",
            "create_review_task",
            "narrative_context",
        ),
        runtime_disabled_tools=("narrative_context",),
    )

    assert effective == (
        AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
        AgentToolName.CALCULATE_APPROVED_EVIDENCE,
        AgentToolName.CREATE_REVIEW_TASK,
    )
    assert AgentToolName.VERIFY_CLAIMS not in effective


@pytest.mark.parametrize(
    "allowed,disabled",
    [
        (("unknown",), ()),
        (("verify_claims", "verify_claims"), ()),
        (("verify_claims",), ("narrative_context",)),
    ],
)
def test_malformed_runtime_tool_sets_fail_closed(
    allowed: tuple[str, ...], disabled: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError, match="runtime tool policy"):
        effective_tools_for_intent(
            ResearchIntent.VERIFY,
            runtime_allowed_tools=allowed,
            runtime_disabled_tools=disabled,
        )
