"""Replay-relevant audit manifest construction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
import json

from quantify.engine import EvidenceSnapshot, EvidenceValue, RestatementSelection

from .sec.client import SecPayload


@dataclass(frozen=True, slots=True)
class AuditManifest:
    manifest_version: str
    analysis_as_of_date: date
    snapshot_id: str
    snapshot_manifest_hash: str
    source_url: str
    source_payload_sha256: str
    source_retrieved_at: str
    cache_hit: bool
    requested_forms: tuple[str, ...]
    resolved_filing_accessions: tuple[str, ...]
    filing_accessions: tuple[str, ...]
    superseded_filing_accessions: tuple[str, ...]
    restatement_policy: str
    selected_evidence_ids: tuple[str, ...]
    superseded_evidence_ids: tuple[str, ...]
    selection_rationale: str
    request_timestamp: str
    acquisition_records: tuple[tuple[str, str], ...] = ()
    agent_resolution_records: tuple[tuple[str, str], ...] = ()
    normalizer_version: str = "1.1.0"
    adapter_version: str = "1.0.0"
    eligibility_policy_version: str = "1.0.0"
    relation_policy_version: str = "1.0.0"
    counterevidence_policy_version: str = "1.0.0"
    persistence_policy_version: str = "1.0.0"
    restatement_policy_version: str = "1.0.0"
    agent_resolution_policy_version: str = "1.0.0"
    disclosure_detector_version: str = "unconfigured"
    extraction_model: str = "unconfigured"
    structured_output_schema_version: str = "1.0.0"
    prompt_hash: str | None = None
    temperature: float | None = None
    evidence_fixture_manifest_hash: str | None = None
    deployment_image_digest: str | None = None
    canonical_claim_source_spans: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def manifest_hash(self) -> str:
        payload = asdict(self)
        payload["analysis_as_of_date"] = self.analysis_as_of_date.isoformat()
        # Cache status is operational observability, not replay semantics. The
        # same frozen payload must produce one semantic manifest regardless of
        # whether this particular request read it from cache or the network.
        payload.pop("cache_hit")
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
    requested_forms: tuple[str, ...] = ("10-K", "10-Q"),
    resolved_filing_accessions: tuple[str, ...] = (),
    request_timestamp: str | None = None,
    normalized_evidence: tuple[EvidenceValue, ...] | None = None,
    acquisition_records: tuple[tuple[str, str], ...] = (),
) -> AuditManifest:
    selected_accessions = tuple(sorted({item.accession for item in snapshot.evidence}))
    evidence_by_id = {
        item.evidence_id: item for item in normalized_evidence or snapshot.evidence
    }
    missing_audit_evidence_ids = set(selection.superseded_evidence_ids).difference(
        evidence_by_id
    )
    if missing_audit_evidence_ids:
        raise ValueError(
            "restatement audit requires normalized evidence for superseded facts"
        )
    superseded_accessions = tuple(
        sorted(
            {
                evidence_by_id[evidence_id].accession
                for evidence_id in selection.superseded_evidence_ids
            }
        )
    )
    return AuditManifest(
        manifest_version="1.5.0",
        analysis_as_of_date=selection.as_of_date,
        snapshot_id=snapshot.snapshot_id,
        snapshot_manifest_hash=snapshot.manifest_hash,
        source_url=source.source_url,
        source_payload_sha256=source.payload_sha256,
        source_retrieved_at=source.retrieved_at,
        cache_hit=source.cache_hit,
        requested_forms=tuple(
            sorted(form.removesuffix("/A") for form in requested_forms)
        ),
        resolved_filing_accessions=(
            tuple(sorted(resolved_filing_accessions))
            if resolved_filing_accessions
            else selected_accessions
        ),
        filing_accessions=selected_accessions,
        superseded_filing_accessions=superseded_accessions,
        restatement_policy=selection.policy.value,
        selected_evidence_ids=selection.selected_evidence_ids,
        superseded_evidence_ids=selection.superseded_evidence_ids,
        selection_rationale=(
            f"{selection.policy.value} at {selection.as_of_date.isoformat()}: "
            f"selected accessions {selected_accessions} and "
            f"superseded accessions {superseded_accessions}"
        ),
        request_timestamp=request_timestamp or source.retrieved_at,
        acquisition_records=tuple(sorted(acquisition_records)),
        extraction_model=extraction_model,
        disclosure_detector_version=disclosure_detector_version,
        prompt_hash=prompt_hash,
        temperature=temperature,
    )
