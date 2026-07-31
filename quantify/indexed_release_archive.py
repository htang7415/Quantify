"""Canonical, replay-checked serialization for an indexed evidence release."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal
import json
from typing import Mapping

from quantify.engine import EvidenceEligibilityDecision, EvidenceEligibilityReason, EvidenceSnapshot, EvidenceValue, RestatementPolicy, RestatementSelection, SourceType
from quantify.harness.audit import AuditManifest
from quantify.harness.snapshots import SnapshotBuild
from quantify.indexed_release import (
    IndexedEvidenceRelease,
    IndexedSnapshot,
    IndexedSnapshotProvider,
    IndexedSnapshotRequest,
    IndexedReleaseError,
    NarrativeDisclosureChunk,
    compile_indexed_release,
)
from quantify.release_factory import EvidenceRelease

_VERSION = "1.1.0"

def _evidence(value: EvidenceValue) -> dict[str, object]:
    raw = asdict(value)
    for field in ("value", "period_start", "period_end", "filed_at"):
        raw[field] = str(raw[field]) if field == "value" else raw[field].isoformat()
    return raw

def _load_evidence(raw: Mapping[str, object]) -> EvidenceValue:
    return EvidenceValue(**{**raw, "value": Decimal(str(raw["value"])), "period_start": date.fromisoformat(str(raw["period_start"])), "period_end": date.fromisoformat(str(raw["period_end"])), "filed_at": date.fromisoformat(str(raw["filed_at"])), "derived_from_evidence_ids": tuple(raw.get("derived_from_evidence_ids", ()))})

def _audit(manifest: AuditManifest) -> dict[str, object]:
    raw = asdict(manifest); raw["analysis_as_of_date"] = manifest.analysis_as_of_date.isoformat()
    return raw

def _load_audit(raw: Mapping[str, object]) -> AuditManifest:
    values = dict(raw); values["analysis_as_of_date"] = date.fromisoformat(str(values["analysis_as_of_date"]))
    for field in ("requested_forms", "resolved_filing_accessions", "filing_accessions", "superseded_filing_accessions", "selected_evidence_ids", "superseded_evidence_ids"):
        values[field] = tuple(values[field])
    for field in ("acquisition_records", "agent_resolution_records", "canonical_claim_source_spans"):
        values[field] = tuple(tuple(item) for item in values[field])
    return AuditManifest(**values)

class IndexedReleaseArchive:
    @staticmethod
    def dump(release: IndexedEvidenceRelease) -> bytes:
        snapshots=[]
        for item in release.snapshots:
            build=item.build
            snapshots.append({"request": {"cik": item.request.cik, "as_of_date": item.request.as_of_date.isoformat(), "forms": item.request.forms, "acquisition_records": item.request.acquisition_records}, "snapshot_id": build.snapshot.snapshot_id, "source_type": build.snapshot.source_type.value, "visible_evidence_ids": build.snapshot.visible_evidence_ids, "snapshot_manifest_hash": build.snapshot.manifest_hash, "evidence": [_evidence(value) for value in build.snapshot.evidence], "selection": {"policy": build.selection.policy.value, "as_of_date": build.selection.as_of_date.isoformat(), "selected": build.selection.selected_evidence_ids, "superseded": build.selection.superseded_evidence_ids, "decisions": [(d.evidence_id,d.reason.value) for d in build.selection.eligibility_decisions]}, "audit": _audit(build.audit_manifest)})
        payload={
            "schema_version":_VERSION,
            "evidence_release":release.evidence_release.as_dict(),
            "indexed_release_manifest_hash":release.manifest_hash,
            "exact_fact_index_hash":release.exact_facts.manifest_hash,
            "narrative_context_index_hash":release.narrative_context.manifest_hash,
            "narrative_chunks":[asdict(chunk) for chunk in release.narrative_context.chunks],
            "snapshots":snapshots,
        }
        return json.dumps(payload,sort_keys=True,separators=(",",":"),default=list).encode()

    @staticmethod
    def load(payload: bytes) -> "ArchivedIndexedSnapshotProvider":
        try: raw=json.loads(payload)
        except (TypeError,json.JSONDecodeError) as error: raise IndexedReleaseError("indexed release archive is invalid") from error
        if not isinstance(raw,dict) or raw.get("schema_version")!=_VERSION or not isinstance(raw.get("snapshots"),list) or not isinstance(raw.get("narrative_chunks"),list): raise IndexedReleaseError("indexed release archive schema is invalid")
        release_raw=raw.get("evidence_release")
        if not isinstance(release_raw,dict): raise IndexedReleaseError("indexed release archive has no release manifest")
        declared=release_raw.get("manifest_hash")
        release_payload={key:value for key,value in release_raw.items() if key != "manifest_hash"}
        try: release=EvidenceRelease(**release_payload)
        except (TypeError,ValueError) as error: raise IndexedReleaseError("indexed release archive manifest is invalid") from error
        if release.manifest_hash != declared: raise IndexedReleaseError("indexed release archive manifest does not replay")
        try:
            snapshots=tuple(_indexed_snapshot(item) for item in raw["snapshots"])
            chunks=tuple(NarrativeDisclosureChunk(**chunk) for chunk in raw["narrative_chunks"])
            indexed=compile_indexed_release(
                evidence_release=release,
                snapshots=snapshots,
                narrative_chunks=chunks,
            )
        except IndexedReleaseError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise IndexedReleaseError("indexed release archive does not rebuild") from error
        if indexed.manifest_hash != raw.get("indexed_release_manifest_hash") or indexed.exact_facts.manifest_hash != raw.get("exact_fact_index_hash") or indexed.narrative_context.manifest_hash != raw.get("narrative_context_index_hash"):
            raise IndexedReleaseError("indexed release archive index hashes do not replay")
        return ArchivedIndexedSnapshotProvider(indexed_release=indexed)


class S3IndexedReleaseArchiveStore:
    """Encrypted, content-addressed archive storage for the offline factory."""
    def __init__(self, *, bucket_name: str, client: object) -> None:
        if not bucket_name: raise ValueError("indexed release bucket is required")
        self._bucket_name=bucket_name; self._client=client
    def persist(self, release: IndexedEvidenceRelease) -> str:
        payload=IndexedReleaseArchive.dump(release); manifest_hash=release.evidence_release.manifest_hash
        IndexedReleaseArchive.load(payload)
        try:
            self._client.put_object(Bucket=self._bucket_name,Key=f"evidence-releases/v1/{manifest_hash}/indexed-release.json",Body=payload,ContentType="application/json",ServerSideEncryption="aws:kms",BucketKeyEnabled=True,IfNoneMatch="*")
        except Exception as error:
            response=getattr(error,"response",None); code=response.get("Error",{}).get("Code") if isinstance(response,Mapping) else None
            if code not in {"PreconditionFailed","412"}: raise IndexedReleaseError("indexed release archive could not be persisted") from error
            try:
                existing=self.load(evidence_release_manifest_hash=manifest_hash)
                if IndexedReleaseArchive.dump(existing.indexed_release) != payload:
                    raise IndexedReleaseError("existing indexed release archive does not match")
            except IndexedReleaseError:
                raise
            except Exception as read_error:
                raise IndexedReleaseError("existing indexed release archive cannot be verified") from read_error
        return manifest_hash
    def load(self, *, evidence_release_manifest_hash: str) -> ArchivedIndexedSnapshotProvider:
        try:
            response=self._client.get_object(Bucket=self._bucket_name,Key=f"evidence-releases/v1/{evidence_release_manifest_hash}/indexed-release.json")
            body=response["Body"]; payload=body.read() if hasattr(body,"read") else body
            if not isinstance(payload,bytes): raise TypeError
            parsed=json.loads(payload); declared=parsed["evidence_release"]["manifest_hash"]
            if declared != evidence_release_manifest_hash: raise IndexedReleaseError("indexed release archive key does not match manifest")
            return IndexedReleaseArchive.load(payload)
        except IndexedReleaseError: raise
        except Exception as error: raise IndexedReleaseError("indexed release archive is unavailable") from error

def _indexed_snapshot(item: Mapping[str, object]) -> IndexedSnapshot:
    request_raw=item["request"]
    request=IndexedSnapshotRequest(cik=request_raw["cik"],as_of_date=date.fromisoformat(request_raw["as_of_date"]),forms=tuple(request_raw["forms"]),acquisition_records=tuple(tuple(row) for row in request_raw["acquisition_records"]))
    evidence=tuple(_load_evidence(value) for value in item["evidence"])
    snapshot=EvidenceSnapshot.freeze(snapshot_id=item["snapshot_id"],evidence=evidence,source_type=SourceType(item["source_type"]),visible_evidence_ids=tuple(item["visible_evidence_ids"]) if item["visible_evidence_ids"] is not None else None)
    if snapshot.manifest_hash!=item["snapshot_manifest_hash"]: raise IndexedReleaseError("archived snapshot manifest does not replay")
    sel=item["selection"]
    selection=RestatementSelection(policy=RestatementPolicy(sel["policy"]),as_of_date=date.fromisoformat(sel["as_of_date"]),selected_evidence_ids=tuple(sel["selected"]),superseded_evidence_ids=tuple(sel["superseded"]),eligibility_decisions=tuple(EvidenceEligibilityDecision(evidence_id=x,reason=EvidenceEligibilityReason(y)) for x,y in sel["decisions"]))
    audit=_load_audit(item["audit"])
    if audit.snapshot_manifest_hash!=snapshot.manifest_hash: raise IndexedReleaseError("archived audit does not match snapshot")
    return IndexedSnapshot(request=request,build=SnapshotBuild(snapshot=snapshot,selection=selection,audit_manifest=audit))


class ArchivedIndexedSnapshotProvider:
    def __init__(self, *, indexed_release: IndexedEvidenceRelease) -> None:
        self.indexed_release=indexed_release
        self._provider=IndexedSnapshotProvider(indexed_release=indexed_release)

    def build(self, *, cik: str, as_of_date: date, forms: tuple[str,...], acquisition_records=()) -> SnapshotBuild:
        return self._provider.build(
            cik=cik,
            as_of_date=as_of_date,
            forms=forms,
            acquisition_records=acquisition_records,
        )
