"""Typed internal agent tools; none can compose or alter a verdict."""

from __future__ import annotations

from quantify.calculations import (
    ApprovedCalculationRequest,
    ApprovedCalculationResult,
    DeterministicCalculationAdapter,
)
from quantify.evidence_search import (
    ApprovedEvidenceSearchRequest,
    ApprovedEvidenceSearchResult,
    FrozenReleaseEvidenceSearch,
)
from quantify.indexed_release import IndexedEvidenceRelease
from quantify.narrative_context import (
    ApprovedNarrativeContextRequest,
    ApprovedNarrativeContextResult,
    FrozenReleaseNarrativeContext,
)
from quantify.policy_control import PolicyControlPlane, PolicyControlPointers
from quantify.review_tasks import (
    ApprovedReviewTaskRequest,
    ApprovedReviewTaskResult,
    DeterministicReviewTaskAdapter,
    ReviewTaskGroundingContext,
)


class ToolUnavailableError(RuntimeError):
    pass


class ApprovedReleaseTools:
    def __init__(
        self,
        *,
        release: IndexedEvidenceRelease,
        policy: PolicyControlPlane,
        pointers: PolicyControlPointers,
    ) -> None:
        self._release = release
        self._policy = policy
        self._pointers = pointers

    def search_approved_evidence_release(
        self, *, request: ApprovedEvidenceSearchRequest
    ) -> ApprovedEvidenceSearchResult:
        """Run one versioned exact search after the existing policy check."""

        self._permit("search_approved_evidence_release")
        if request.release_manifest_hash != self._pointers.evidence_release_manifest_hash:
            raise ToolUnavailableError("request is outside the active evidence release")
        return FrozenReleaseEvidenceSearch(release=self._release).search(request)

    def calculate_approved_evidence(
        self,
        *,
        request: ApprovedCalculationRequest,
        evidence_search_result: ApprovedEvidenceSearchResult,
    ) -> ApprovedCalculationResult:
        """Calculate only from a policy-admitted exact search result."""

        self._permit("calculate_approved_evidence")
        if request.release_manifest_hash != self._pointers.evidence_release_manifest_hash:
            raise ToolUnavailableError("request is outside the active evidence release")
        return DeterministicCalculationAdapter().calculate(
            request=request,
            evidence_search_result=evidence_search_result,
        )

    def create_review_task(
        self,
        *,
        request: ApprovedReviewTaskRequest,
        grounding_context: ReviewTaskGroundingContext,
    ) -> ApprovedReviewTaskResult:
        """Create a typed non-persistent review-required record."""

        self._permit("create_review_task")
        if (
            request.release_id != self._release.evidence_release.release_id
            or request.release_manifest_hash
            != self._pointers.evidence_release_manifest_hash
            or request.runtime_policy_bundle_hash
            != self._pointers.runtime_policy_bundle_hash
            or request.release_gate_policy_hash
            != self._pointers.release_gate_policy_hash
        ):
            raise ToolUnavailableError("request is outside the active policy scope")
        return DeterministicReviewTaskAdapter().create(
            request=request,
            grounding_context=grounding_context,
        )

    def narrative_context(
        self, *, request: ApprovedNarrativeContextRequest
    ) -> ApprovedNarrativeContextResult:
        """Retrieve typed context-only disclosure chunks after policy checks."""

        self._permit("narrative_context")
        if request.release_manifest_hash != self._pointers.evidence_release_manifest_hash:
            raise ToolUnavailableError("request is outside the active evidence release")
        return FrozenReleaseNarrativeContext(release=self._release).retrieve(request)

    def _permit(self, tool: str) -> None:
        try:
            self._policy.authorize_tool(task_pointers=self._pointers, tool_name=tool)
        except Exception as error:
            raise ToolUnavailableError(
                "tool is unavailable under current policy"
            ) from error
