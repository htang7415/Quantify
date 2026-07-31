"""Offline evidence-release gate, approval, catalog, rollback, and revocation controls."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
import re

from quantify.release_factory import EvidenceRelease
from quantify.policy_control import ReleaseGatePolicy


class ReleaseOperationError(ValueError): pass
class ReleaseLane(StrEnum): A = "lane_a"; B = "lane_b"
class ReleaseStatus(StrEnum): APPROVED = "approved"; REVOKED = "revoked"; ROLLED_BACK = "rolled_back"

_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")

@dataclass(frozen=True, slots=True)
class SourceValidation:
    source_id: str; licensed_or_public: bool; frozen_payload_hash: str; freshness_days: int
    def __post_init__(self):
        if not self.source_id or not isinstance(self.licensed_or_public, bool) or not _HASH_PATTERN.fullmatch(self.frozen_payload_hash) or self.freshness_days < 0: raise ReleaseOperationError("source validation is invalid")

@dataclass(frozen=True, slots=True)
class ReleaseEvaluation:
    automated_pass_rate_basis_points: int; review_exception_rate_basis_points: int; correction_rate_basis_points: int
    def __post_init__(self):
        if any(not 0 <= v <= 10_000 for v in (self.automated_pass_rate_basis_points,self.review_exception_rate_basis_points,self.correction_rate_basis_points)): raise ReleaseOperationError("release evaluation is invalid")

@dataclass(frozen=True, slots=True)
class ReleaseGateThresholds:
    minimum_pass_rate_basis_points: int; maximum_review_exception_rate_basis_points: int; maximum_correction_rate_basis_points: int; maximum_source_age_days: int
    lane_a_spot_review_required: bool = True
    lane_b_reviewer_approval_required: bool = True
    def __post_init__(self):
        if any(not 0 <= value <= 10_000 for value in (self.minimum_pass_rate_basis_points,self.maximum_review_exception_rate_basis_points,self.maximum_correction_rate_basis_points)) or self.maximum_source_age_days < 0:
            raise ReleaseOperationError("release gate thresholds are invalid")
    @classmethod
    def from_policy(cls, policy: ReleaseGatePolicy) -> "ReleaseGateThresholds":
        return cls(
            minimum_pass_rate_basis_points=policy.minimum_automated_pass_rate_basis_points,
            maximum_review_exception_rate_basis_points=policy.maximum_review_exception_rate_basis_points,
            maximum_correction_rate_basis_points=policy.maximum_correction_rate_basis_points,
            maximum_source_age_days=policy.maximum_source_age_days,
            lane_a_spot_review_required=policy.lane_a_spot_review_required,
            lane_b_reviewer_approval_required=policy.lane_b_reviewer_approval_required,
        )

@dataclass(frozen=True, slots=True)
class ReviewerApproval:
    reviewer_id: str; approval_record_hash: str
    def __post_init__(self):
        if not self.reviewer_id or len(self.approval_record_hash) != 64: raise ReleaseOperationError("reviewer approval is invalid")

@dataclass(frozen=True, slots=True)
class ReleaseGateRecord:
    release_hash: str; lane: ReleaseLane; approved: bool; reasons: tuple[str, ...]; reviewer: ReviewerApproval | None
    def __post_init__(self):
        if not _HASH_PATTERN.fullmatch(self.release_hash) or len(set(self.reasons)) != len(self.reasons):
            raise ReleaseOperationError("release gate record is invalid")
    @property
    def manifest_hash(self) -> str:
        return sha256(json.dumps({"release_hash":self.release_hash,"lane":self.lane.value,"approved":self.approved,"reasons":self.reasons,"reviewer":None if self.reviewer is None else {"reviewer_id":self.reviewer.reviewer_id,"approval_record_hash":self.reviewer.approval_record_hash}},sort_keys=True,separators=(",",":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ReleaseApprovalRecord:
    """Canonical, replayable offline release-gate decision."""

    release_manifest_hash: str
    release_gate_policy_hash: str
    release_gate_record_hash: str
    source_validation_hashes: tuple[str, ...]
    evaluation_hash: str
    lane: ReleaseLane
    reasons: tuple[str, ...]
    reviewer_approval_record_hash: str | None
    approved: bool

    def __post_init__(self):
        hashes = (
            self.release_manifest_hash,
            self.release_gate_policy_hash,
            self.release_gate_record_hash,
            self.evaluation_hash,
            *self.source_validation_hashes,
        )
        if not hashes or any(not _HASH_PATTERN.fullmatch(item) for item in hashes) or len(set(self.source_validation_hashes)) != len(self.source_validation_hashes) or len(set(self.reasons)) != len(self.reasons) or (self.reviewer_approval_record_hash is not None and not _HASH_PATTERN.fullmatch(self.reviewer_approval_record_hash)):
            raise ReleaseOperationError("release approval record is invalid")

    @property
    def manifest_hash(self) -> str:
        return sha256(
            json.dumps(
                {
                    "release_manifest_hash": self.release_manifest_hash,
                    "release_gate_policy_hash": self.release_gate_policy_hash,
                    "release_gate_record_hash": self.release_gate_record_hash,
                    "source_validation_hashes": self.source_validation_hashes,
                    "evaluation_hash": self.evaluation_hash,
                    "lane": self.lane.value,
                    "reasons": self.reasons,
                    "reviewer_approval_record_hash": self.reviewer_approval_record_hash,
                    "approved": self.approved,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "release_manifest_hash": self.release_manifest_hash,
            "release_gate_policy_hash": self.release_gate_policy_hash,
            "release_gate_record_hash": self.release_gate_record_hash,
            "source_validation_hashes": list(self.source_validation_hashes),
            "evaluation_hash": self.evaluation_hash,
            "lane": self.lane.value,
            "reasons": list(self.reasons),
            "reviewer_approval_record_hash": self.reviewer_approval_record_hash,
            "approved": self.approved,
            "manifest_hash": self.manifest_hash,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "ReleaseApprovalRecord":
        if not isinstance(payload, dict):
            raise ReleaseOperationError("release approval record is invalid")
        expected = {
            "release_manifest_hash", "release_gate_policy_hash", "release_gate_record_hash",
            "source_validation_hashes", "evaluation_hash", "lane", "reasons",
            "reviewer_approval_record_hash", "approved", "manifest_hash",
        }
        if set(payload) != expected:
            raise ReleaseOperationError("release approval record is invalid")
        sources, reasons = payload["source_validation_hashes"], payload["reasons"]
        reviewer = payload["reviewer_approval_record_hash"]
        if (
            not isinstance(payload["approved"], bool)
            or not isinstance(sources, list) or not all(isinstance(item, str) for item in sources)
            or not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons)
            or (reviewer is not None and not isinstance(reviewer, str))
        ):
            raise ReleaseOperationError("release approval record is invalid")
        try:
            record = cls(
                release_manifest_hash=str(payload["release_manifest_hash"]),
                release_gate_policy_hash=str(payload["release_gate_policy_hash"]),
                release_gate_record_hash=str(payload["release_gate_record_hash"]),
                source_validation_hashes=tuple(sources), evaluation_hash=str(payload["evaluation_hash"]),
                lane=ReleaseLane(str(payload["lane"])), reasons=tuple(reasons),
                reviewer_approval_record_hash=reviewer, approved=payload["approved"],
            )
        except (TypeError, ValueError) as error:
            raise ReleaseOperationError("release approval record is invalid") from error
        if payload["manifest_hash"] != record.manifest_hash:
            raise ReleaseOperationError("release approval record does not replay")
        return record


def _source_hash(source: SourceValidation) -> str:
    return sha256(json.dumps({"source_id":source.source_id,"licensed_or_public":source.licensed_or_public,"frozen_payload_hash":source.frozen_payload_hash,"freshness_days":source.freshness_days},sort_keys=True,separators=(",",":")).encode()).hexdigest()


def _evaluation_hash(evaluation: ReleaseEvaluation) -> str:
    return sha256(json.dumps({"automated_pass_rate_basis_points":evaluation.automated_pass_rate_basis_points,"review_exception_rate_basis_points":evaluation.review_exception_rate_basis_points,"correction_rate_basis_points":evaluation.correction_rate_basis_points},sort_keys=True,separators=(",",":")).encode()).hexdigest()


def gate_release(
    *,
    release: EvidenceRelease,
    sources: tuple[SourceValidation, ...],
    evaluation: ReleaseEvaluation,
    policy: ReleaseGatePolicy,
    lane: ReleaseLane,
    reviewer: ReviewerApproval | None = None,
) -> ReleaseApprovalRecord:
    """Evaluate one release only against the selected immutable gate policy."""

    gate = evaluate_release(
        release=release,
        sources=sources,
        evaluation=evaluation,
        thresholds=ReleaseGateThresholds.from_policy(policy),
        lane=lane,
        reviewer=reviewer,
    )
    return ReleaseApprovalRecord(
        release_manifest_hash=release.manifest_hash,
        release_gate_policy_hash=policy.content_hash,
        release_gate_record_hash=gate.manifest_hash,
        source_validation_hashes=tuple(sorted(_source_hash(source) for source in sources)),
        evaluation_hash=_evaluation_hash(evaluation),
        lane=lane,
        reasons=gate.reasons,
        reviewer_approval_record_hash=(reviewer.approval_record_hash if reviewer is not None else None),
        approved=gate.approved,
    )

def evaluate_release(*, release: EvidenceRelease, sources: tuple[SourceValidation,...], evaluation: ReleaseEvaluation, thresholds: ReleaseGateThresholds, lane: ReleaseLane, reviewer: ReviewerApproval | None = None) -> ReleaseGateRecord:
    reasons=[]
    if not sources: reasons.append("no_validated_source")
    if any(not s.licensed_or_public for s in sources): reasons.append("source_not_licensed_or_public")
    if any(s.freshness_days > thresholds.maximum_source_age_days for s in sources): reasons.append("source_stale")
    if evaluation.automated_pass_rate_basis_points < thresholds.minimum_pass_rate_basis_points: reasons.append("automated_pass_rate")
    if evaluation.review_exception_rate_basis_points > thresholds.maximum_review_exception_rate_basis_points: reasons.append("review_exception_rate")
    if evaluation.correction_rate_basis_points > thresholds.maximum_correction_rate_basis_points: reasons.append("correction_rate")
    if lane is ReleaseLane.A and thresholds.lane_a_spot_review_required and reviewer is None: reasons.append("lane_a_spot_reviewer_required")
    if lane is ReleaseLane.B and thresholds.lane_b_reviewer_approval_required and reviewer is None: reasons.append("lane_b_reviewer_required")
    return ReleaseGateRecord(release.manifest_hash,lane,not reasons,tuple(reasons),reviewer)

@dataclass(frozen=True, slots=True)
class CatalogEntry:
    release_id: str; release_hash: str; status: ReleaseStatus


@dataclass(frozen=True, slots=True)
class ReleaseCatalogManifest:
    """Canonical CDN-safe catalog containing only currently serveable releases."""

    schema_version: str
    entries: tuple[CatalogEntry, ...]

    @property
    def manifest_hash(self) -> str:
        return sha256(self.serialized()).hexdigest()

    def serialized(self) -> bytes:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "entries": [
                    {"release_id": entry.release_id, "release_hash": entry.release_hash}
                    for entry in self.entries
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

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
    def serving_manifest(self) -> ReleaseCatalogManifest:
        return ReleaseCatalogManifest(
            schema_version="1.0.0",
            entries=tuple(
                sorted(
                    (entry for entry in self._entries.values() if entry.status is ReleaseStatus.APPROVED),
                    key=lambda entry: entry.release_id,
                )
            ),
        )
    def _set(self, release_id: str, status: ReleaseStatus) -> None:
        entry=self._entries.get(release_id)
        if entry is None: raise ReleaseOperationError("release is not published")
        self._entries[release_id]=CatalogEntry(entry.release_id,entry.release_hash,status)
