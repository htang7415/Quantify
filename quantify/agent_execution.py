"""Provider-free execution of independently admitted bounded-agent stages.

The validated plan supplies ordering only. An application-controlled provider
must supply each already-typed request at execution time. Every tool is
reauthorized, every dependency is resolved inside one task-local registry, and
the runner emits metadata only. It does not call a planner, compose a research
answer, or create a verification verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, TypeAlias

from quantify.agent_plans import (
    AgentPlanGroundingContext,
    AgentPlanRequest,
    AgentPlanResult,
    AgentPlanStage,
    AgentPlanStatus,
    hash_document,
)
from quantify.agent_tool import agent_safe_result
from quantify.approved_tools import ApprovedReleaseTools, ToolUnavailableError
from quantify.calculations import (
    ApprovedCalculationRequest,
    ApprovedCalculationResult,
    CalculationError,
)
from quantify.evidence_search import (
    ApprovedEvidenceSearchRequest,
    ApprovedEvidenceSearchResult,
    EvidenceSearchError,
)
from quantify.narrative_context import (
    ApprovedNarrativeContextRequest,
    ApprovedNarrativeContextResult,
    NarrativeContextError,
)
from quantify.policy_control import (
    PolicyControlError,
    PolicyControlPlane,
    PolicyControlPointers,
)
from quantify.research_intents import AgentToolName
from quantify.research_tasks import ResearchTaskRequest
from quantify.review_tasks import (
    ApprovedReviewTaskRequest,
    ApprovedReviewTaskResult,
    ReviewTaskError,
    ReviewTaskGroundingContext,
)


_LIMITATION = (
    "Execution metadata only; typed results remain task-local and no model, "
    "research answer, recommendation, publication decision, or verdict is composed."
)


class AgentExecutionError(ValueError):
    """A plan, invocation, dependency, or artifact failed closed."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class AgentExecutionStatus(StrEnum):
    COMPLETED = "completed"
    REQUIRES_REVIEW = "requires_review"
    UNAVAILABLE = "unavailable"


class AgentExecutionUnavailableReason(StrEnum):
    PLAN_UNAVAILABLE = "plan_unavailable"
    POLICY_UNAVAILABLE = "policy_unavailable"
    TOOL_UNAVAILABLE = "tool_unavailable"
    REQUIRED_INPUT_UNAVAILABLE = "required_input_unavailable"
    REQUIRED_DATA_UNAVAILABLE = "required_data_unavailable"
    VERIFIER_UNAVAILABLE = "verifier_unavailable"


ToolRequest: TypeAlias = (
    ApprovedEvidenceSearchRequest
    | ApprovedCalculationRequest
    | ApprovedNarrativeContextRequest
    | ApprovedReviewTaskRequest
    | ResearchTaskRequest
)
ToolResult: TypeAlias = (
    ApprovedEvidenceSearchResult
    | ApprovedCalculationResult
    | ApprovedNarrativeContextResult
    | ApprovedReviewTaskResult
    | Mapping[str, object]
)


class DeterministicVerificationExecutor(Protocol):
    def verify(
        self, *, cik: str, request: object
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class AgentStageInvocation:
    stage_id: str
    request: ToolRequest
    review_grounding_context: ReviewTaskGroundingContext | None = None


@dataclass(frozen=True, slots=True)
class AgentArtifact:
    stage_id: str
    tool_name: AgentToolName
    request_hash: str
    result_hash: str
    dependency_result_hashes: tuple[str, ...]
    status: str
    statement_ids: tuple[str, ...] = ()
    citation_ids: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.stage_id
            or not isinstance(self.tool_name, AgentToolName)
            or not _is_hash(self.request_hash)
            or not _is_hash(self.result_hash)
            or any(not _is_hash(value) for value in self.dependency_result_hashes)
            or self.status not in {"completed", "partial", "unavailable", "requires_review"}
        ):
            raise AgentExecutionError("invalid_artifact", "artifact metadata is invalid")
        _unique_ids(self.statement_ids, field="statement_ids")
        _unique_ids(self.citation_ids, field="citation_ids")
        _unique_ids(self.claim_ids, field="claim_ids")

    def to_document(self) -> dict[str, object]:
        return {
            "stage_id": self.stage_id,
            "tool_name": self.tool_name.value,
            "request_hash": self.request_hash,
            "result_hash": self.result_hash,
            "dependency_result_hashes": list(self.dependency_result_hashes),
            "status": self.status,
            "statement_ids": list(self.statement_ids),
            "citation_ids": list(self.citation_ids),
            "claim_ids": list(self.claim_ids),
        }


class AgentArtifactView:
    """Read-only task-local dependency view for a stage-request provider."""

    def __init__(
        self,
        *,
        task_id: str,
        plan_id: str,
        artifacts: Mapping[str, AgentArtifact],
        results: Mapping[str, ToolResult],
    ) -> None:
        self.task_id = task_id
        self.plan_id = plan_id
        self._artifacts = MappingProxyType(dict(artifacts))
        self._results = MappingProxyType(dict(results))

    def artifact(self, *, stage_id: str) -> AgentArtifact:
        try:
            return self._artifacts[stage_id]
        except KeyError as error:
            raise AgentExecutionError(
                "unknown_dependency", "dependency artifact is unavailable"
            ) from error

    def typed_result(self, *, stage_id: str, tool_name: AgentToolName) -> ToolResult:
        artifact = self.artifact(stage_id=stage_id)
        if artifact.tool_name is not tool_name:
            raise AgentExecutionError(
                "dependency_type_mismatch", "dependency tool type is invalid"
            )
        return self._results[stage_id]


class AgentArtifactRegistry:
    """One mutable registry owned exclusively by a single runner invocation."""

    def __init__(self, *, task_id: str, plan_id: str) -> None:
        self._task_id = task_id
        self._plan_id = plan_id
        self._artifacts: dict[str, AgentArtifact] = {}
        self._results: dict[str, ToolResult] = {}

    def view(self) -> AgentArtifactView:
        return AgentArtifactView(
            task_id=self._task_id,
            plan_id=self._plan_id,
            artifacts=self._artifacts,
            results=self._results,
        )

    def register(
        self,
        *,
        stage: AgentPlanStage,
        request_hash: str,
        result_hash: str,
        dependency_result_hashes: tuple[str, ...],
        status: str,
        result: ToolResult,
        statement_ids: tuple[str, ...] = (),
        citation_ids: tuple[str, ...] = (),
        claim_ids: tuple[str, ...] = (),
    ) -> AgentArtifact:
        if stage.stage_id in self._artifacts:
            raise AgentExecutionError("duplicate_stage", "stage already has an artifact")
        expected_dependencies = tuple(
            self._artifacts[stage_id].result_hash
            for stage_id in stage.depends_on_stage_ids
            if stage_id in self._artifacts
        )
        if (
            len(expected_dependencies) != len(stage.depends_on_stage_ids)
            or dependency_result_hashes != expected_dependencies
        ):
            raise AgentExecutionError(
                "dependency_mismatch", "artifact dependencies differ from the plan"
            )
        if result_hash in {item.result_hash for item in self._artifacts.values()}:
            raise AgentExecutionError("duplicate_result", "result hash is already registered")
        existing_statement_ids = {
            value for item in self._artifacts.values() for value in item.statement_ids
        }
        existing_citation_ids = {
            value for item in self._artifacts.values() for value in item.citation_ids
        }
        existing_claim_ids = {
            value for item in self._artifacts.values() for value in item.claim_ids
        }
        if (
            existing_statement_ids.intersection(statement_ids)
            or existing_citation_ids.intersection(citation_ids)
            or existing_claim_ids.intersection(claim_ids)
        ):
            raise AgentExecutionError(
                "duplicate_reference", "artifact identifiers are ambiguous"
            )
        artifact = AgentArtifact(
            stage_id=stage.stage_id,
            tool_name=stage.tool_name,
            request_hash=request_hash,
            result_hash=result_hash,
            dependency_result_hashes=dependency_result_hashes,
            status=status,
            statement_ids=_unique_ids(statement_ids, field="statement_ids"),
            citation_ids=_unique_ids(citation_ids, field="citation_ids"),
            claim_ids=_unique_ids(claim_ids, field="claim_ids"),
        )
        self._artifacts[stage.stage_id] = artifact
        self._results[stage.stage_id] = result
        return artifact

    @property
    def artifacts(self) -> tuple[AgentArtifact, ...]:
        return tuple(self._artifacts.values())


StageRequestProvider: TypeAlias = Callable[
    [AgentPlanStage, AgentArtifactView], AgentStageInvocation
]


@dataclass(frozen=True, slots=True)
class AgentExecutionResult:
    execution_id: str
    task_id: str
    plan_id: str
    plan_request_hash: str
    status: AgentExecutionStatus
    artifacts: tuple[AgentArtifact, ...]
    unavailable_reason: AgentExecutionUnavailableReason | None
    schema_version: str = "agent-execution-result.v1"

    def __post_init__(self) -> None:
        if (
            self.schema_version != "agent-execution-result.v1"
            or not self.execution_id.startswith("agent-execution-")
            or not self.task_id
            or not self.plan_id
            or not _is_hash(self.plan_request_hash)
            or not isinstance(self.status, AgentExecutionStatus)
            or not isinstance(self.artifacts, tuple)
            or not all(isinstance(item, AgentArtifact) for item in self.artifacts)
            or len({item.stage_id for item in self.artifacts}) != len(self.artifacts)
            or len({item.result_hash for item in self.artifacts}) != len(self.artifacts)
        ):
            raise AgentExecutionError("invalid_result", "execution result is invalid")
        if (self.status is AgentExecutionStatus.UNAVAILABLE) != (
            self.unavailable_reason is not None
        ):
            raise AgentExecutionError(
                "invalid_result", "unavailable state and reason must be paired"
            )

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "plan_request_hash": self.plan_request_hash,
            "status": self.status.value,
            "artifacts": [artifact.to_document() for artifact in self.artifacts],
            "unavailable_reason": (
                self.unavailable_reason.value if self.unavailable_reason else None
            ),
            "limitations": [_LIMITATION],
        }


class ProviderFreeAgentExecutionRunner:
    """Execute one validated plan with no planner or implicit request creation."""

    def __init__(
        self,
        *,
        tools: ApprovedReleaseTools,
        policy_control: PolicyControlPlane,
        policy_pointers: PolicyControlPointers,
        verification_executor: DeterministicVerificationExecutor | None = None,
    ) -> None:
        self._tools = tools
        self._policy = policy_control
        self._pointers = policy_pointers
        self._verification_executor = verification_executor

    def execute(
        self,
        *,
        plan_request: AgentPlanRequest,
        grounding_context: AgentPlanGroundingContext,
        plan: AgentPlanResult,
        stage_request_provider: StageRequestProvider,
    ) -> AgentExecutionResult:
        grounding_context.validate_request(plan_request)
        self._validate_plan(plan_request=plan_request, plan=plan)
        if not callable(stage_request_provider):
            raise AgentExecutionError(
                "invalid_execution", "stage request provider is unavailable"
            )
        try:
            self._policy.authorize_serving(task_pointers=self._pointers)
        except PolicyControlError:
            return self._result(
                plan_request=plan_request,
                plan=plan,
                status=AgentExecutionStatus.UNAVAILABLE,
                artifacts=(),
                reason=AgentExecutionUnavailableReason.POLICY_UNAVAILABLE,
            )
        if plan.status is AgentPlanStatus.UNAVAILABLE:
            return self._result(
                plan_request=plan_request,
                plan=plan,
                status=AgentExecutionStatus.UNAVAILABLE,
                artifacts=(),
                reason=AgentExecutionUnavailableReason.PLAN_UNAVAILABLE,
            )

        registry = AgentArtifactRegistry(task_id=plan.task_id, plan_id=plan.plan_id)
        for stage in plan.stages:
            invocation = stage_request_provider(stage, registry.view())
            self._validate_invocation(
                plan_request=plan_request,
                grounding_context=grounding_context,
                stage=stage,
                invocation=invocation,
                registry=registry,
            )
            if (
                stage.tool_name is AgentToolName.VERIFY_CLAIMS
                and self._verification_executor is None
            ):
                return self._result(
                    plan_request=plan_request,
                    plan=plan,
                    status=AgentExecutionStatus.UNAVAILABLE,
                    artifacts=registry.artifacts,
                    reason=AgentExecutionUnavailableReason.VERIFIER_UNAVAILABLE,
                )
            try:
                artifact = self._execute_stage(
                    plan_request=plan_request,
                    stage=stage,
                    invocation=invocation,
                    registry=registry,
                )
            except ToolUnavailableError:
                return self._result(
                    plan_request=plan_request,
                    plan=plan,
                    status=AgentExecutionStatus.UNAVAILABLE,
                    artifacts=registry.artifacts,
                    reason=AgentExecutionUnavailableReason.POLICY_UNAVAILABLE,
                )
            except CalculationError as error:
                reason = (
                    AgentExecutionUnavailableReason.REQUIRED_INPUT_UNAVAILABLE
                    if error.code
                    in {"input_unavailable", "input_binding_mismatch", "incompatible_inputs"}
                    else AgentExecutionUnavailableReason.TOOL_UNAVAILABLE
                )
                return self._result(
                    plan_request=plan_request,
                    plan=plan,
                    status=AgentExecutionStatus.UNAVAILABLE,
                    artifacts=registry.artifacts,
                    reason=reason,
                )
            except (EvidenceSearchError, NarrativeContextError, ReviewTaskError):
                return self._result(
                    plan_request=plan_request,
                    plan=plan,
                    status=AgentExecutionStatus.UNAVAILABLE,
                    artifacts=registry.artifacts,
                    reason=AgentExecutionUnavailableReason.TOOL_UNAVAILABLE,
                )
            if artifact.status == "requires_review":
                return self._authorized_result(
                    plan_request=plan_request,
                    plan=plan,
                    status=AgentExecutionStatus.REQUIRES_REVIEW,
                    artifacts=registry.artifacts,
                    reason=None,
                )

        statuses = {artifact.status for artifact in registry.artifacts}
        if statuses and statuses <= {"unavailable"}:
            status = AgentExecutionStatus.UNAVAILABLE
            reason = AgentExecutionUnavailableReason.REQUIRED_DATA_UNAVAILABLE
        else:
            status = AgentExecutionStatus.COMPLETED
            reason = None
        return self._authorized_result(
            plan_request=plan_request,
            plan=plan,
            status=status,
            artifacts=registry.artifacts,
            reason=reason,
        )

    def _execute_stage(
        self,
        *,
        plan_request: AgentPlanRequest,
        stage: AgentPlanStage,
        invocation: AgentStageInvocation,
        registry: AgentArtifactRegistry,
    ) -> AgentArtifact:
        dependency_hashes = tuple(
            registry.view().artifact(stage_id=stage_id).result_hash
            for stage_id in stage.depends_on_stage_ids
        )
        request = invocation.request
        if stage.tool_name is AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE:
            assert isinstance(request, ApprovedEvidenceSearchRequest)
            result = self._tools.search_approved_evidence_release(request=request)
            return registry.register(
                stage=stage,
                request_hash=request.request_hash,
                result_hash=result.result_hash,
                dependency_result_hashes=dependency_hashes,
                status=result.status.value,
                result=result,
                statement_ids=tuple(fact.statement_id for fact in result.facts),
                citation_ids=tuple(fact.citation_id for fact in result.facts),
            )
        if stage.tool_name is AgentToolName.CALCULATE_APPROVED_EVIDENCE:
            assert isinstance(request, ApprovedCalculationRequest)
            search_result = self._search_dependency(stage=stage, registry=registry)
            result = self._tools.calculate_approved_evidence(
                request=request,
                evidence_search_result=search_result,
            )
            return registry.register(
                stage=stage,
                request_hash=request.request_hash,
                result_hash=result.result_hash,
                dependency_result_hashes=dependency_hashes,
                status="completed",
                result=result,
                statement_ids=tuple(item.statement_id for item in result.calculations),
            )
        if stage.tool_name is AgentToolName.NARRATIVE_CONTEXT:
            assert isinstance(request, ApprovedNarrativeContextRequest)
            result = self._tools.narrative_context(request=request)
            return registry.register(
                stage=stage,
                request_hash=request.request_hash,
                result_hash=result.result_hash,
                dependency_result_hashes=dependency_hashes,
                status=result.status.value,
                result=result,
                statement_ids=tuple(item.statement_id for item in result.contexts),
                citation_ids=tuple(item.citation_id for item in result.contexts),
            )
        if stage.tool_name is AgentToolName.CREATE_REVIEW_TASK:
            assert isinstance(request, ApprovedReviewTaskRequest)
            assert invocation.review_grounding_context is not None
            result = self._tools.create_review_task(
                request=request,
                grounding_context=invocation.review_grounding_context,
            )
            return registry.register(
                stage=stage,
                request_hash=request.request_hash,
                result_hash=result.result_hash,
                dependency_result_hashes=dependency_hashes,
                status="requires_review",
                result=result,
            )
        assert stage.tool_name is AgentToolName.VERIFY_CLAIMS
        assert isinstance(request, ResearchTaskRequest)
        assert self._verification_executor is not None
        self._policy.authorize_tool(
            task_pointers=self._pointers,
            tool_name=AgentToolName.VERIFY_CLAIMS.value,
        )
        response = self._verification_executor.verify(
            cik=request.cik,
            request=request.verify_request(),
        )
        safe_result = self._validate_verification_result(
            response=response,
            plan_request=plan_request,
        )
        verdicts = safe_result["verdicts"]
        assert isinstance(verdicts, list)
        return registry.register(
            stage=stage,
            request_hash=request.canonical_request_hash,
            result_hash=hash_document(safe_result),
            dependency_result_hashes=dependency_hashes,
            status=(
                "requires_review"
                if safe_result["requires_agent_resolution"]
                else "completed"
            ),
            result=safe_result,
            claim_ids=tuple(str(item["claim_id"]) for item in verdicts),
        )

    def _validate_invocation(
        self,
        *,
        plan_request: AgentPlanRequest,
        grounding_context: AgentPlanGroundingContext,
        stage: AgentPlanStage,
        invocation: AgentStageInvocation,
        registry: AgentArtifactRegistry,
    ) -> None:
        if not isinstance(invocation, AgentStageInvocation) or invocation.stage_id != stage.stage_id:
            raise AgentExecutionError(
                "stage_mismatch", "stage invocation differs from the plan"
            )
        expected_type = {
            AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE: ApprovedEvidenceSearchRequest,
            AgentToolName.CALCULATE_APPROVED_EVIDENCE: ApprovedCalculationRequest,
            AgentToolName.NARRATIVE_CONTEXT: ApprovedNarrativeContextRequest,
            AgentToolName.CREATE_REVIEW_TASK: ApprovedReviewTaskRequest,
            AgentToolName.VERIFY_CLAIMS: ResearchTaskRequest,
        }[stage.tool_name]
        if not isinstance(invocation.request, expected_type):
            raise AgentExecutionError(
                "request_type_mismatch", "typed request does not match the stage tool"
            )
        request = invocation.request
        if isinstance(request, (ApprovedEvidenceSearchRequest, ApprovedNarrativeContextRequest)):
            if (
                request.task_type is not plan_request.task_intent
                or request.cik != plan_request.cik
                or request.as_of != plan_request.as_of
                or request.release_id != plan_request.release_id
                or request.release_manifest_hash != plan_request.release_manifest_hash
            ):
                raise AgentExecutionError(
                    "scope_mismatch", "tool request differs from the admitted plan scope"
                )
        elif isinstance(request, ApprovedCalculationRequest):
            search_result = self._search_dependency(stage=stage, registry=registry)
            if (
                request.release_manifest_hash != plan_request.release_manifest_hash
                or request.evidence_search_result_hash != search_result.result_hash
            ):
                raise AgentExecutionError(
                    "dependency_mismatch", "calculation request is not bound to its search"
                )
        elif isinstance(request, ApprovedReviewTaskRequest):
            self._validate_review_invocation(
                plan_request=plan_request,
                stage=stage,
                request=request,
                review_context=invocation.review_grounding_context,
                registry=registry,
            )
        else:
            assert isinstance(request, ResearchTaskRequest)
            if (
                request.cik != plan_request.cik
                or request.as_of_date != plan_request.as_of
                or request.analysis != grounding_context.authorized_question
            ):
                raise AgentExecutionError(
                    "scope_mismatch", "verification request differs from the admitted claim"
                )
        if (
            stage.tool_name is not AgentToolName.CREATE_REVIEW_TASK
            and invocation.review_grounding_context is not None
        ):
            raise AgentExecutionError(
                "invalid_execution", "only a review stage may carry review grounding"
            )

    def _validate_review_invocation(
        self,
        *,
        plan_request: AgentPlanRequest,
        stage: AgentPlanStage,
        request: ApprovedReviewTaskRequest,
        review_context: ReviewTaskGroundingContext | None,
        registry: AgentArtifactRegistry,
    ) -> None:
        if review_context is None:
            raise AgentExecutionError(
                "invalid_execution", "review stage requires independent grounding"
            )
        dependencies = tuple(
            registry.view().artifact(stage_id=stage_id)
            for stage_id in stage.depends_on_stage_ids
        )
        result_hashes = {item.result_hash for item in dependencies}
        statement_ids = {
            statement_id for item in dependencies for statement_id in item.statement_ids
        }
        citation_ids = {
            citation_id for item in dependencies for citation_id in item.citation_ids
        }
        if (
            request.task_type is not plan_request.task_intent
            or request.release_id != plan_request.release_id
            or request.release_manifest_hash != plan_request.release_manifest_hash
            or request.runtime_policy_bundle_hash
            != plan_request.runtime_policy_bundle_hash
            or request.release_gate_policy_hash != plan_request.release_gate_policy_hash
            or not set(request.source_result_hashes).issubset(result_hashes)
            or not set(request.derived_from_statement_ids).issubset(statement_ids)
            or not set(request.derived_from_citation_ids).issubset(citation_ids)
            or not set(review_context.authorized_source_result_hashes).issubset(
                result_hashes
            )
            or not set(review_context.authorized_statement_ids).issubset(statement_ids)
            or not set(review_context.authorized_citation_ids).issubset(citation_ids)
        ):
            raise AgentExecutionError(
                "cross_task_reference", "review references leave the task-local registry"
            )

    @staticmethod
    def _search_dependency(
        *, stage: AgentPlanStage, registry: AgentArtifactRegistry
    ) -> ApprovedEvidenceSearchResult:
        search_stage_ids = [
            stage_id
            for stage_id in stage.depends_on_stage_ids
            if registry.view().artifact(stage_id=stage_id).tool_name
            is AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE
        ]
        if len(search_stage_ids) != 1:
            raise AgentExecutionError(
                "dependency_mismatch", "calculation requires one task-local search"
            )
        result = registry.view().typed_result(
            stage_id=search_stage_ids[0],
            tool_name=AgentToolName.SEARCH_APPROVED_EVIDENCE_RELEASE,
        )
        if not isinstance(result, ApprovedEvidenceSearchResult):
            raise AgentExecutionError(
                "dependency_type_mismatch", "search dependency is invalid"
            )
        return result

    def _validate_verification_result(
        self,
        *,
        response: Mapping[str, object],
        plan_request: AgentPlanRequest,
    ) -> dict[str, object]:
        audit = response.get("audit_manifest")
        if not isinstance(audit, Mapping) or any(
            audit.get(field) != expected
            for field, expected in {
                "evidence_release_manifest_hash": plan_request.release_manifest_hash,
                "runtime_policy_bundle_hash": plan_request.runtime_policy_bundle_hash,
                "release_gate_policy_hash": plan_request.release_gate_policy_hash,
            }.items()
        ):
            raise AgentExecutionError(
                "verification_scope_mismatch", "verifier audit differs from admission"
            )
        safe = agent_safe_result(response)
        scope = safe["evidence_scope"]
        assert isinstance(scope, Mapping)
        if scope.get("snapshot_manifest_hash") != plan_request.release_manifest_hash:
            raise AgentExecutionError(
                "verification_scope_mismatch", "verifier evidence scope differs from admission"
            )
        return safe

    def _authorized_result(
        self,
        *,
        plan_request: AgentPlanRequest,
        plan: AgentPlanResult,
        status: AgentExecutionStatus,
        artifacts: tuple[AgentArtifact, ...],
        reason: AgentExecutionUnavailableReason | None,
    ) -> AgentExecutionResult:
        try:
            self._policy.authorize_serving(task_pointers=self._pointers)
        except PolicyControlError:
            return self._result(
                plan_request=plan_request,
                plan=plan,
                status=AgentExecutionStatus.UNAVAILABLE,
                artifacts=artifacts,
                reason=AgentExecutionUnavailableReason.POLICY_UNAVAILABLE,
            )
        return self._result(
            plan_request=plan_request,
            plan=plan,
            status=status,
            artifacts=artifacts,
            reason=reason,
        )

    @staticmethod
    def _result(
        *,
        plan_request: AgentPlanRequest,
        plan: AgentPlanResult,
        status: AgentExecutionStatus,
        artifacts: tuple[AgentArtifact, ...],
        reason: AgentExecutionUnavailableReason | None,
    ) -> AgentExecutionResult:
        identity = {
            "task_id": plan_request.task_id,
            "plan_id": plan.plan_id,
            "plan_request_hash": plan_request.request_hash,
            "status": status.value,
            "artifact_hashes": [artifact.result_hash for artifact in artifacts],
            "unavailable_reason": reason.value if reason else None,
        }
        return AgentExecutionResult(
            execution_id=f"agent-execution-{hash_document(identity)[:32]}",
            task_id=plan_request.task_id,
            plan_id=plan.plan_id,
            plan_request_hash=plan_request.request_hash,
            status=status,
            artifacts=artifacts,
            unavailable_reason=reason,
        )

    def _validate_plan(
        self, *, plan_request: AgentPlanRequest, plan: AgentPlanResult
    ) -> None:
        if (
            not isinstance(plan, AgentPlanResult)
            or plan.task_id != plan_request.task_id
            or plan.request_hash != plan_request.request_hash
            or plan.task_intent is not plan_request.task_intent
            or len(plan.stages) > plan_request.maximum_actions
            or self._pointers.evidence_release_manifest_hash
            != plan_request.release_manifest_hash
            or self._pointers.runtime_policy_bundle_hash
            != plan_request.runtime_policy_bundle_hash
            or self._pointers.release_gate_policy_hash
            != plan_request.release_gate_policy_hash
        ):
            raise AgentExecutionError(
                "scope_mismatch", "execution plan differs from admission or policy pointers"
            )


def _unique_ids(values: tuple[str, ...], *, field: str) -> tuple[str, ...]:
    if (
        not isinstance(values, tuple)
        or any(not isinstance(value, str) or not value for value in values)
        or len(set(values)) != len(values)
    ):
        raise AgentExecutionError("invalid_artifact", f"{field} are invalid")
    return values


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
