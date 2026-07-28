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


@dataclass(frozen=True, slots=True)
class EvidenceSnapshot:
    """A canonical, immutable evidence pool for deterministic verification."""

    snapshot_id: str
    evidence: tuple[EvidenceValue, ...]
    manifest_hash: str

    @classmethod
    def freeze(
        cls, *, snapshot_id: str, evidence: tuple[EvidenceValue, ...]
    ) -> "EvidenceSnapshot":
        """Canonicalize evidence and derive a content-addressed manifest hash."""

        canonical_evidence = tuple(sorted(evidence, key=lambda item: item.evidence_id))
        evidence_ids = [item.evidence_id for item in canonical_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique within a snapshot")

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
class MetricThresholdClaim:
    """A typed claim that one reported fact is above or below a fixed threshold."""

    claim_id: str
    cited_evidence_id: str
    relation: Relation
    threshold: Decimal


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Auditable result from local warrant and CE1-style counterevidence checks."""

    claim_id: str
    outcome: VerificationOutcome
    cited_evidence_id: str
    counterevidence_evidence_ids: tuple[str, ...] = ()
