"""Release-scoped, provider-free narrative context retrieval.

This adapter can return only already-compiled issuer disclosure chunks. Its
outputs are context-only citation authorizations for ``research-answer.v1``;
they can never become structured facts, measurements, or verdict evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from hashlib import sha256
import json
import re
from urllib.parse import urlparse

from quantify.harness.sec.client import SecCompanyFactsClient
from quantify.indexed_release import (
    IndexedEvidenceRelease,
    IndexedReleaseError,
    NarrativeContextRetriever,
    NarrativeDisclosureChunk,
)
from quantify.research_answers import AuthorizedCitation
from quantify.research_intents import ResearchIntent


_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ACCESSION_PATTERN = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_LIMITATION = (
    "Release-scoped issuer disclosure context only; never fact or verdict evidence; "
    "no live retrieval, similarity expansion, licensed news, prediction, "
    "recommendation, or verdict."
)


class NarrativeContextError(ValueError):
    """A narrative-context request or result failed closed."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


NarrativeContextTask = ResearchIntent


class NarrativeContextStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _require_text(value: str, *, field: str, code: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise NarrativeContextError(code, f"{field} is invalid")


def _require_hash(value: str, *, field: str, code: str) -> None:
    if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value):
        raise NarrativeContextError(code, f"{field} must be a lowercase SHA-256 hash")


def _require_accession(value: str, *, field: str, code: str) -> None:
    if not isinstance(value, str) or not _ACCESSION_PATTERN.fullmatch(value):
        raise NarrativeContextError(code, f"{field} is invalid")


def _require_https_url(value: str, *, field: str, code: str) -> None:
    parsed = urlparse(value) if isinstance(value, str) else None
    if (
        parsed is None
        or parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise NarrativeContextError(code, f"{field} must be HTTPS")


@dataclass(frozen=True, slots=True)
class ApprovedNarrativeContextRequest:
    task_type: NarrativeContextTask
    cik: str
    as_of: date
    release_id: str
    release_manifest_hash: str
    filing_accessions: tuple[str, ...] = ()
    maximum_chunks: int = 8
    schema_version: str = "approved-narrative-context-request.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "approved-narrative-context-request.v1":
            raise NarrativeContextError("invalid_request", "request schema version is invalid")
        if not isinstance(self.task_type, NarrativeContextTask):
            raise NarrativeContextError("invalid_request", "task_type is invalid")
        try:
            normalized_cik = SecCompanyFactsClient.normalize_cik(self.cik)
        except (TypeError, ValueError) as error:
            raise NarrativeContextError("invalid_request", "company CIK is invalid") from error
        object.__setattr__(self, "cik", normalized_cik)
        if not isinstance(self.as_of, date):
            raise NarrativeContextError("invalid_request", "as_of is invalid")
        _require_text(self.release_id, field="release_id", code="invalid_request")
        _require_hash(
            self.release_manifest_hash,
            field="release_manifest_hash",
            code="invalid_request",
        )
        if (
            not isinstance(self.filing_accessions, tuple)
            or len(self.filing_accessions) > 16
        ):
            raise NarrativeContextError(
                "invalid_request", "filing_accessions must contain at most 16 values"
            )
        for accession in self.filing_accessions:
            _require_accession(accession, field="filing_accession", code="invalid_request")
        if len(set(self.filing_accessions)) != len(self.filing_accessions):
            raise NarrativeContextError(
                "invalid_request", "filing_accessions must contain unique values"
            )
        if (
            not isinstance(self.maximum_chunks, int)
            or isinstance(self.maximum_chunks, bool)
            or not 1 <= self.maximum_chunks <= 16
        ):
            raise NarrativeContextError(
                "invalid_request", "maximum_chunks must be between 1 and 16"
            )
        object.__setattr__(self, "filing_accessions", tuple(sorted(self.filing_accessions)))

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "task_type": self.task_type.value,
            "entity": {"entity_type": "company", "cik": self.cik},
            "as_of": self.as_of.isoformat(),
            "release": {
                "release_id": self.release_id,
                "manifest_hash": self.release_manifest_hash,
            },
            "filing_accessions": list(self.filing_accessions),
            "maximum_chunks": self.maximum_chunks,
        }

    @property
    def request_hash(self) -> str:
        return sha256(_canonical_json(self.to_document())).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovedNarrativeContext:
    chunk_hash: str
    statement_text: str
    entity_cik: str
    filing_accession: str
    filed_at: date
    source_url: str
    source_span: tuple[int, int]
    release_manifest_hash: str

    def __post_init__(self) -> None:
        _require_hash(self.chunk_hash, field="chunk_hash", code="invalid_result")
        _require_text(self.statement_text, field="statement_text", code="invalid_result")
        if len(self.statement_text) > 12_000:
            raise NarrativeContextError("invalid_result", "statement_text is too long")
        try:
            normalized_cik = SecCompanyFactsClient.normalize_cik(self.entity_cik)
        except (TypeError, ValueError) as error:
            raise NarrativeContextError("invalid_result", "context company CIK is invalid") from error
        if normalized_cik != self.entity_cik:
            raise NarrativeContextError("invalid_result", "context company CIK is not canonical")
        _require_accession(
            self.filing_accession,
            field="filing_accession",
            code="invalid_result",
        )
        if not isinstance(self.filed_at, date):
            raise NarrativeContextError("invalid_result", "context filing date is invalid")
        _require_https_url(self.source_url, field="source_url", code="invalid_result")
        if (
            not isinstance(self.source_span, tuple)
            or len(self.source_span) != 2
            or any(
                not isinstance(item, int) or isinstance(item, bool)
                for item in self.source_span
            )
            or self.source_span[0] < 0
            or self.source_span[0] >= self.source_span[1]
            or self.source_span[1] - self.source_span[0] != len(self.statement_text)
        ):
            raise NarrativeContextError("invalid_result", "context source span is invalid")
        _require_hash(
            self.release_manifest_hash,
            field="release_manifest_hash",
            code="invalid_result",
        )
        try:
            NarrativeDisclosureChunk(
                evidence_release_manifest_hash=self.release_manifest_hash,
                cik=self.entity_cik,
                filing_accession=self.filing_accession,
                filed_at=self.filed_at,
                source_url=self.source_url,
                source_span=self.source_span,
                text=self.statement_text,
                chunk_hash=self.chunk_hash,
            )
        except IndexedReleaseError as error:
            raise NarrativeContextError(
                "invalid_result", "context does not replay its compiled chunk hash"
            ) from error

    @property
    def context_id(self) -> str:
        return f"context-{self.chunk_hash}"

    @property
    def statement_id(self) -> str:
        return self.context_id

    @property
    def citation_id(self) -> str:
        return f"citation-context-{self.chunk_hash}"

    def to_document(self) -> dict[str, object]:
        return {
            "context_id": self.context_id,
            "statement_id": self.statement_id,
            "kind": "narrative_context",
            "statement_text": self.statement_text,
            "entity_cik": self.entity_cik,
            "filing_accession": self.filing_accession,
            "filed_at": self.filed_at.isoformat(),
            "citation": {
                "citation_id": self.citation_id,
                "source_type": "narrative_disclosure",
                "verification_role": "context_only",
                "release_manifest_hash": self.release_manifest_hash,
                "source_record_id": self.filing_accession,
                "source_url": self.source_url,
                "evidence_id": None,
                "chunk_hash": self.chunk_hash,
                "source_span": {
                    "start_char": self.source_span[0],
                    "end_char": self.source_span[1],
                },
            },
        }

    def authorization(self) -> AuthorizedCitation:
        return AuthorizedCitation(
            source_type="narrative_disclosure",
            verification_role="context_only",
            release_manifest_hash=self.release_manifest_hash,
            source_record_id=self.filing_accession,
            source_url=self.source_url,
            statement_text=self.statement_text,
            chunk_hash=self.chunk_hash,
            source_span=self.source_span,
        )


@dataclass(frozen=True, slots=True)
class UnavailableNarrativeContext:
    request: str
    reason: str
    detail: str

    def __post_init__(self) -> None:
        _require_text(self.request, field="unavailable request", code="invalid_result")
        if self.reason not in {
            "narrative_context_not_released",
            "filing_context_not_released",
        }:
            raise NarrativeContextError("invalid_result", "unavailable reason is invalid")
        _require_text(self.detail, field="unavailable detail", code="invalid_result")

    def to_document(self) -> dict[str, str]:
        return {"request": self.request, "reason": self.reason, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class ApprovedNarrativeContextResult:
    request: ApprovedNarrativeContextRequest
    contexts: tuple[ApprovedNarrativeContext, ...]
    unavailable: tuple[UnavailableNarrativeContext, ...]
    omitted_chunk_count: int = 0
    schema_version: str = "approved-narrative-context-result.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "approved-narrative-context-result.v1":
            raise NarrativeContextError("invalid_result", "result schema version is invalid")
        if not isinstance(self.request, ApprovedNarrativeContextRequest):
            raise NarrativeContextError("invalid_result", "result request binding is invalid")
        if not isinstance(self.contexts, tuple) or not all(
            isinstance(item, ApprovedNarrativeContext) for item in self.contexts
        ):
            raise NarrativeContextError("invalid_result", "contexts are invalid")
        if not isinstance(self.unavailable, tuple) or not all(
            isinstance(item, UnavailableNarrativeContext) for item in self.unavailable
        ):
            raise NarrativeContextError("invalid_result", "unavailable context is invalid")
        if (
            not isinstance(self.omitted_chunk_count, int)
            or isinstance(self.omitted_chunk_count, bool)
            or self.omitted_chunk_count < 0
            or (self.omitted_chunk_count and len(self.contexts) != self.request.maximum_chunks)
        ):
            raise NarrativeContextError("invalid_result", "omitted chunk count is invalid")
        if len(self.contexts) > self.request.maximum_chunks:
            raise NarrativeContextError("invalid_result", "context result exceeds its request cap")
        chunk_hashes = [item.chunk_hash for item in self.contexts]
        if len(set(chunk_hashes)) != len(chunk_hashes):
            raise NarrativeContextError("invalid_result", "context chunks must be unique")
        unavailable_requests = [item.request for item in self.unavailable]
        if len(set(unavailable_requests)) != len(unavailable_requests):
            raise NarrativeContextError("invalid_result", "unavailable requests must be unique")
        requested_accessions = set(self.request.filing_accessions)
        returned_accessions = {item.filing_accession for item in self.contexts}
        for item in self.contexts:
            if (
                item.entity_cik != self.request.cik
                or item.release_manifest_hash != self.request.release_manifest_hash
                or item.filed_at > self.request.as_of
                or (
                    requested_accessions
                    and item.filing_accession not in requested_accessions
                )
            ):
                raise NarrativeContextError(
                    "invalid_result", "context does not match its request and release binding"
                )
        if requested_accessions:
            if any(
                item.request not in requested_accessions
                or item.reason != "filing_context_not_released"
                or item.request in returned_accessions
                for item in self.unavailable
            ):
                raise NarrativeContextError(
                    "invalid_result", "unavailable filing context does not match the request"
                )
            unresolved = requested_accessions - returned_accessions - set(unavailable_requests)
            if unresolved and not self.omitted_chunk_count:
                raise NarrativeContextError(
                    "invalid_result", "result does not cover each requested filing"
                )
        elif self.unavailable and (
            len(self.unavailable) != 1
            or self.unavailable[0].request != f"company:{self.request.cik}"
            or self.unavailable[0].reason != "narrative_context_not_released"
            or self.contexts
        ):
            raise NarrativeContextError(
                "invalid_result", "issuer-level unavailable context is invalid"
            )
        if not self.contexts and not self.unavailable:
            raise NarrativeContextError("invalid_result", "result has no context outcome")
        object.__setattr__(
            self,
            "contexts",
            tuple(sorted(self.contexts, key=lambda item: item.chunk_hash)),
        )
        object.__setattr__(
            self,
            "unavailable",
            tuple(sorted(self.unavailable, key=lambda item: item.request)),
        )

    @property
    def status(self) -> NarrativeContextStatus:
        if self.contexts and not self.unavailable and not self.omitted_chunk_count:
            return NarrativeContextStatus.COMPLETED
        if self.contexts:
            return NarrativeContextStatus.PARTIAL
        return NarrativeContextStatus.UNAVAILABLE

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_hash": self.request.request_hash,
            "status": self.status.value,
            "release": {
                "release_id": self.request.release_id,
                "manifest_hash": self.request.release_manifest_hash,
            },
            "contexts": [item.to_document() for item in self.contexts],
            "unavailable": [item.to_document() for item in self.unavailable],
            "omitted_chunk_count": self.omitted_chunk_count,
            "limitation": _LIMITATION,
        }

    @property
    def result_hash(self) -> str:
        return sha256(_canonical_json(self.to_document())).hexdigest()

    def authorized_citations(self) -> tuple[AuthorizedCitation, ...]:
        return tuple(item.authorization() for item in self.contexts)


class FrozenReleaseNarrativeContext:
    """Retrieve bounded disclosure context from one already-compiled release."""

    def __init__(self, *, release: IndexedEvidenceRelease) -> None:
        self._release = release

    def retrieve(
        self, request: ApprovedNarrativeContextRequest
    ) -> ApprovedNarrativeContextResult:
        release = self._release.evidence_release
        if (
            request.release_id != release.release_id
            or request.release_manifest_hash != release.manifest_hash
        ):
            raise NarrativeContextError(
                "release_mismatch", "request release is not the loaded release"
            )
        if request.cik not in release.issuer_ciks:
            raise NarrativeContextError(
                "entity_out_of_scope", "company is outside the loaded release"
            )
        if not any(
            snapshot.request.cik == request.cik
            and snapshot.request.as_of_date == request.as_of
            for snapshot in self._release.snapshots
        ):
            raise NarrativeContextError(
                "as_of_not_compiled", "entity and as-of date are not compiled"
            )

        eligible = NarrativeContextRetriever(
            narrative_index=self._release.narrative_context
        ).context(
            evidence_release_manifest_hash=request.release_manifest_hash,
            cik=request.cik,
            as_of_date=request.as_of,
            filing_accessions=request.filing_accessions,
        )
        selected = eligible[: request.maximum_chunks]
        contexts = tuple(
            ApprovedNarrativeContext(
                chunk_hash=chunk.chunk_hash,
                statement_text=chunk.text,
                entity_cik=chunk.cik,
                filing_accession=chunk.filing_accession,
                filed_at=chunk.filed_at,
                source_url=chunk.source_url,
                source_span=chunk.source_span,
                release_manifest_hash=chunk.evidence_release_manifest_hash,
            )
            for chunk in selected
        )
        available_accessions = {chunk.filing_accession for chunk in eligible}
        unavailable = tuple(
            UnavailableNarrativeContext(
                request=accession,
                reason="filing_context_not_released",
                detail=(
                    "No approved narrative context matched this filing accession "
                    "within the declared release and as-of scope."
                ),
            )
            for accession in request.filing_accessions
            if accession not in available_accessions
        )
        if not request.filing_accessions and not eligible:
            unavailable = (
                UnavailableNarrativeContext(
                    request=f"company:{request.cik}",
                    reason="narrative_context_not_released",
                    detail=(
                        "No approved narrative context is available for this company "
                        "within the declared release and as-of scope."
                    ),
                ),
            )
        return ApprovedNarrativeContextResult(
            request=request,
            contexts=contexts,
            unavailable=unavailable,
            omitted_chunk_count=len(eligible) - len(selected),
        )
