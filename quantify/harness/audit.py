"""Replay-relevant audit manifest construction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
import json

from quantify.engine import EvidenceSnapshot, RestatementSelection

from .sec.client import SecPayload


@dataclass(frozen=True, slots=True)
class AuditManifest:
    manifest_version: str
    analysis_as_of_date: date
    snapshot_id: str
    snapshot_manifest_hash: str
    source_url: str
    source_payload_sha256: str
    cache_hit: bool
    filing_accessions: tuple[str, ...]
    restatement_policy: str
    selected_evidence_ids: tuple[str, ...]
    superseded_evidence_ids: tuple[str, ...]
    normalizer_version: str = "1.0.0"
    adapter_version: str = "1.0.0"
    eligibility_policy_version: str = "1.0.0"
    relation_policy_version: str = "1.0.0"
    counterevidence_policy_version: str = "1.0.0"
    restatement_policy_version: str = "1.0.0"
    disclosure_detector_version: str = "unconfigured"
    extraction_model: str = "unconfigured"
    structured_output_schema_version: str = "1.0.0"
    prompt_hash: str | None = None
    temperature: float | None = None

    @property
    def manifest_hash(self) -> str:
        payload = asdict(self)
        payload["analysis_as_of_date"] = self.analysis_as_of_date.isoformat()
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def build_audit_manifest(
    *,
    snapshot: EvidenceSnapshot,
    selection: RestatementSelection,
    source: SecPayload,
    extraction_model: str = "unconfigured",
    disclosure_detector_version: str = "unconfigured",
    prompt_hash: str | None = None,
    temperature: float | None = None,
) -> AuditManifest:
    return AuditManifest(
        manifest_version="1.0.0",
        analysis_as_of_date=selection.as_of_date,
        snapshot_id=snapshot.snapshot_id,
        snapshot_manifest_hash=snapshot.manifest_hash,
        source_url=source.source_url,
        source_payload_sha256=source.payload_sha256,
        cache_hit=source.cache_hit,
        filing_accessions=tuple(sorted({item.accession for item in snapshot.evidence})),
        restatement_policy=selection.policy.value,
        selected_evidence_ids=selection.selected_evidence_ids,
        superseded_evidence_ids=selection.superseded_evidence_ids,
        extraction_model=extraction_model,
        disclosure_detector_version=disclosure_detector_version,
        prompt_hash=prompt_hash,
        temperature=temperature,
    )
