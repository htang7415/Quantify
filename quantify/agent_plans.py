"""Provider-free contracts for one bounded, grounded agent plan.

The model may propose a small sequence of stages. Deterministic code binds the
proposal to independently admitted scope and permissions. A validated plan is
not tool-execution authority and cannot contain tool arguments, facts, answers,
citations, provider instructions, or verdicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Mapping

from quantify.harness.sec.client import SecCompanyFactsClient
from quantify.research_intents import (
    AgentToolName,
    ResearchIntent,
    intent_allows_tool,
    tools_for_intent,
)


_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_QUESTION_LIMIT = 2_000
_MAXIMUM_ACTIONS = 8
_MAXIMUM_MODEL_CALLS = 8
_LIMITATION = (
    "Validated planning metadata only; no tool execution, live retrieval, "
    "model authority, factual assertion, recommendation, or verdict."
)


class AgentPlanError(ValueError):
    """An admitted plan request, grounding context, or proposal failed closed."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class AgentPlanStatus(StrEnum):
    PLANNED = "planned"
    UNAVAILABLE = "unavailable"


class AgentPlanPurpose(StrEnum):
    RETRIEVE_FACTS = "retrieve_facts"
    CALCULATE = "calculate"
    RETRIEVE_CONTEXT = "retrieve_context"
    VERIFY_CLAIM = "verify_claim"
    ROUTE_REVIEW = "route_review"


class AgentPlanUnavailableReason(StrEnum):
    UNSUPPORTED_QUESTION = "unsupported_question"
    INSUFFICIENT_SCOPE = "insufficient_scope"
    NO_PERMITTED_TOOLS = "no_permitted_tools"
    PROHIBITED_REQUEST = "prohibited_request"


_PURPOSE_BY_TOOL = {
    AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE: AgentPlanPurpose.RETRIEVE_FACTS,
    AgentToolName.CALCULATE_APPROVED_EVIDENCE: AgentPlanPurpose.CALCULATE,
    AgentToolName.NARRATIVE_CONTEXT: AgentPlanPurpose.RETRIEVE_CONTEXT,
    AgentToolName.VERIFY_CLAIMS: AgentPlanPurpose.VERIFY_CLAIM,
    AgentToolName.CREATE_REVIEW_TASK: AgentPlanPurpose.ROUTE_REVIEW,
}


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def hash_document(value: object) -> str:
    """Hash one JSON-compatible document using the contract canonicalization."""

    try:
        return sha256(_canonical_json(value)).hexdigest()
    except (TypeError, ValueError) as error:
        raise AgentPlanError("invalid_proposal", "proposal is not canonical JSON") from error


def normalize_question(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > _QUESTION_LIMIT
        or "\x00" in value
    ):
        raise AgentPlanError("invalid_context", "question is invalid")
    return value


def question_hash(value: str) -> str:
    return sha256(normalize_question(value).encode("utf-8")).hexdigest()


def _require_hash(value: str, *, field: str, code: str) -> None:
    if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value):
        raise AgentPlanError(code, f"{field} must be a lowercase SHA-256 hash")


def _require_text(value: str, *, field: str, code: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AgentPlanError(code, f"{field} is invalid")


def _require_id(value: str, *, field: str, code: str) -> None:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        raise AgentPlanError(code, f"{field} is invalid")


@dataclass(frozen=True, slots=True)
class AgentPlanRequest:
    task_id: str
    task_intent: ResearchIntent
    question_hash: str
    cik: str
    as_of: date
    release_id: str
    release_manifest_hash: str
    runtime_policy_bundle_hash: str
    release_gate_policy_hash: str
    allowed_tools: tuple[AgentToolName, ...]
    maximum_actions: int
    maximum_model_calls: int
    prompt_contract_hash: str
    tool_contract_hash: str
    schema_version: str = "agent-plan-request.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "agent-plan-request.v1":
            raise AgentPlanError("invalid_request", "request schema version is invalid")
        _require_id(self.task_id, field="task_id", code="invalid_request")
        if not isinstance(self.task_intent, ResearchIntent):
            raise AgentPlanError("invalid_request", "task_intent is invalid")
        _require_hash(self.question_hash, field="question_hash", code="invalid_request")
        try:
            normalized_cik = SecCompanyFactsClient.normalize_cik(self.cik)
        except (TypeError, ValueError) as error:
            raise AgentPlanError("invalid_request", "company CIK is invalid") from error
        object.__setattr__(self, "cik", normalized_cik)
        if not isinstance(self.as_of, date):
            raise AgentPlanError("invalid_request", "as_of is invalid")
        _require_text(self.release_id, field="release_id", code="invalid_request")
        for field in (
            "release_manifest_hash",
            "runtime_policy_bundle_hash",
            "release_gate_policy_hash",
            "prompt_contract_hash",
            "tool_contract_hash",
        ):
            _require_hash(getattr(self, field), field=field, code="invalid_request")
        if (
            not isinstance(self.allowed_tools, tuple)
            or not self.allowed_tools
            or not all(isinstance(tool, AgentToolName) for tool in self.allowed_tools)
            or len(set(self.allowed_tools)) != len(self.allowed_tools)
            or any(not intent_allows_tool(self.task_intent, tool) for tool in self.allowed_tools)
        ):
            raise AgentPlanError("invalid_request", "allowed_tools exceed the intent ceiling")
        ordered = tuple(
            tool for tool in tools_for_intent(self.task_intent) if tool in self.allowed_tools
        )
        object.__setattr__(self, "allowed_tools", ordered)
        if (
            not isinstance(self.maximum_actions, int)
            or isinstance(self.maximum_actions, bool)
            or not 1 <= self.maximum_actions <= _MAXIMUM_ACTIONS
        ):
            raise AgentPlanError("invalid_request", "maximum_actions is invalid")
        if (
            not isinstance(self.maximum_model_calls, int)
            or isinstance(self.maximum_model_calls, bool)
            or not 1 <= self.maximum_model_calls <= _MAXIMUM_MODEL_CALLS
        ):
            raise AgentPlanError("invalid_request", "maximum_model_calls is invalid")

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "task_intent": self.task_intent.value,
            "question_hash": self.question_hash,
            "entity": {"entity_type": "company", "cik": self.cik},
            "as_of": self.as_of.isoformat(),
            "release": {
                "release_id": self.release_id,
                "manifest_hash": self.release_manifest_hash,
            },
            "policy": {
                "runtime_policy_bundle_hash": self.runtime_policy_bundle_hash,
                "release_gate_policy_hash": self.release_gate_policy_hash,
            },
            "allowed_tools": [tool.value for tool in self.allowed_tools],
            "budgets": {
                "maximum_actions": self.maximum_actions,
                "maximum_model_calls": self.maximum_model_calls,
            },
            "contracts": {
                "prompt_contract_hash": self.prompt_contract_hash,
                "tool_contract_hash": self.tool_contract_hash,
            },
        }

    @property
    def request_hash(self) -> str:
        return hash_document(self.to_document())


@dataclass(frozen=True, slots=True)
class AgentPlanGroundingContext:
    task_id: str
    task_intent: ResearchIntent
    authorized_question: str
    cik: str
    as_of: date
    release_id: str
    release_manifest_hash: str
    runtime_policy_bundle_hash: str
    release_gate_policy_hash: str
    authorized_tools: tuple[AgentToolName, ...]
    maximum_actions: int
    maximum_model_calls: int
    prompt_contract_hash: str
    tool_contract_hash: str

    def validate_request(self, request: AgentPlanRequest) -> None:
        normalized = normalize_question(self.authorized_question)
        expected = (
            self.task_id,
            self.task_intent,
            question_hash(normalized),
            SecCompanyFactsClient.normalize_cik(self.cik),
            self.as_of,
            self.release_id,
            self.release_manifest_hash,
            self.runtime_policy_bundle_hash,
            self.release_gate_policy_hash,
            self.authorized_tools,
            self.maximum_actions,
            self.maximum_model_calls,
            self.prompt_contract_hash,
            self.tool_contract_hash,
        )
        actual = (
            request.task_id,
            request.task_intent,
            request.question_hash,
            request.cik,
            request.as_of,
            request.release_id,
            request.release_manifest_hash,
            request.runtime_policy_bundle_hash,
            request.release_gate_policy_hash,
            request.allowed_tools,
            request.maximum_actions,
            request.maximum_model_calls,
            request.prompt_contract_hash,
            request.tool_contract_hash,
        )
        if expected != actual:
            raise AgentPlanError("scope_mismatch", "plan request differs from admission")


@dataclass(frozen=True, slots=True)
class AgentPlanStage:
    stage_id: str
    tool_name: AgentToolName
    purpose: AgentPlanPurpose
    depends_on_stage_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_id(self.stage_id, field="stage_id", code="invalid_result")
        if (
            not isinstance(self.tool_name, AgentToolName)
            or not isinstance(self.purpose, AgentPlanPurpose)
            or _PURPOSE_BY_TOOL.get(self.tool_name) is not self.purpose
            or not isinstance(self.depends_on_stage_ids, tuple)
            or any(not isinstance(item, str) for item in self.depends_on_stage_ids)
            or len(set(self.depends_on_stage_ids)) != len(self.depends_on_stage_ids)
        ):
            raise AgentPlanError("invalid_result", "plan stage is invalid")

    def to_document(self) -> dict[str, object]:
        return {
            "stage_id": self.stage_id,
            "tool_name": self.tool_name.value,
            "purpose": self.purpose.value,
            "depends_on_stage_ids": list(self.depends_on_stage_ids),
        }


@dataclass(frozen=True, slots=True)
class AgentPlanResult:
    plan_id: str
    task_id: str
    request_hash: str
    proposal_hash: str
    task_intent: ResearchIntent
    status: AgentPlanStatus
    stages: tuple[AgentPlanStage, ...]
    unavailable_reason: AgentPlanUnavailableReason | None
    schema_version: str = "agent-plan-result.v1"

    def __post_init__(self) -> None:
        expected_plan_hash = hash_document(
            {
                "request_hash": self.request_hash,
                "proposal_hash": self.proposal_hash,
            }
        )
        if (
            self.schema_version != "agent-plan-result.v1"
            or self.plan_id != f"agent-plan-{expected_plan_hash[:32]}"
            or not self.task_id
            or not isinstance(self.request_hash, str)
            or not _HASH_PATTERN.fullmatch(self.request_hash)
            or not isinstance(self.proposal_hash, str)
            or not _HASH_PATTERN.fullmatch(self.proposal_hash)
            or not isinstance(self.task_intent, ResearchIntent)
            or not isinstance(self.status, AgentPlanStatus)
            or not isinstance(self.stages, tuple)
            or not all(isinstance(stage, AgentPlanStage) for stage in self.stages)
            or len(self.stages) > _MAXIMUM_ACTIONS
        ):
            raise AgentPlanError("invalid_result", "plan result is invalid")
        if self.status is AgentPlanStatus.UNAVAILABLE:
            if self.stages or not isinstance(
                self.unavailable_reason, AgentPlanUnavailableReason
            ):
                raise AgentPlanError("invalid_result", "unavailable plan is invalid")
            return
        if not self.stages or self.unavailable_reason is not None:
            raise AgentPlanError("invalid_result", "planned result is invalid")
        seen_ids: set[str] = set()
        seen_tools: set[AgentToolName] = set()
        for stage in self.stages:
            if (
                stage.stage_id in seen_ids
                or stage.tool_name in seen_tools
                or not intent_allows_tool(self.task_intent, stage.tool_name)
                or any(item not in seen_ids for item in stage.depends_on_stage_ids)
            ):
                raise AgentPlanError("invalid_result", "plan stage graph is invalid")
            dependency_tools = {
                prior.tool_name
                for prior in self.stages
                if prior.stage_id in stage.depends_on_stage_ids
            }
            if (
                stage.tool_name is AgentToolName.CALCULATE_APPROVED_EVIDENCE
                and AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE
                not in dependency_tools
            ):
                raise AgentPlanError("invalid_result", "calculation dependency is invalid")
            if (
                stage.tool_name is AgentToolName.CREATE_REVIEW_TASK
                and not stage.depends_on_stage_ids
            ):
                raise AgentPlanError("invalid_result", "review dependency is invalid")
            seen_ids.add(stage.stage_id)
            seen_tools.add(stage.tool_name)
        if any(
            stage.tool_name is AgentToolName.CREATE_REVIEW_TASK
            for stage in self.stages[:-1]
        ):
            raise AgentPlanError("invalid_result", "review must be terminal")

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "request_hash": self.request_hash,
            "proposal_hash": self.proposal_hash,
            "task_intent": self.task_intent.value,
            "status": self.status.value,
            "stages": [stage.to_document() for stage in self.stages],
            "unavailable_reason": (
                self.unavailable_reason.value if self.unavailable_reason else None
            ),
            "limitations": [_LIMITATION],
        }


class DeterministicAgentPlanAdapter:
    """Validate one model proposal without calling a provider or any tool."""

    def validate(
        self,
        *,
        request: AgentPlanRequest,
        grounding_context: AgentPlanGroundingContext,
        proposed_plan: Mapping[str, object],
    ) -> AgentPlanResult:
        if not isinstance(request, AgentPlanRequest):
            raise AgentPlanError("invalid_request", "plan request is invalid")
        grounding_context.validate_request(request)
        proposal = self._parse_proposal(request=request, value=proposed_plan)
        proposal_hash = hash_document(proposed_plan)
        plan_hash = hash_document(
            {
                "request_hash": request.request_hash,
                "proposal_hash": proposal_hash,
            }
        )
        return AgentPlanResult(
            plan_id=f"agent-plan-{plan_hash[:32]}",
            task_id=request.task_id,
            request_hash=request.request_hash,
            proposal_hash=proposal_hash,
            task_intent=request.task_intent,
            status=proposal[0],
            stages=proposal[1],
            unavailable_reason=proposal[2],
        )

    def _parse_proposal(
        self, *, request: AgentPlanRequest, value: Mapping[str, object]
    ) -> tuple[
        AgentPlanStatus,
        tuple[AgentPlanStage, ...],
        AgentPlanUnavailableReason | None,
    ]:
        if not isinstance(value, Mapping) or set(value) != {
            "status",
            "stages",
            "unavailable_reason",
        }:
            raise AgentPlanError("invalid_proposal", "proposal shape is invalid")
        try:
            status = AgentPlanStatus(value["status"])
        except (TypeError, ValueError) as error:
            raise AgentPlanError("invalid_proposal", "status is invalid") from error
        raw_stages = value["stages"]
        if not isinstance(raw_stages, list):
            raise AgentPlanError("invalid_proposal", "stages must be an array")
        if status is AgentPlanStatus.UNAVAILABLE:
            if raw_stages:
                raise AgentPlanError("invalid_proposal", "unavailable plan cannot have stages")
            try:
                reason = AgentPlanUnavailableReason(value["unavailable_reason"])
            except (TypeError, ValueError) as error:
                raise AgentPlanError(
                    "invalid_proposal", "unavailable reason is invalid"
                ) from error
            return status, (), reason
        if value["unavailable_reason"] is not None:
            raise AgentPlanError("invalid_proposal", "planned result cannot be unavailable")
        if not 1 <= len(raw_stages) <= request.maximum_actions:
            raise AgentPlanError("budget_exceeded", "stage count exceeds admission")

        stages: list[AgentPlanStage] = []
        seen_ids: set[str] = set()
        seen_tools: set[AgentToolName] = set()
        for raw_stage in raw_stages:
            if not isinstance(raw_stage, Mapping) or set(raw_stage) != {
                "stage_id",
                "tool_name",
                "purpose",
                "depends_on_stage_ids",
            }:
                raise AgentPlanError("invalid_proposal", "stage shape is invalid")
            stage_id = raw_stage["stage_id"]
            _require_id(stage_id, field="stage_id", code="invalid_proposal")
            if stage_id in seen_ids:
                raise AgentPlanError("invalid_proposal", "stage IDs must be unique")
            try:
                tool = AgentToolName(raw_stage["tool_name"])
                purpose = AgentPlanPurpose(raw_stage["purpose"])
            except (TypeError, ValueError) as error:
                raise AgentPlanError("invalid_proposal", "stage tool or purpose is invalid") from error
            if tool not in request.allowed_tools or not intent_allows_tool(
                request.task_intent, tool
            ):
                raise AgentPlanError("tool_not_permitted", "stage tool is not permitted")
            if _PURPOSE_BY_TOOL[tool] is not purpose:
                raise AgentPlanError("invalid_proposal", "stage purpose does not match tool")
            if tool in seen_tools:
                raise AgentPlanError("invalid_proposal", "each tool may appear at most once")
            dependencies = raw_stage["depends_on_stage_ids"]
            if (
                not isinstance(dependencies, list)
                or any(not isinstance(item, str) for item in dependencies)
                or len(set(dependencies)) != len(dependencies)
                or any(item not in seen_ids for item in dependencies)
            ):
                raise AgentPlanError(
                    "invalid_dependency", "dependencies must name unique earlier stages"
                )
            dependency_tools = {
                stage.tool_name for stage in stages if stage.stage_id in dependencies
            }
            if (
                tool is AgentToolName.CALCULATE_APPROVED_EVIDENCE
                and AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE not in dependency_tools
            ):
                raise AgentPlanError(
                    "invalid_dependency", "calculation must depend on exact search"
                )
            if tool is AgentToolName.CREATE_REVIEW_TASK and not dependencies:
                raise AgentPlanError(
                    "invalid_dependency", "review must depend on prior grounded work"
                )
            if tool is AgentToolName.VERIFY_CLAIMS and request.task_intent is not ResearchIntent.VERIFY:
                raise AgentPlanError("tool_not_permitted", "verification tool requires verify intent")
            stages.append(
                AgentPlanStage(
                    stage_id=stage_id,
                    tool_name=tool,
                    purpose=purpose,
                    depends_on_stage_ids=tuple(dependencies),
                )
            )
            seen_ids.add(stage_id)
            seen_tools.add(tool)
        if any(
            stage.tool_name is AgentToolName.CREATE_REVIEW_TASK
            for stage in stages[:-1]
        ):
            raise AgentPlanError("invalid_proposal", "review must be the terminal stage")
        return status, tuple(stages), None
