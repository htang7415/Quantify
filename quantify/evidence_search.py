"""Exact, provider-free search over one approved frozen evidence release.

The adapter in this module cannot retrieve live data, perform similarity
search, return narrative context, call a model, or compose a verdict. It turns
exact indexed facts into a versioned, replayable result and citation
authorizations suitable for ``research-answer.v1`` validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
import re
from urllib.parse import urlparse

from quantify.harness.sec.client import SecCompanyFactsClient
from quantify.indexed_release import ExactFactKey, IndexedEvidenceRelease
from quantify.research_answers import AuthorizedCitation
from quantify.research_intents import ResearchIntent


_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
_METRIC_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_UNIT_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_./-]{0,31}$")
_LIMITATION = (
    "Exact structured facts from the declared frozen release only; "
    "no narrative fallback, live retrieval, prediction, recommendation, or verdict."
)


class EvidenceSearchError(ValueError):
    """An exact search request or compiled result failed closed."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


EvidenceSearchTask = ResearchIntent


class EvidenceSearchStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


def _require_text(
    value: str, *, field: str, code: str = "invalid_request"
) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EvidenceSearchError(code, f"{field} is invalid")


def _require_hash(
    value: str, *, field: str, code: str = "invalid_request"
) -> None:
    if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value):
        raise EvidenceSearchError(
            code, f"{field} must be a lowercase SHA-256 hash"
        )


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_decimal(value: Decimal) -> str:
    """Render a finite Decimal without exponent or insignificant trailing zeroes."""

    if not isinstance(value, Decimal) or not value.is_finite():
        raise EvidenceSearchError("invalid_release_fact", "fact measurement is not finite")
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"-0", ""} else rendered


@dataclass(frozen=True, slots=True)
class ApprovedEvidenceQuery:
    query_id: str
    metric: str
    period_start: date
    period_end: date
    unit: str

    def __post_init__(self) -> None:
        if not isinstance(self.query_id, str) or not _ID_PATTERN.fullmatch(self.query_id):
            raise EvidenceSearchError("invalid_request", "query_id is invalid")
        if not isinstance(self.metric, str) or not _METRIC_PATTERN.fullmatch(self.metric):
            raise EvidenceSearchError("invalid_request", "metric is invalid")
        if (
            not isinstance(self.period_start, date)
            or not isinstance(self.period_end, date)
            or self.period_start > self.period_end
        ):
            raise EvidenceSearchError("invalid_request", "query period is invalid")
        if not isinstance(self.unit, str) or not _UNIT_PATTERN.fullmatch(self.unit):
            raise EvidenceSearchError("invalid_request", "unit is invalid")

    def to_document(self) -> dict[str, str]:
        return {
            "query_id": self.query_id,
            "metric": self.metric,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class ApprovedEvidenceSearchRequest:
    task_type: EvidenceSearchTask
    cik: str
    as_of: date
    release_id: str
    release_manifest_hash: str
    queries: tuple[ApprovedEvidenceQuery, ...]
    schema_version: str = "approved-evidence-search-request.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "approved-evidence-search-request.v1":
            raise EvidenceSearchError("invalid_request", "request schema version is invalid")
        if not isinstance(self.task_type, EvidenceSearchTask):
            raise EvidenceSearchError("invalid_request", "task_type is invalid")
        try:
            normalized_cik = SecCompanyFactsClient.normalize_cik(self.cik)
        except (TypeError, ValueError) as error:
            raise EvidenceSearchError("invalid_request", "company CIK is invalid") from error
        object.__setattr__(self, "cik", normalized_cik)
        if not isinstance(self.as_of, date):
            raise EvidenceSearchError("invalid_request", "as_of is invalid")
        _require_text(self.release_id, field="release_id")
        _require_hash(self.release_manifest_hash, field="release_manifest_hash")
        if (
            not isinstance(self.queries, tuple)
            or not 1 <= len(self.queries) <= 32
            or not all(isinstance(query, ApprovedEvidenceQuery) for query in self.queries)
        ):
            raise EvidenceSearchError("invalid_request", "queries must contain 1 to 32 exact queries")
        query_ids = [query.query_id for query in self.queries]
        if len(set(query_ids)) != len(query_ids):
            raise EvidenceSearchError("invalid_request", "query IDs must be unique")
        query_keys = [
            (query.metric, query.period_start, query.period_end, query.unit)
            for query in self.queries
        ]
        if len(set(query_keys)) != len(query_keys):
            raise EvidenceSearchError(
                "invalid_request", "exact query keys must be unique"
            )
        object.__setattr__(self, "queries", tuple(sorted(self.queries, key=lambda query: query.query_id)))

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
            "queries": [query.to_document() for query in self.queries],
        }

    @property
    def request_hash(self) -> str:
        return sha256(_canonical_json(self.to_document())).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovedEvidenceFact:
    query_id: str
    fact_id: str
    statement_text: str
    entity_cik: str
    metric: str
    value: Decimal
    unit: str
    period_start: date
    period_end: date
    filing_accession: str
    filed_at: date
    source_url: str
    evidence_id: str
    release_manifest_hash: str
    derived_from_evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.query_id, str) or not _ID_PATTERN.fullmatch(self.query_id):
            raise EvidenceSearchError("invalid_result", "fact query_id is invalid")
        if not isinstance(self.fact_id, str) or not _HASH_PATTERN.fullmatch(self.fact_id):
            raise EvidenceSearchError("invalid_result", "fact_id is invalid")
        _require_text(self.statement_text, field="statement_text", code="invalid_result")
        try:
            normalized_cik = SecCompanyFactsClient.normalize_cik(self.entity_cik)
        except (TypeError, ValueError) as error:
            raise EvidenceSearchError("invalid_result", "fact company CIK is invalid") from error
        if normalized_cik != self.entity_cik:
            raise EvidenceSearchError("invalid_result", "fact company CIK is not canonical")
        if not isinstance(self.metric, str) or not _METRIC_PATTERN.fullmatch(self.metric):
            raise EvidenceSearchError("invalid_result", "fact metric is invalid")
        canonical_decimal(self.value)
        if not isinstance(self.unit, str) or not _UNIT_PATTERN.fullmatch(self.unit):
            raise EvidenceSearchError("invalid_result", "fact unit is invalid")
        if (
            not isinstance(self.period_start, date)
            or not isinstance(self.period_end, date)
            or self.period_start > self.period_end
            or not isinstance(self.filed_at, date)
        ):
            raise EvidenceSearchError("invalid_result", "fact dates are invalid")
        _require_text(
            self.filing_accession, field="filing_accession", code="invalid_result"
        )
        parsed_url = urlparse(self.source_url) if isinstance(self.source_url, str) else None
        if (
            parsed_url is None
            or parsed_url.scheme != "https"
            or not parsed_url.netloc
            or parsed_url.username
            or parsed_url.password
        ):
            raise EvidenceSearchError("invalid_result", "fact source_url must be HTTPS")
        _require_text(self.evidence_id, field="evidence_id", code="invalid_result")
        _require_hash(
            self.release_manifest_hash,
            field="release_manifest_hash",
            code="invalid_result",
        )
        if not isinstance(self.derived_from_evidence_ids, tuple) or not all(
            isinstance(item, str) and item and item == item.strip()
            for item in self.derived_from_evidence_ids
        ):
            raise EvidenceSearchError(
                "invalid_result", "derived evidence IDs are invalid"
            )
        if len(set(self.derived_from_evidence_ids)) != len(self.derived_from_evidence_ids):
            raise EvidenceSearchError(
                "invalid_result", "derived evidence IDs must be unique"
            )
        object.__setattr__(
            self,
            "derived_from_evidence_ids",
            tuple(sorted(self.derived_from_evidence_ids)),
        )

    @property
    def statement_id(self) -> str:
        return f"fact-{self.fact_id}"

    @property
    def citation_id(self) -> str:
        return f"citation-{self.fact_id}"

    def to_document(self) -> dict[str, object]:
        return {
            "query_id": self.query_id,
            "fact_id": self.fact_id,
            "statement_id": self.statement_id,
            "statement_text": self.statement_text,
            "entity_cik": self.entity_cik,
            "metric": self.metric,
            "measurement": {"value": canonical_decimal(self.value), "unit": self.unit},
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "filing_accession": self.filing_accession,
            "filed_at": self.filed_at.isoformat(),
            "derived_from_evidence_ids": list(self.derived_from_evidence_ids),
            "citation": {
                "citation_id": self.citation_id,
                "source_type": "structured_fact",
                "verification_role": "verdict_evidence",
                "release_manifest_hash": self.release_manifest_hash,
                "source_record_id": self.filing_accession,
                "source_url": self.source_url,
                "evidence_id": self.evidence_id,
                "chunk_hash": None,
                "source_span": None,
            },
        }

    def authorization(self) -> AuthorizedCitation:
        return AuthorizedCitation(
            source_type="structured_fact",
            verification_role="verdict_evidence",
            release_manifest_hash=self.release_manifest_hash,
            source_record_id=self.filing_accession,
            source_url=self.source_url,
            statement_text=self.statement_text,
            evidence_id=self.evidence_id,
            measurement_value=self.value,
            measurement_unit=self.unit,
        )


@dataclass(frozen=True, slots=True)
class UnavailableEvidenceQuery:
    query_id: str
    reason: str = "exact_fact_not_found"
    detail: str = "No exact eligible structured fact matched the declared release key."

    def __post_init__(self) -> None:
        if not isinstance(self.query_id, str) or not _ID_PATTERN.fullmatch(self.query_id):
            raise EvidenceSearchError("invalid_result", "unavailable query_id is invalid")
        if self.reason != "exact_fact_not_found":
            raise EvidenceSearchError("invalid_result", "unavailable reason is invalid")
        _require_text(self.detail, field="unavailable detail", code="invalid_result")

    def to_document(self) -> dict[str, str]:
        return {"query_id": self.query_id, "reason": self.reason, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class ApprovedEvidenceSearchResult:
    request: ApprovedEvidenceSearchRequest
    facts: tuple[ApprovedEvidenceFact, ...]
    unavailable: tuple[UnavailableEvidenceQuery, ...]
    schema_version: str = "approved-evidence-search-result.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "approved-evidence-search-result.v1":
            raise EvidenceSearchError("invalid_result", "result schema version is invalid")
        if not isinstance(self.request, ApprovedEvidenceSearchRequest):
            raise EvidenceSearchError("invalid_result", "result request binding is invalid")
        if not isinstance(self.facts, tuple) or not all(
            isinstance(fact, ApprovedEvidenceFact) for fact in self.facts
        ):
            raise EvidenceSearchError("invalid_result", "facts are invalid")
        if not isinstance(self.unavailable, tuple) or not all(
            isinstance(item, UnavailableEvidenceQuery) for item in self.unavailable
        ):
            raise EvidenceSearchError("invalid_result", "unavailable queries are invalid")
        fact_ids = [fact.fact_id for fact in self.facts]
        if len(set(fact_ids)) != len(fact_ids):
            raise EvidenceSearchError("invalid_result", "fact IDs must be unique")
        resolved_query_ids = [fact.query_id for fact in self.facts]
        unavailable_query_ids = [item.query_id for item in self.unavailable]
        if len(set(resolved_query_ids)) != len(resolved_query_ids) or len(
            set(unavailable_query_ids)
        ) != len(unavailable_query_ids):
            raise EvidenceSearchError("invalid_result", "query outcomes must be unique")
        expected = {query.query_id for query in self.request.queries}
        actual = set(resolved_query_ids) | set(unavailable_query_ids)
        if actual != expected or set(resolved_query_ids) & set(unavailable_query_ids):
            raise EvidenceSearchError("invalid_result", "result does not cover each query exactly once")
        queries = {query.query_id: query for query in self.request.queries}
        for fact in self.facts:
            query = queries[fact.query_id]
            if (
                fact.entity_cik != self.request.cik
                or fact.metric != query.metric
                or fact.period_start != query.period_start
                or fact.period_end != query.period_end
                or fact.unit != query.unit
                or fact.release_manifest_hash != self.request.release_manifest_hash
                or fact.filed_at > self.request.as_of
            ):
                raise EvidenceSearchError(
                    "invalid_result", "fact does not match its request and release binding"
                )
        object.__setattr__(self, "facts", tuple(sorted(self.facts, key=lambda fact: fact.query_id)))
        object.__setattr__(
            self,
            "unavailable",
            tuple(sorted(self.unavailable, key=lambda item: item.query_id)),
        )

    @property
    def status(self) -> EvidenceSearchStatus:
        if self.facts and not self.unavailable:
            return EvidenceSearchStatus.COMPLETED
        if self.facts:
            return EvidenceSearchStatus.PARTIAL
        return EvidenceSearchStatus.UNAVAILABLE

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_hash": self.request.request_hash,
            "status": self.status.value,
            "release": {
                "release_id": self.request.release_id,
                "manifest_hash": self.request.release_manifest_hash,
            },
            "facts": [fact.to_document() for fact in self.facts],
            "unavailable": [item.to_document() for item in self.unavailable],
            "limitation": _LIMITATION,
        }

    @property
    def result_hash(self) -> str:
        return sha256(_canonical_json(self.to_document())).hexdigest()

    def authorized_citations(self) -> tuple[AuthorizedCitation, ...]:
        return tuple(fact.authorization() for fact in self.facts)


class FrozenReleaseEvidenceSearch:
    """Perform exact structured lookups against one already-compiled release."""

    def __init__(self, *, release: IndexedEvidenceRelease) -> None:
        self._release = release

    def search(self, request: ApprovedEvidenceSearchRequest) -> ApprovedEvidenceSearchResult:
        release = self._release.evidence_release
        if (
            request.release_id != release.release_id
            or request.release_manifest_hash != release.manifest_hash
        ):
            raise EvidenceSearchError("release_mismatch", "request release is not the loaded release")
        if request.cik not in release.issuer_ciks:
            raise EvidenceSearchError("entity_out_of_scope", "company is outside the loaded release")
        if not any(
            snapshot.request.cik == request.cik
            and snapshot.request.as_of_date == request.as_of
            for snapshot in self._release.snapshots
        ):
            raise EvidenceSearchError("as_of_not_compiled", "entity and as-of date are not compiled")

        facts: list[ApprovedEvidenceFact] = []
        unavailable: list[UnavailableEvidenceQuery] = []
        for query in request.queries:
            key = ExactFactKey(
                evidence_release_manifest_hash=request.release_manifest_hash,
                cik=request.cik,
                metric=query.metric,
                fiscal_period_start=query.period_start,
                fiscal_period_end=query.period_end,
                unit=query.unit,
            )
            record = self._release.exact_facts.lookup(key=key)
            if record is None:
                unavailable.append(UnavailableEvidenceQuery(query_id=query.query_id))
                continue
            evidence = record.evidence
            if (
                not evidence.eligible
                or not evidence.is_standard_tag
                or evidence.entity_cik != request.cik
                or evidence.filed_at > request.as_of
            ):
                raise EvidenceSearchError(
                    "invalid_release_fact",
                    "matched indexed fact is not eligible in the admitted scope",
                )
            value = canonical_decimal(evidence.value)
            statement_text = (
                f"CIK {evidence.entity_cik} reported {evidence.metric} of {value} "
                f"{evidence.unit} for {evidence.period_start.isoformat()} through "
                f"{evidence.period_end.isoformat()} in filing {evidence.accession}, "
                f"filed {evidence.filed_at.isoformat()}."
            )
            facts.append(
                ApprovedEvidenceFact(
                    query_id=query.query_id,
                    fact_id=record.fact_id,
                    statement_text=statement_text,
                    entity_cik=evidence.entity_cik,
                    metric=evidence.metric,
                    value=evidence.value,
                    unit=evidence.unit,
                    period_start=evidence.period_start,
                    period_end=evidence.period_end,
                    filing_accession=evidence.accession,
                    filed_at=evidence.filed_at,
                    source_url=evidence.source_url,
                    evidence_id=evidence.evidence_id,
                    release_manifest_hash=request.release_manifest_hash,
                    derived_from_evidence_ids=evidence.derived_from_evidence_ids,
                )
            )
        return ApprovedEvidenceSearchResult(
            request=request,
            facts=tuple(facts),
            unavailable=tuple(unavailable),
        )
