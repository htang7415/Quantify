"""Offline-compiled, release-scoped evidence indexes.

The exact-fact index is the only indexed data that may rebuild an
``EvidenceSnapshot`` for deterministic verification.  Narrative disclosures
are deliberately represented by different types and are exposed only through
the context retriever; no conversion from a narrative chunk to an
``EvidenceValue`` exists in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from hashlib import sha256
import json
import re
from urllib.parse import urlparse

from quantify.engine import EvidenceSnapshot, EvidenceValue
from quantify.harness import SnapshotBuild
from quantify.harness.acquisition import EvidenceAcquisitionRecord
from quantify.harness.sec.client import SecCompanyFactsClient
from quantify.release_factory import EvidenceRelease


_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ACCESSION_PATTERN = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_MAX_NARRATIVE_CHARS = 12_000


class IndexedReleaseError(ValueError):
    """A compiled index is malformed, incomplete, or queried out of scope."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _hash(value: object) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _require_hash(value: str, *, field: str) -> None:
    if not _HASH_PATTERN.fullmatch(value):
        raise IndexedReleaseError(f"{field} must be a lowercase SHA-256 hash")


def _normalize_forms(forms: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(sorted({form.removesuffix("/A") for form in forms}))
    if not normalized or any(form not in {"10-K", "10-Q"} for form in normalized):
        raise IndexedReleaseError("indexed snapshot forms are invalid")
    return normalized


@dataclass(frozen=True, slots=True)
class IndexedSnapshotRequest:
    """The exact request identity compiled into a frozen release."""

    cik: str
    as_of_date: date
    forms: tuple[str, ...]
    acquisition_records: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "cik", SecCompanyFactsClient.normalize_cik(self.cik))
        object.__setattr__(self, "forms", _normalize_forms(self.forms))
        canonical_records = tuple(sorted(self.acquisition_records))
        if any(
            not isinstance(request_type, str)
            or not request_type
            or not isinstance(reason, str)
            or not reason
            for request_type, reason in canonical_records
        ):
            raise IndexedReleaseError("indexed acquisition records are invalid")
        if len(canonical_records) != len(set(canonical_records)):
            raise IndexedReleaseError("indexed acquisition records must be unique")
        object.__setattr__(self, "acquisition_records", canonical_records)

    def key(self) -> tuple[str, str, tuple[str, ...], tuple[tuple[str, str], ...]]:
        return (
            self.cik,
            self.as_of_date.isoformat(),
            self.forms,
            self.acquisition_records,
        )


@dataclass(frozen=True, slots=True)
class ExactFactKey:
    """The required exact lookup key for structured evidence."""

    evidence_release_manifest_hash: str
    cik: str
    metric: str
    fiscal_period_start: date
    fiscal_period_end: date
    unit: str

    def __post_init__(self) -> None:
        _require_hash(
            self.evidence_release_manifest_hash,
            field="evidence_release_manifest_hash",
        )
        object.__setattr__(self, "cik", SecCompanyFactsClient.normalize_cik(self.cik))
        if not self.metric or not self.unit or self.fiscal_period_start > self.fiscal_period_end:
            raise IndexedReleaseError("exact fact key is invalid")

    @classmethod
    def from_evidence(
        cls, *, evidence_release_manifest_hash: str, evidence: EvidenceValue
    ) -> "ExactFactKey":
        return cls(
            evidence_release_manifest_hash=evidence_release_manifest_hash,
            cik=evidence.entity_cik,
            metric=evidence.metric,
            fiscal_period_start=evidence.period_start,
            fiscal_period_end=evidence.period_end,
            unit=evidence.unit,
        )

    def payload(self) -> dict[str, str]:
        return {
            "evidence_release_manifest_hash": self.evidence_release_manifest_hash,
            "cik": self.cik,
            "metric": self.metric,
            "fiscal_period_start": self.fiscal_period_start.isoformat(),
            "fiscal_period_end": self.fiscal_period_end.isoformat(),
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class ExactFactRecord:
    """A typed fact plus stable fact/evidence identifiers."""

    fact_id: str
    key: ExactFactKey
    evidence: EvidenceValue

    def __post_init__(self) -> None:
        _require_hash(self.fact_id, field="fact_id")
        if self.key != ExactFactKey.from_evidence(
            evidence_release_manifest_hash=self.key.evidence_release_manifest_hash,
            evidence=self.evidence,
        ):
            raise IndexedReleaseError("fact key does not match evidence")

    @classmethod
    def from_evidence(
        cls, *, evidence_release_manifest_hash: str, evidence: EvidenceValue
    ) -> "ExactFactRecord":
        key = ExactFactKey.from_evidence(
            evidence_release_manifest_hash=evidence_release_manifest_hash,
            evidence=evidence,
        )
        return cls(
            fact_id=_hash(key.payload()),
            key=key,
            evidence=evidence,
        )

    def payload(self) -> dict[str, object]:
        return {
            "fact_id": self.fact_id,
            "key": self.key.payload(),
            "evidence": {
                "evidence_id": self.evidence.evidence_id,
                "entity_cik": self.evidence.entity_cik,
                "metric": self.evidence.metric,
                "value": str(self.evidence.value),
                "unit": self.evidence.unit,
                "period_start": self.evidence.period_start.isoformat(),
                "period_end": self.evidence.period_end.isoformat(),
                "accession": self.evidence.accession,
                "filed_at": self.evidence.filed_at.isoformat(),
                "source_url": self.evidence.source_url,
                "eligible": self.evidence.eligible,
                "is_standard_tag": self.evidence.is_standard_tag,
                "derived_from_evidence_ids": self.evidence.derived_from_evidence_ids,
            },
        }


@dataclass(frozen=True, slots=True)
class ExactFactIndex:
    """A release-scoped map; similarity lookup is intentionally impossible."""

    evidence_release_manifest_hash: str
    records: tuple[ExactFactRecord, ...]

    def __post_init__(self) -> None:
        _require_hash(
            self.evidence_release_manifest_hash,
            field="evidence_release_manifest_hash",
        )
        ordered = tuple(sorted(self.records, key=lambda record: record.fact_id))
        if len({record.fact_id for record in ordered}) != len(ordered):
            raise IndexedReleaseError("exact fact IDs must be unique")
        if any(
            record.key.evidence_release_manifest_hash
            != self.evidence_release_manifest_hash
            for record in ordered
        ):
            raise IndexedReleaseError("exact fact belongs to a different release")
        object.__setattr__(self, "records", ordered)

    @property
    def manifest_hash(self) -> str:
        return _hash(
            {
                "evidence_release_manifest_hash": self.evidence_release_manifest_hash,
                "records": [record.payload() for record in self.records],
            }
        )

    def lookup(self, *, key: ExactFactKey) -> ExactFactRecord | None:
        if key.evidence_release_manifest_hash != self.evidence_release_manifest_hash:
            return None
        return next((record for record in self.records if record.key == key), None)

    def evidence_by_id(self, *, evidence_id: str) -> EvidenceValue | None:
        """Return only an already-compiled exact fact, never narrative context."""

        record = next(
            (record for record in self.records if record.evidence.evidence_id == evidence_id),
            None,
        )
        return record.evidence if record is not None else None


@dataclass(frozen=True, slots=True)
class NarrativeDisclosureChunk:
    """Issuer disclosure context that has no verdict-evidence representation."""

    evidence_release_manifest_hash: str
    cik: str
    filing_accession: str
    filed_at: date
    source_url: str
    source_span: tuple[int, int]
    text: str
    chunk_hash: str

    def __post_init__(self) -> None:
        _require_hash(
            self.evidence_release_manifest_hash,
            field="evidence_release_manifest_hash",
        )
        object.__setattr__(self, "cik", SecCompanyFactsClient.normalize_cik(self.cik))
        if not isinstance(self.filing_accession, str) or not _ACCESSION_PATTERN.fullmatch(
            self.filing_accession
        ):
            raise IndexedReleaseError("narrative filing accession is invalid")
        if not isinstance(self.filed_at, date):
            raise IndexedReleaseError("narrative filing date is invalid")
        parsed_url = urlparse(self.source_url) if isinstance(self.source_url, str) else None
        if (
            parsed_url is None
            or parsed_url.scheme != "https"
            or not parsed_url.netloc
            or parsed_url.username
            or parsed_url.password
        ):
            raise IndexedReleaseError("narrative source URL must be HTTPS")
        if (
            not isinstance(self.source_span, tuple)
            or len(self.source_span) != 2
            or any(not isinstance(item, int) or isinstance(item, bool) for item in self.source_span)
            or self.source_span[0] < 0
            or self.source_span[0] >= self.source_span[1]
        ):
            raise IndexedReleaseError("narrative source span is invalid")
        if (
            not isinstance(self.text, str)
            or not self.text
            or self.text != self.text.strip()
            or len(self.text) > _MAX_NARRATIVE_CHARS
            or self.source_span[1] - self.source_span[0] != len(self.text)
        ):
            raise IndexedReleaseError("narrative disclosure chunk is incomplete")
        if self.chunk_hash != _hash(
            {
                "cik": self.cik,
                "filing_accession": self.filing_accession,
                "filed_at": self.filed_at.isoformat(),
                "source_url": self.source_url,
                "source_span": self.source_span,
                "text": self.text,
            }
        ):
            raise IndexedReleaseError("narrative chunk hash does not match its content")

    @classmethod
    def create(
        cls,
        *,
        evidence_release_manifest_hash: str,
        cik: str,
        filing_accession: str,
        filed_at: date,
        source_url: str,
        source_span: tuple[int, int],
        text: str,
    ) -> "NarrativeDisclosureChunk":
        normalized_cik = SecCompanyFactsClient.normalize_cik(cik)
        if not isinstance(filed_at, date):
            raise IndexedReleaseError("narrative filing date is invalid")
        chunk_hash = _hash(
            {
                "cik": normalized_cik,
                "filing_accession": filing_accession,
                "filed_at": filed_at.isoformat(),
                "source_url": source_url,
                "source_span": source_span,
                "text": text,
            }
        )
        return cls(
            evidence_release_manifest_hash=evidence_release_manifest_hash,
            cik=normalized_cik,
            filing_accession=filing_accession,
            filed_at=filed_at,
            source_url=source_url,
            source_span=source_span,
            text=text,
            chunk_hash=chunk_hash,
        )


@dataclass(frozen=True, slots=True)
class NarrativeContextIndex:
    """Release-filtered issuer-disclosure context, never facts."""

    evidence_release_manifest_hash: str
    chunks: tuple[NarrativeDisclosureChunk, ...] = ()

    def __post_init__(self) -> None:
        _require_hash(
            self.evidence_release_manifest_hash,
            field="evidence_release_manifest_hash",
        )
        ordered = tuple(sorted(self.chunks, key=lambda chunk: chunk.chunk_hash))
        if len({chunk.chunk_hash for chunk in ordered}) != len(ordered):
            raise IndexedReleaseError("narrative chunk hashes must be unique")
        if any(
            chunk.evidence_release_manifest_hash
            != self.evidence_release_manifest_hash
            for chunk in ordered
        ):
            raise IndexedReleaseError("narrative chunk belongs to a different release")
        object.__setattr__(self, "chunks", ordered)

    @property
    def manifest_hash(self) -> str:
        return _hash(
            {
                "evidence_release_manifest_hash": self.evidence_release_manifest_hash,
                "chunks": [
                    {
                        "cik": chunk.cik,
                        "filing_accession": chunk.filing_accession,
                        "filed_at": chunk.filed_at.isoformat(),
                        "source_url": chunk.source_url,
                        "source_span": chunk.source_span,
                        "chunk_hash": chunk.chunk_hash,
                    }
                    for chunk in self.chunks
                ],
            }
        )

    def context(
        self,
        *,
        evidence_release_manifest_hash: str,
        cik: str,
        as_of_date: date | None = None,
        filing_accessions: tuple[str, ...] = (),
    ) -> tuple[NarrativeDisclosureChunk, ...]:
        if evidence_release_manifest_hash != self.evidence_release_manifest_hash:
            return ()
        normalized_cik = SecCompanyFactsClient.normalize_cik(cik)
        if as_of_date is not None and not isinstance(as_of_date, date):
            raise IndexedReleaseError("narrative context as-of date is invalid")
        if not isinstance(filing_accessions, tuple) or any(
            not isinstance(accession, str)
            or not _ACCESSION_PATTERN.fullmatch(accession)
            for accession in filing_accessions
        ):
            raise IndexedReleaseError("narrative context filing scope is invalid")
        if len(set(filing_accessions)) != len(filing_accessions):
            raise IndexedReleaseError("narrative context filing scope is invalid")
        requested = set(filing_accessions)
        return tuple(
            chunk
            for chunk in self.chunks
            if chunk.cik == normalized_cik
            and (as_of_date is None or chunk.filed_at <= as_of_date)
            and (not requested or chunk.filing_accession in requested)
        )


@dataclass(frozen=True, slots=True)
class IndexedSnapshot:
    request: IndexedSnapshotRequest
    build: SnapshotBuild

    def __post_init__(self) -> None:
        if self.build.audit_manifest.analysis_as_of_date != self.request.as_of_date:
            raise IndexedReleaseError("indexed snapshot date does not match its audit manifest")
        if self.build.audit_manifest.requested_forms != self.request.forms:
            raise IndexedReleaseError("indexed snapshot forms do not match its audit manifest")
        if any(item.entity_cik != self.request.cik for item in self.build.snapshot.evidence):
            raise IndexedReleaseError("indexed snapshot contains evidence for another issuer")

    def payload(self) -> dict[str, object]:
        return {
            "request": {
                "cik": self.request.cik,
                "as_of_date": self.request.as_of_date.isoformat(),
                "forms": self.request.forms,
                "acquisition_records": self.request.acquisition_records,
            },
            "snapshot_manifest_hash": self.build.snapshot.manifest_hash,
            "audit_manifest_hash": self.build.audit_manifest.manifest_hash,
        }


@dataclass(frozen=True, slots=True)
class IndexedEvidenceRelease:
    """One frozen release and its deterministic structured/context indexes."""

    evidence_release: EvidenceRelease
    snapshots: tuple[IndexedSnapshot, ...]
    exact_facts: ExactFactIndex
    narrative_context: NarrativeContextIndex

    def __post_init__(self) -> None:
        release_hash = self.evidence_release.manifest_hash
        if self.exact_facts.evidence_release_manifest_hash != release_hash:
            raise IndexedReleaseError("exact fact index does not match the evidence release")
        if self.narrative_context.evidence_release_manifest_hash != release_hash:
            raise IndexedReleaseError("narrative index does not match the evidence release")
        ordered = tuple(sorted(self.snapshots, key=lambda snapshot: snapshot.request.key()))
        if len({snapshot.request.key() for snapshot in ordered}) != len(ordered):
            raise IndexedReleaseError("indexed snapshot requests must be unique")
        if not ordered:
            raise IndexedReleaseError("an indexed release requires at least one snapshot")
        issuers = set(self.evidence_release.issuer_ciks)
        if any(snapshot.request.cik not in issuers for snapshot in ordered):
            raise IndexedReleaseError("indexed snapshot issuer is outside the evidence release")
        if any(chunk.cik not in issuers for chunk in self.narrative_context.chunks):
            raise IndexedReleaseError("narrative chunk issuer is outside the evidence release")
        evidence_ids = {
            evidence.evidence_id
            for snapshot in ordered
            for evidence in snapshot.build.snapshot.evidence
        }
        if {record.evidence.evidence_id for record in self.exact_facts.records} != evidence_ids:
            raise IndexedReleaseError("exact fact index does not cover the compiled snapshots")
        object.__setattr__(self, "snapshots", ordered)

    @property
    def manifest_hash(self) -> str:
        return _hash(
            {
                "evidence_release_manifest_hash": self.evidence_release.manifest_hash,
                "snapshots": [snapshot.payload() for snapshot in self.snapshots],
                "exact_fact_index_hash": self.exact_facts.manifest_hash,
                "narrative_context_index_hash": self.narrative_context.manifest_hash,
            }
        )

    def snapshot_for(self, *, request: IndexedSnapshotRequest) -> SnapshotBuild:
        for snapshot in self.snapshots:
            if snapshot.request == request:
                original = snapshot.build.snapshot
                evidence_ids = (
                    original.visible_evidence_ids
                    if original.visible_evidence_ids is not None
                    else tuple(item.evidence_id for item in original.evidence)
                )
                evidence = tuple(
                    self.exact_facts.evidence_by_id(evidence_id=evidence_id)
                    for evidence_id in evidence_ids
                )
                if any(item is None for item in evidence):
                    raise IndexedReleaseError(
                        "compiled exact fact index is missing snapshot evidence"
                    )
                rebuilt = EvidenceSnapshot.freeze(
                    snapshot_id=original.snapshot_id,
                    evidence=tuple(item for item in evidence if item is not None),
                    source_type=original.source_type,
                    visible_evidence_ids=original.visible_evidence_ids,
                )
                if rebuilt.manifest_hash != original.manifest_hash:
                    raise IndexedReleaseError(
                        "compiled exact fact index does not replay the snapshot manifest"
                    )
                return replace(snapshot.build, snapshot=rebuilt)
        raise IndexedReleaseError("request is not compiled into the declared release")


def compile_indexed_release(
    *,
    evidence_release: EvidenceRelease,
    snapshots: tuple[IndexedSnapshot, ...],
    narrative_chunks: tuple[NarrativeDisclosureChunk, ...] = (),
) -> IndexedEvidenceRelease:
    """Compile deterministic exact facts and context-only narrative indexes offline."""

    release_hash = evidence_release.manifest_hash
    fact_by_id: dict[str, ExactFactRecord] = {}
    for indexed_snapshot in snapshots:
        for evidence in indexed_snapshot.build.snapshot.evidence:
            record = ExactFactRecord.from_evidence(
                evidence_release_manifest_hash=release_hash,
                evidence=evidence,
            )
            existing = fact_by_id.get(record.fact_id)
            if existing is not None and existing.evidence != record.evidence:
                raise IndexedReleaseError("one exact fact key resolves to conflicting evidence")
            fact_by_id[record.fact_id] = record
    return IndexedEvidenceRelease(
        evidence_release=evidence_release,
        snapshots=snapshots,
        exact_facts=ExactFactIndex(
            evidence_release_manifest_hash=release_hash,
            records=tuple(fact_by_id.values()),
        ),
        narrative_context=NarrativeContextIndex(
            evidence_release_manifest_hash=release_hash,
            chunks=narrative_chunks,
        ),
    )


class IndexedSnapshotProvider:
    """Snapshot provider backed solely by a frozen compiled exact-fact release."""

    def __init__(self, *, indexed_release: IndexedEvidenceRelease) -> None:
        self._indexed_release = indexed_release

    def build(
        self,
        *,
        cik: str,
        as_of_date: date,
        forms: tuple[str, ...],
        acquisition_records: tuple[EvidenceAcquisitionRecord, ...] = (),
    ) -> SnapshotBuild:
        request = IndexedSnapshotRequest(
            cik=cik,
            as_of_date=as_of_date,
            forms=forms,
            acquisition_records=tuple(
                (record.request_type.value, record.reason)
                for record in acquisition_records
            ),
        )
        return self._indexed_release.snapshot_for(request=request)


class NarrativeContextRetriever:
    """Separate context-only adapter for a frozen narrative index."""

    def __init__(self, *, narrative_index: NarrativeContextIndex) -> None:
        self._narrative_index = narrative_index

    def context(
        self,
        *,
        evidence_release_manifest_hash: str,
        cik: str,
        as_of_date: date | None = None,
        filing_accessions: tuple[str, ...] = (),
    ) -> tuple[NarrativeDisclosureChunk, ...]:
        return self._narrative_index.context(
            evidence_release_manifest_hash=evidence_release_manifest_hash,
            cik=cik,
            as_of_date=as_of_date,
            filing_accessions=filing_accessions,
        )
