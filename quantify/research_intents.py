"""Canonical bounded research intents and their deterministic tool ceilings.

The signed runtime policy may narrow these permissions further. Neither a
request nor model output can add a tool that is absent from this matrix.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Iterable


class ResearchIntent(StrEnum):
    EXPLORE = "explore"
    ANALYZE = "analyze"
    COMPARE = "compare"
    VERIFY = "verify"


class AgentToolName(StrEnum):
    VERIFY_CLAIMS = "verify_claims"
    SEARCH_APPROVED_EVIDENCE_RELEASE = "search_approved_evidence_release"
    CALCULATE_APPROVED_EVIDENCE = "calculate_approved_evidence"
    CREATE_REVIEW_TASK = "create_review_task"
    NARRATIVE_CONTEXT = "narrative_context"


_TOOL_ORDER = (
    AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
    AgentToolName.CALCULATE_APPROVED_EVIDENCE,
    AgentToolName.NARRATIVE_CONTEXT,
    AgentToolName.VERIFY_CLAIMS,
    AgentToolName.CREATE_REVIEW_TASK,
)

_TOOLS_BY_INTENT = {
    ResearchIntent.EXPLORE: frozenset(
        {
            AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
            AgentToolName.NARRATIVE_CONTEXT,
            AgentToolName.CREATE_REVIEW_TASK,
        }
    ),
    ResearchIntent.ANALYZE: frozenset(
        {
            AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
            AgentToolName.CALCULATE_APPROVED_EVIDENCE,
            AgentToolName.NARRATIVE_CONTEXT,
            AgentToolName.CREATE_REVIEW_TASK,
        }
    ),
    ResearchIntent.COMPARE: frozenset(
        {
            AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
            AgentToolName.CALCULATE_APPROVED_EVIDENCE,
            AgentToolName.NARRATIVE_CONTEXT,
            AgentToolName.CREATE_REVIEW_TASK,
        }
    ),
    ResearchIntent.VERIFY: frozenset(
        {
            AgentToolName.VERIFY_CLAIMS,
            AgentToolName.CREATE_REVIEW_TASK,
        }
    ),
}


ALL_AGENT_TOOLS = frozenset(tool.value for tool in AgentToolName)


def tools_for_intent(intent: ResearchIntent) -> tuple[AgentToolName, ...]:
    """Return the ordered, code-defined maximum tool set for one intent."""

    if not isinstance(intent, ResearchIntent):
        raise ValueError("research intent is invalid")
    permitted = _TOOLS_BY_INTENT[intent]
    return tuple(tool for tool in _TOOL_ORDER if tool in permitted)


def effective_tools_for_intent(
    intent: ResearchIntent,
    *,
    runtime_allowed_tools: Iterable[str],
    runtime_disabled_tools: Iterable[str] = (),
) -> tuple[AgentToolName, ...]:
    """Intersect the intent ceiling with one independently loaded policy."""

    allowed = tuple(runtime_allowed_tools)
    disabled = tuple(runtime_disabled_tools)
    if (
        any(not isinstance(tool, str) or tool not in ALL_AGENT_TOOLS for tool in allowed)
        or len(set(allowed)) != len(allowed)
        or any(not isinstance(tool, str) or tool not in ALL_AGENT_TOOLS for tool in disabled)
        or len(set(disabled)) != len(disabled)
        or not set(disabled).issubset(allowed)
    ):
        raise ValueError("runtime tool policy is invalid")
    allowed_set = set(allowed) - set(disabled)
    return tuple(tool for tool in tools_for_intent(intent) if tool.value in allowed_set)


def intent_allows_tool(intent: ResearchIntent, tool: AgentToolName) -> bool:
    if not isinstance(tool, AgentToolName):
        return False
    return tool in _TOOLS_BY_INTENT.get(intent, frozenset())
