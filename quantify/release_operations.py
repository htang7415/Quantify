"""Offline evidence-release gate, approval, catalog, rollback, and revocation controls."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json

from quantify.release_factory import EvidenceRelease


class ReleaseOperationError(ValueError): pass
class ReleaseLane(StrEnum): A = "lane_a"; B = "lane_b"
class ReleaseStatus(StrEnum): APPROVED = "approved"; REVOKED = "revoked"; ROLLED_BACK = "rolled_back"

@dataclass(frozen=True, slots=True)
class SourceValidation:
    source_id: str; licensed_or_public: bool; frozen_payload_hash: str; freshness_days: int
    def __post_init__(self):
        if not self.source_id or len(self.frozen_payload_hash) != 64 or self.freshness_days < 0: raise ReleaseOperationError("source validation is invalid")

@dataclass(frozen=True, slots=True)
class ReleaseEvaluation:
    automated_pass_rate_basis_points: int; review_exception_rate_basis_points: int; correction_rate_basis_points: int
    def __post_init__(self):
        if any(not 0 <= v <= 10_000 for v in (self.automated_pass_rate_basis_points,self.review_exception_rate_basis_points,self.correction_rate_basis_points)): raise ReleaseOperationError("release evaluation is invalid")

@dataclass(frozen=True, slots=True)
class ReleaseGateThresholds:
    minimum_pass_rate_basis_points: int; maximum_review_exception_rate_basis_points: int; maximum_correction_rate_basis_points: int; maximum_source_age_days: int

@dataclass(frozen=True, slots=True)
class ReviewerApproval:
    reviewer_id: str; approval_record_hash: str
    def __post_init__(self):
        if not self.reviewer_id or len(self.approval_record_hash) != 64: raise ReleaseOperationError("reviewer approval is invalid")

@dataclass(frozen=True, slots=True)
class ReleaseGateRecord:
    release_hash: str; lane: ReleaseLane; approved: bool; reasons: tuple[str, ...]; reviewer: ReviewerApproval | None

def evaluate_release(*, release: EvidenceRelease, sources: tuple[SourceValidation,...], evaluation: ReleaseEvaluation, thresholds: ReleaseGateThresholds, lane: ReleaseLane, reviewer: ReviewerApproval | None = None) -> ReleaseGateRecord:
    reasons=[]
    if not sources: reasons.append("no_validated_source")
    if any(not s.licensed_or_public for s in sources): reasons.append("source_not_licensed_or_public")
    if any(s.freshness_days > thresholds.maximum_source_age_days for s in sources): reasons.append("source_stale")
    if evaluation.automated_pass_rate_basis_points < thresholds.minimum_pass_rate_basis_points: reasons.append("automated_pass_rate")
    if evaluation.review_exception_rate_basis_points > thresholds.maximum_review_exception_rate_basis_points: reasons.append("review_exception_rate")
    if evaluation.correction_rate_basis_points > thresholds.maximum_correction_rate_basis_points: reasons.append("correction_rate")
    if lane is ReleaseLane.B and reviewer is None: reasons.append("lane_b_reviewer_required")
    return ReleaseGateRecord(release.manifest_hash,lane,not reasons,tuple(reasons),reviewer)

@dataclass(frozen=True, slots=True)
class CatalogEntry:
    release_id: str; release_hash: str; status: ReleaseStatus

class ReleaseCatalog:
    """Immutable approved entries; serving excludes revoked/rolled-back releases."""
    def __init__(self): self._entries: dict[str,CatalogEntry]={}
    def publish(self, *, release: EvidenceRelease, gate: ReleaseGateRecord) -> CatalogEntry:
        if gate.release_hash != release.manifest_hash or not gate.approved: raise ReleaseOperationError("release gate did not approve publication")
        entry=CatalogEntry(release.release_id,release.manifest_hash,ReleaseStatus.APPROVED)
        old=self._entries.get(release.release_id)
        if old and old.release_hash != entry.release_hash: raise ReleaseOperationError("release id is immutable")
        self._entries[release.release_id]=entry; return entry
    def revoke(self, *, release_id: str) -> None: self._set(release_id,ReleaseStatus.REVOKED)
    def rollback(self, *, release_id: str) -> None: self._set(release_id,ReleaseStatus.ROLLED_BACK)
    def serving_entry(self, *, release_id: str) -> CatalogEntry | None:
        entry=self._entries.get(release_id); return entry if entry and entry.status is ReleaseStatus.APPROVED else None
    def _set(self, release_id: str, status: ReleaseStatus) -> None:
        entry=self._entries.get(release_id)
        if entry is None: raise ReleaseOperationError("release is not published")
        self._entries[release_id]=CatalogEntry(entry.release_id,entry.release_hash,status)
