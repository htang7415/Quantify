"""Bounded autonomous resolution for otherwise fail-closed verification states."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from quantify.engine import ClaimVerdict, EvidenceSnapshot, ReviewReason

from .disclosure import DisclosureDetector
from .extraction import ExtractionResult
from .orchestrator import VerificationReport, verify_report


class AgentResolutionAction(StrEnum):
    """Actions the V1 resolver may take without changing engine semantics."""

    ASSESS_DISCLOSURE = "assess_disclosure"


@dataclass(frozen=True, slots=True)
class AgentResolutionRecord:
    """One replay-visible autonomous action and its deterministic result."""

    action: AgentResolutionAction
    reason: ReviewReason
    outcome: str

    def manifest_entry(self) -> tuple[str, str]:
        return (self.action.value, f"{self.reason.value}:{self.outcome}")


@dataclass(frozen=True, slots=True)
class AgentResolutionOutcome:
    report: VerificationReport
    records: tuple[AgentResolutionRecord, ...]


class AutonomousResolutionLoop:
    """Resolve only an explicitly permitted class of ambiguity.

    The loop never changes a typed claim, evidence snapshot, or engine policy.  It
    may make one disclosure-assessment attempt, then re-run deterministic verdict
    composition.  Any remaining ambiguity stays fail-closed as
    ``requires_agent_resolution`` for a later bounded capability.
    """

    policy_version = "1.0.0"

    def __init__(self, *, max_actions: int = 1) -> None:
        if max_actions < 0 or max_actions > 1:
            raise ValueError("V1 agent resolution supports between zero and one action")
        self._max_actions = max_actions

    def resolve(
        self,
        *,
        report_text: str,
        snapshot: EvidenceSnapshot,
        extraction: ExtractionResult,
        disclosure_detector: DisclosureDetector | None = None,
    ) -> AgentResolutionOutcome:
        initial = verify_report(
            report_text=report_text, snapshot=snapshot, extraction=extraction
        )
        needs_disclosure_resolution = any(
            item.reason
            in {
                ReviewReason.DISCLOSURE_AMBIGUOUS,
                ReviewReason.MISSING_DISCLOSURE_ASSESSMENT,
            }
            for item in initial.review_items
        ) or any(
            item.verdict is ClaimVerdict.REQUIRES_AGENT_RESOLUTION
            for item in initial.claim_verdicts
        )
        if (
            not needs_disclosure_resolution
            or disclosure_detector is None
            or self._max_actions == 0
        ):
            return AgentResolutionOutcome(report=initial, records=())

        resolved = verify_report(
            report_text=report_text,
            snapshot=snapshot,
            extraction=extraction,
            disclosure_detector=disclosure_detector,
        )
        remaining = any(
            item.reason
            in {
                ReviewReason.DISCLOSURE_AMBIGUOUS,
                ReviewReason.MISSING_DISCLOSURE_ASSESSMENT,
            }
            for item in resolved.review_items
        ) or any(
            item.verdict is ClaimVerdict.REQUIRES_AGENT_RESOLUTION
            for item in resolved.claim_verdicts
        )
        reason = next(
            (
                item.reason
                for item in initial.review_items
                if item.reason
                in {
                    ReviewReason.DISCLOSURE_AMBIGUOUS,
                    ReviewReason.MISSING_DISCLOSURE_ASSESSMENT,
                }
            ),
            ReviewReason.MISSING_DISCLOSURE_ASSESSMENT,
        )
        return AgentResolutionOutcome(
            report=resolved,
            records=(
                AgentResolutionRecord(
                    action=AgentResolutionAction.ASSESS_DISCLOSURE,
                    reason=reason,
                    outcome="unresolved" if remaining else "resolved",
                ),
            ),
        )
