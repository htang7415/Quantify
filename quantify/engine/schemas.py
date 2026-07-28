"""Immutable domain types for the first deterministic verification slice."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json


class Relation(StrEnum):
    """Closed relation vocabulary supported by this slice."""

    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"


class VerificationOutcome(StrEnum):
    """Pre-disclosure outcome for one validated typed claim."""

    VERIFIED = "verified"
    UNSUPPORTED = "unsupported"
    COUNTEREVIDENCE = "counterevidence"


class EvidenceEligibilityReason(StrEnum):
    """Why an evidence value may enter deterministic verification."""

    ELIGIBLE = "eligible"
    MISSING_PROVENANCE = "missing_provenance"
    FUTURE_FILING = "future_filing"
    ENTITY_SCOPE_MISMATCH = "entity_scope_mismatch"
    PERIOD_ALIGNMENT_MISMATCH = "period_alignment_mismatch"
    UNIT_MISMATCH = "unit_mismatch"
    TRANSFORMATION_FAILURE = "transformation_failure"


class RestatementPolicy(StrEnum):
    """Versioned choices for selecting competing facts for one semantic fact."""

    AS_FILED_AT_CUTOFF = "as_filed_at_cutoff"
    LATEST_AVAILABLE_AT_CUTOFF = "latest_available_at_cutoff"
    LATEST_KNOWN = "latest_known"


@dataclass(frozen=True, slots=True)
class EvidenceValue:
    """One normalized, eligible financial fact from a declared source."""

    evidence_id: str
    entity_cik: str
    metric: str
    value: Decimal
    unit: str
    period_start: date
    period_end: date
    accession: str
    filed_at: date
    source_url: str
    eligible: bool = True

    @property
    def semantic_key(self) -> tuple[str, str, str, date, date]:
        """Identity fields that must match before a fact can counter a claim."""

        return (
            self.entity_cik,
            self.metric,
            self.unit,
            self.period_start,
            self.period_end,
        )

    @property
    def comparability_key(self) -> tuple[str, str, str]:
        """Fields that must agree before two periods can be compared."""

        return (self.entity_cik, self.metric, self.unit)


@dataclass(frozen=True, slots=True)
class EvidenceSnapshot:
    """A canonical, immutable evidence pool for deterministic verification."""

    snapshot_id: str
    evidence: tuple[EvidenceValue, ...]
    manifest_hash: str

    @classmethod
    def freeze(
        cls,
        *,
        snapshot_id: str,
        evidence: tuple[EvidenceValue, ...],
        allow_conflicting_evidence: bool = False,
    ) -> "EvidenceSnapshot":
        """Canonicalize evidence and derive a content-addressed manifest hash.

        A production snapshot must contain at most one eligible fact for a
        semantic identity. The explicit escape hatch exists only for narrow
        regression cases that exercise counterevidence behavior before a
        restatement policy is applied.
        """

        canonical_evidence = tuple(sorted(evidence, key=lambda item: item.evidence_id))
        evidence_ids = [item.evidence_id for item in canonical_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique within a snapshot")
        if not allow_conflicting_evidence:
            semantic_keys = [
                item.semantic_key for item in canonical_evidence if item.eligible
            ]
            if len(semantic_keys) != len(set(semantic_keys)):
                raise ValueError(
                    "snapshot contains unresolved eligible facts with the same semantic identity"
                )

        canonical_payload = {
            "snapshot_id": snapshot_id,
            "evidence": [
                {
                    **asdict(item),
                    "value": str(item.value),
                    "period_start": item.period_start.isoformat(),
                    "period_end": item.period_end.isoformat(),
                    "filed_at": item.filed_at.isoformat(),
                }
                for item in canonical_evidence
            ],
        }
        encoded = json.dumps(
            canonical_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return cls(
            snapshot_id=snapshot_id,
            evidence=canonical_evidence,
            manifest_hash=sha256(encoded).hexdigest(),
        )

    def evidence_by_id(self, evidence_id: str) -> EvidenceValue | None:
        return next(
            (item for item in self.evidence if item.evidence_id == evidence_id), None
        )


@dataclass(frozen=True, slots=True)
class EvidenceEligibilityDecision:
    """A deterministic eligibility decision retained for audit and replay."""

    evidence_id: str
    reason: EvidenceEligibilityReason


@dataclass(frozen=True, slots=True)
class RestatementSelection:
    """Selected and superseded facts under one restatement policy."""

    policy: RestatementPolicy
    as_of_date: date
    selected_evidence_ids: tuple[str, ...]
    superseded_evidence_ids: tuple[str, ...]
    eligibility_decisions: tuple[EvidenceEligibilityDecision, ...]


@dataclass(frozen=True, slots=True)
class MetricThresholdClaim:
    """A typed claim that one reported fact is above or below a fixed threshold."""

    claim_id: str
    cited_evidence_id: str
    relation: Relation
    threshold: Decimal

    @property
    def cited_evidence_ids(self) -> tuple[str, ...]:
        return (self.cited_evidence_id,)


@dataclass(frozen=True, slots=True)
class MetricComparisonClaim:
    """A typed claim that compares the same metric across two periods."""

    claim_id: str
    left_evidence_id: str
    relation: Relation
    right_evidence_id: str

    @property
    def cited_evidence_ids(self) -> tuple[str, ...]:
        return (self.left_evidence_id, self.right_evidence_id)


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Auditable result from local warrant and CE1-style counterevidence checks."""

    claim_id: str
    outcome: VerificationOutcome
    cited_evidence_ids: tuple[str, ...]
    counterevidence_evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LocalWarrantResult:
    """The deterministic local-support decision for one typed claim."""

    claim_id: str
    passed: bool
    cited_evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CounterevidencePair:
    """One eligible evidence item that directly defeats a locally warranted claim."""

    claim_id: str
    evidence_id: str


@dataclass(frozen=True, slots=True)
class ClaimAnalysisResult:
    """Separate local-warrant and CE1 outputs for a frozen snapshot."""

    local_warrants: tuple[LocalWarrantResult, ...]
    counterevidence_pairs: tuple[CounterevidencePair, ...]


class DisclosureStatus(StrEnum):
    """Harness assessment of how a report treats defeating evidence."""

    NOT_DISCLOSED = "not_disclosed"
    DISCLOSED_SAME_SENTENCE = "disclosed_same_sentence"
    DISCLOSED_ELSEWHERE = "disclosed_elsewhere"
    AMBIGUOUS = "ambiguous"


class ClaimVerdict(StrEnum):
    """Final deterministic claim verdict after disclosure assessment."""

    VERIFIED = "verified"
    UNSUPPORTED = "unsupported"
    DEFEATED = "defeated"
    QUALIFIED = "qualified"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


@dataclass(frozen=True, slots=True)
class DisclosureAssessment:
    """One harness-supplied assessment for a typed claim × CE1 pair."""

    claim_id: str
    defeating_evidence_id: str
    status: DisclosureStatus
    supporting_report_span_ids: tuple[str, ...] = ()
    detector_version: str = "manual-v1"
    prompt_hash: str | None = None


@dataclass(frozen=True, slots=True)
class CounterevidenceDetail:
    """Disclosure status retained for every defeating evidence item."""

    evidence_id: str
    disclosure_status: DisclosureStatus
    report_span_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ComposedClaimVerdict:
    """Final verdict with every CE1 detail preserved for review."""

    claim_id: str
    verdict: ClaimVerdict
    counterevidence_detail: tuple[CounterevidenceDetail, ...] = ()


class ReviewReason(StrEnum):
    """Reasons that require a reviewer rather than a negative accusation."""

    REPORT_SPAN_NOT_GROUNDED = "report_span_not_grounded"
    PARTIAL_CONTRASTIVE_EXTRACTION = "partial_contrastive_extraction"
    INVALID_EVIDENCE_REFERENCE = "invalid_evidence_reference"
    EXTRACTION_SCHEMA_FAILURE = "extraction_schema_failure"


class StatementClassification(StrEnum):
    """Conservative classification before a statement enters the engine."""

    CLASSIFIED = "classified"
    UNCLASSIFIED = "unclassified"
    NON_FACTUAL = "non_factual"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


@dataclass(frozen=True, slots=True)
class ReportSpan:
    """Exact sentence and claim-fragment offsets in submitted report text."""

    span_id: str
    sentence_text: str
    sentence_start: int
    sentence_end: int
    claim_fragment: str
    fragment_start: int
    fragment_end: int
    contrastive_markers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewItem:
    """A fail-safe routing item produced by harness validation."""

    statement_id: str
    reason: ReviewReason
    message: str
    report_span_ids: tuple[str, ...] = ()
    claim_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
