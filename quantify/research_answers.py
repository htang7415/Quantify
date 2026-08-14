"""Fail-closed validation for grounded ``research-answer.v1`` documents.

This module has no provider, retrieval, persistence, or publication capability.
It validates one proposed document only against an independently supplied,
immutable admission context and returns a detached canonical snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from hashlib import sha256
import json
import re
from typing import Mapping
from urllib.parse import urlparse

from quantify.research_intents import ResearchIntent


_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_CATALOGS = frozenset(
    {
        "investors",
        "venture",
        "markets",
        "macro",
        "rates",
        "etf_flows",
        "etf_holdings",
        "crypto",
        "crypto_exposure",
        "earnings",
        "policy",
        "events",
    }
)
_ENTITY_TYPES = frozenset(
    {"company", "investor", "fund", "security", "policy_authority", "market"}
)
_TASK_TYPES = frozenset(
    intent.value for intent in ResearchIntent if intent is not ResearchIntent.VERIFY
)
_STATUSES = frozenset({"completed", "requires_review", "unavailable"})
_STATEMENT_KINDS = frozenset(
    {
        "released_fact",
        "deterministic_calculation",
        "agent_interpretation",
        "narrative_context",
        "open_question",
    }
)
_SOURCE_TYPES = frozenset({"structured_fact", "narrative_disclosure", "licensed_news"})
_VERIFICATION_ROLES = frozenset({"verdict_evidence", "context_only"})
_OPERATIONS = frozenset({"sum", "difference", "percent_change", "percentage_point_change"})
_UNAVAILABLE_REASONS = frozenset(
    {"not_released", "out_of_scope", "not_entitled", "stale", "revoked", "unavailable"}
)
_VERDICTS = frozenset(
    {"verified", "unsupported", "defeated", "qualified", "requires_agent_resolution"}
)
_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "task_type",
        "status",
        "as_of",
        "entities",
        "release_scope",
        "answer",
        "answer_statement_ids",
        "statements",
        "citations",
        "counterpoint_statement_ids",
        "unavailable",
        "limitations",
        "model_contract",
        "verification_results",
        "audit_manifest_hash",
    }
)
_PROHIBITED_TEXT_PATTERNS = (
    re.compile(r"(?:^|[.!?]\s+)(?:buy|sell|hold|short)\s+(?!side\b)", re.IGNORECASE),
    re.compile(
        r"\b(?:you|investors?|clients?)\s+should\s+"
        r"(?:buy|sell|hold|short|invest|allocate)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:we|quantify)\s+(?:recommend|recommends)\b.{0,40}"
        r"\b(?:buy|sell|hold|short|invest|allocate)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bis\s+(?:an?\s+)?(?:buy|sell|hold)\b", re.IGNORECASE),
    re.compile(r"\bprice\s+target\s*(?:is|of|:)\s*\$?\d", re.IGNORECASE),
    re.compile(r"\ballocat(?:e|ion)\s+\d+(?:\.\d+)?\s*%", re.IGNORECASE),
    re.compile(
        r"\bposition\s+siz(?:e|ing)\s*(?:of|at|:)?\s*\d+(?:\.\d+)?\s*%",
        re.IGNORECASE,
    ),
)


def has_prohibited_investment_output(value: str) -> bool:
    """Return whether visible text contains prohibited advisory output."""

    return isinstance(value, str) and any(
        pattern.search(value) for pattern in _PROHIBITED_TEXT_PATTERNS
    )


class ResearchAnswerValidationError(ValueError):
    """A proposed research answer or its independent context failed closed."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code} at {path}: {detail}")


def _fail(code: str, path: str, detail: str) -> None:
    raise ResearchAnswerValidationError(code, path, detail)


def _context(condition: bool, path: str, detail: str) -> None:
    if not condition:
        _fail("invalid_context", path, detail)


def _decimal(value: object, *, path: str, code: str = "invalid_value") -> Decimal:
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value):
        _fail(code, path, "must be a canonical finite decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise ResearchAnswerValidationError(
            code, path, "must be a canonical finite decimal string"
        ) from error


def _valid_datetime(value: object, *, path: str, code: str = "invalid_value") -> datetime:
    if not isinstance(value, str) or "T" not in value:
        _fail(code, path, "must be an ISO 8601 date-time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ResearchAnswerValidationError(code, path, "must be an ISO 8601 date-time") from error
    if parsed.tzinfo is None:
        _fail(code, path, "must include a UTC offset")
    return parsed


def _valid_hash(value: object, *, path: str, code: str = "invalid_value") -> str:
    if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value):
        _fail(code, path, "must be a lowercase SHA-256 hash")
    return value


def _valid_id(value: object, *, path: str, code: str = "invalid_value") -> str:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        _fail(code, path, "must be a non-empty contract identifier")
    return value


def _valid_text(value: object, *, path: str, code: str = "invalid_value") -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\x00" in value
    ):
        _fail(code, path, "must be non-empty, trimmed text")
    return value


def _valid_enum(
    value: object,
    allowed: frozenset[str],
    *,
    path: str,
    code: str = "invalid_value",
) -> str:
    if not isinstance(value, str) or value not in allowed:
        _fail(code, path, "value is outside the versioned enum")
    return value


def _valid_url(value: object, *, path: str, code: str = "invalid_value") -> str:
    if not isinstance(value, str):
        _fail(code, path, "must be an HTTPS URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        _fail(code, path, "must be an HTTPS URL without credentials")
    return value


def _exact_mapping(value: object, fields: frozenset[str], *, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        _fail("invalid_shape", path, "object fields do not match the versioned contract")
    return value


def _list(value: object, *, path: str, minimum: int = 0) -> list[object]:
    if not isinstance(value, list) or len(value) < minimum:
        _fail("invalid_shape", path, f"must be an array with at least {minimum} item(s)")
    return value


def _string_list(
    value: object,
    *,
    path: str,
    minimum: int = 0,
    identifiers: bool = False,
) -> tuple[str, ...]:
    values = _list(value, path=path, minimum=minimum)
    parsed = tuple(
        _valid_id(item, path=f"{path}[{index}]")
        if identifiers
        else _valid_text(item, path=f"{path}[{index}]")
        for index, item in enumerate(values)
    )
    if len(set(parsed)) != len(parsed):
        _fail("duplicate_identifier", path, "array items must be unique")
    return parsed


@dataclass(frozen=True, slots=True)
class EntityBinding:
    entity_id: str
    entity_type: str
    display_name: str

    def __post_init__(self) -> None:
        _context(
            isinstance(self.entity_id, str)
            and bool(self.entity_id)
            and self.entity_id == self.entity_id.strip(),
            "context.entities.entity_id",
            "entity ID is required",
        )
        _valid_enum(self.entity_type, _ENTITY_TYPES, path="context.entities.entity_type", code="invalid_context")
        _context(
            isinstance(self.display_name, str)
            and bool(self.display_name)
            and self.display_name == self.display_name.strip(),
            "context.entities.display_name",
            "display name is invalid",
        )


@dataclass(frozen=True, slots=True)
class ReleaseBinding:
    catalog: str
    release_id: str
    manifest_hash: str

    def __post_init__(self) -> None:
        _valid_enum(self.catalog, _CATALOGS, path="context.release_bindings.catalog", code="invalid_context")
        _context(
            isinstance(self.release_id, str)
            and bool(self.release_id)
            and self.release_id == self.release_id.strip(),
            "context.release_bindings.release_id",
            "release ID is required",
        )
        _valid_hash(self.manifest_hash, path="context.release_bindings.manifest_hash", code="invalid_context")


@dataclass(frozen=True, slots=True)
class AuthorizedCitation:
    source_type: str
    verification_role: str
    release_manifest_hash: str
    source_record_id: str
    source_url: str
    statement_text: str
    evidence_id: str | None = None
    chunk_hash: str | None = None
    source_span: tuple[int, int] | None = None
    measurement_value: Decimal | None = None
    measurement_unit: str | None = None

    def __post_init__(self) -> None:
        _valid_enum(self.source_type, _SOURCE_TYPES, path="context.citations.source_type", code="invalid_context")
        _valid_enum(
            self.verification_role,
            _VERIFICATION_ROLES,
            path="context.citations.verification_role",
            code="invalid_context",
        )
        _valid_hash(self.release_manifest_hash, path="context.citations.release_manifest_hash", code="invalid_context")
        _context(
            isinstance(self.source_record_id, str)
            and bool(self.source_record_id)
            and self.source_record_id == self.source_record_id.strip(),
            "context.citations.source_record_id",
            "source record ID is required",
        )
        _valid_url(self.source_url, path="context.citations.source_url", code="invalid_context")
        _valid_text(self.statement_text, path="context.citations.statement_text", code="invalid_context")
        paired_measurement = self.measurement_value is None and self.measurement_unit is None
        paired_measurement = paired_measurement or (
            self.measurement_value is not None
            and isinstance(self.measurement_value, Decimal)
            and self.measurement_value.is_finite()
            and isinstance(self.measurement_unit, str)
            and bool(self.measurement_unit)
            and self.measurement_unit == self.measurement_unit.strip()
        )
        _context(paired_measurement, "context.citations.measurement", "measurement is incomplete")
        if self.source_type == "structured_fact":
            _context(self.verification_role == "verdict_evidence", "context.citations", "structured fact role is invalid")
            _context(
                isinstance(self.evidence_id, str)
                and bool(self.evidence_id)
                and self.evidence_id == self.evidence_id.strip(),
                "context.citations.evidence_id",
                "evidence ID is required",
            )
            _context(self.chunk_hash is None and self.source_span is None, "context.citations", "structured fact context fields are invalid")
        else:
            _context(self.verification_role == "context_only", "context.citations", "narrative role is invalid")
            _context(self.evidence_id is None, "context.citations.evidence_id", "context cannot carry an evidence ID")
            _valid_hash(self.chunk_hash, path="context.citations.chunk_hash", code="invalid_context")
            _context(
                isinstance(self.source_span, tuple)
                and len(self.source_span) == 2
                and all(isinstance(item, int) and not isinstance(item, bool) for item in self.source_span)
                and 0 <= self.source_span[0] < self.source_span[1],
                "context.citations.source_span",
                "source span is invalid",
            )
            _context(
                self.measurement_value is None and self.measurement_unit is None,
                "context.citations.measurement",
                "context cannot authorize a measurement",
            )

    @property
    def document_key(self) -> tuple[object, ...]:
        return (
            self.source_type,
            self.verification_role,
            self.release_manifest_hash,
            self.source_record_id,
            self.source_url,
            self.evidence_id,
            self.chunk_hash,
            self.source_span,
        )


@dataclass(frozen=True, slots=True)
class ModelContract:
    provider: str
    model_id: str
    prompt_contract_hash: str
    tool_contract_hash: str
    provider_attempt_id: str

    def __post_init__(self) -> None:
        for name in ("provider", "model_id", "provider_attempt_id"):
            value = getattr(self, name)
            _context(
                isinstance(value, str) and bool(value) and value == value.strip(),
                f"context.model_contract.{name}",
                f"{name} is required",
            )
        _valid_hash(self.prompt_contract_hash, path="context.model_contract.prompt_contract_hash", code="invalid_context")
        _valid_hash(self.tool_contract_hash, path="context.model_contract.tool_contract_hash", code="invalid_context")

    def as_tuple(self) -> tuple[str, ...]:
        return (
            self.provider,
            self.model_id,
            self.prompt_contract_hash,
            self.tool_contract_hash,
            self.provider_attempt_id,
        )


@dataclass(frozen=True, slots=True)
class InterpretationWarrant:
    statement_id: str
    text: str
    derived_from_statement_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _valid_id(self.statement_id, path="context.interpretation_warrants.statement_id", code="invalid_context")
        _valid_text(self.text, path="context.interpretation_warrants.text", code="invalid_context")
        _context(
            isinstance(self.derived_from_statement_ids, tuple)
            and bool(self.derived_from_statement_ids),
            "context.interpretation_warrants",
            "derivation must be a non-empty immutable tuple",
        )
        for statement_id in self.derived_from_statement_ids:
            _valid_id(statement_id, path="context.interpretation_warrants.derived_from", code="invalid_context")
        _context(
            len(set(self.derived_from_statement_ids)) == len(self.derived_from_statement_ids),
            "context.interpretation_warrants.derived_from",
            "derivation IDs must be unique",
        )

    def as_tuple(self) -> tuple[object, ...]:
        return (self.statement_id, self.text, self.derived_from_statement_ids)


@dataclass(frozen=True, slots=True)
class VerificationResultBinding:
    claim_id: str
    verdict: str
    evidence_scope_manifest_hash: str
    audit_manifest_hash: str

    def __post_init__(self) -> None:
        _context(
            isinstance(self.claim_id, str)
            and bool(self.claim_id)
            and self.claim_id == self.claim_id.strip(),
            "context.verification_results.claim_id",
            "claim ID is required",
        )
        _valid_enum(self.verdict, _VERDICTS, path="context.verification_results.verdict", code="invalid_context")
        _valid_hash(
            self.evidence_scope_manifest_hash,
            path="context.verification_results.evidence_scope_manifest_hash",
            code="invalid_context",
        )
        _valid_hash(
            self.audit_manifest_hash,
            path="context.verification_results.audit_manifest_hash",
            code="invalid_context",
        )

    def as_tuple(self) -> tuple[str, ...]:
        return (
            self.claim_id,
            self.verdict,
            "deterministic_verifier",
            self.evidence_scope_manifest_hash,
            self.audit_manifest_hash,
        )


@dataclass(frozen=True, slots=True)
class ResearchAnswerValidationContext:
    task_type: str
    entities: tuple[EntityBinding, ...]
    as_of: str
    release_bindings: tuple[ReleaseBinding, ...]
    observed_through: str
    authorized_citations: tuple[AuthorizedCitation, ...]
    audit_manifest_hash: str
    model_contract: ModelContract | None = None
    interpretation_warrants: tuple[InterpretationWarrant, ...] = ()
    verification_results: tuple[VerificationResultBinding, ...] = ()

    def __post_init__(self) -> None:
        _valid_enum(self.task_type, _TASK_TYPES, path="context.task_type", code="invalid_context")
        _context(
            isinstance(self.entities, tuple)
            and bool(self.entities)
            and all(isinstance(entity, EntityBinding) for entity in self.entities),
            "context.entities",
            "entities must be a non-empty immutable tuple of bindings",
        )
        _context(
            len({(entity.entity_type, entity.entity_id) for entity in self.entities}) == len(self.entities),
            "context.entities",
            "entities must be unique",
        )
        _valid_datetime(self.as_of, path="context.as_of", code="invalid_context")
        _context(
            isinstance(self.release_bindings, tuple)
            and bool(self.release_bindings)
            and all(isinstance(binding, ReleaseBinding) for binding in self.release_bindings),
            "context.release_bindings",
            "releases must be a non-empty immutable tuple of bindings",
        )
        _context(
            len({binding.release_id for binding in self.release_bindings}) == len(self.release_bindings),
            "context.release_bindings",
            "release IDs must be unique",
        )
        _context(
            len({binding.manifest_hash for binding in self.release_bindings}) == len(self.release_bindings),
            "context.release_bindings",
            "release hashes must be unique",
        )
        _valid_datetime(self.observed_through, path="context.observed_through", code="invalid_context")
        _valid_hash(self.audit_manifest_hash, path="context.audit_manifest_hash", code="invalid_context")
        _context(
            isinstance(self.authorized_citations, tuple)
            and all(isinstance(citation, AuthorizedCitation) for citation in self.authorized_citations),
            "context.authorized_citations",
            "citations must be an immutable tuple of authorizations",
        )
        _context(
            self.model_contract is None or isinstance(self.model_contract, ModelContract),
            "context.model_contract",
            "model contract binding is invalid",
        )
        _context(
            isinstance(self.interpretation_warrants, tuple)
            and all(
                isinstance(warrant, InterpretationWarrant)
                for warrant in self.interpretation_warrants
            ),
            "context.interpretation_warrants",
            "warrants must be an immutable tuple",
        )
        _context(
            isinstance(self.verification_results, tuple)
            and all(
                isinstance(result, VerificationResultBinding)
                for result in self.verification_results
            ),
            "context.verification_results",
            "verification results must be an immutable tuple",
        )
        release_hashes = {binding.manifest_hash for binding in self.release_bindings}
        _context(
            all(citation.release_manifest_hash in release_hashes for citation in self.authorized_citations),
            "context.authorized_citations",
            "citation falls outside the admitted releases",
        )
        citation_keys = [citation.document_key for citation in self.authorized_citations]
        _context(len(set(citation_keys)) == len(citation_keys), "context.authorized_citations", "citations are ambiguous")
        warrant_keys = [warrant.as_tuple() for warrant in self.interpretation_warrants]
        _context(len(set(warrant_keys)) == len(warrant_keys), "context.interpretation_warrants", "warrants are duplicated")
        claim_ids = [result.claim_id for result in self.verification_results]
        _context(len(set(claim_ids)) == len(claim_ids), "context.verification_results", "claim IDs must be unique")
        _context(
            all(result.evidence_scope_manifest_hash in release_hashes for result in self.verification_results),
            "context.verification_results",
            "verifier scope falls outside the admitted releases",
        )

    @property
    def catalogs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(binding.catalog for binding in self.release_bindings))


@dataclass(frozen=True, slots=True)
class ValidatedResearchAnswer:
    """Detached canonical document produced only after all checks pass."""

    canonical_json: bytes
    content_hash: str

    def to_document(self) -> dict[str, object]:
        value = json.loads(self.canonical_json)
        if not isinstance(value, dict):  # pragma: no cover - construction invariant
            raise RuntimeError("validated research answer is not an object")
        return value


@dataclass(frozen=True, slots=True)
class _ParsedCitation:
    citation_id: str
    authorization: AuthorizedCitation


@dataclass(frozen=True, slots=True)
class _Measurement:
    value: Decimal
    unit: str


@dataclass(frozen=True, slots=True)
class _Calculation:
    operation: str
    input_ids: tuple[str, ...]
    value: Decimal
    unit: str
    decimal_places: int


@dataclass(frozen=True, slots=True)
class _Statement:
    statement_id: str
    kind: str
    text: str
    citation_ids: tuple[str, ...]
    derived_from_ids: tuple[str, ...]
    measurement: _Measurement | None
    calculation: _Calculation | None


def validate_research_answer(
    document: Mapping[str, object],
    *,
    context: ResearchAnswerValidationContext,
) -> ValidatedResearchAnswer:
    """Validate and detach one proposed answer against its admitted context."""

    root = _exact_mapping(document, _ROOT_FIELDS, path="$")
    if root["schema_version"] != "research-answer.v1":
        _fail("invalid_value", "$.schema_version", "unsupported research-answer version")
    if root["task_type"] != context.task_type:
        _fail("scope_mismatch", "$.task_type", "task type differs from admission")
    _valid_enum(root["status"], _STATUSES, path="$.status")
    _valid_datetime(root["as_of"], path="$.as_of")
    if root["as_of"] != context.as_of:
        _fail("scope_mismatch", "$.as_of", "as-of time differs from admission")

    _validate_entities(root["entities"], context=context)
    _validate_release_scope(root["release_scope"], context=context)

    citations = _validate_citations(root["citations"], context=context)
    statements = _validate_statements(root["statements"], citations=citations)
    statement_index = {statement.statement_id: statement for statement in statements}
    _validate_statement_graph(statement_index)
    _validate_calculations(statement_index)
    _validate_interpretations(statement_index, context=context)

    answer_ids = _string_list(
        root["answer_statement_ids"],
        path="$.answer_statement_ids",
        minimum=1,
        identifiers=True,
    )
    counterpoint_ids = _string_list(
        root["counterpoint_statement_ids"],
        path="$.counterpoint_statement_ids",
        identifiers=True,
    )
    _validate_references(answer_ids, statement_index, path="$.answer_statement_ids")
    _validate_references(counterpoint_ids, statement_index, path="$.counterpoint_statement_ids")
    if any(statement_index[item].kind == "open_question" for item in counterpoint_ids):
        _fail("invalid_value", "$.counterpoint_statement_ids", "an open question cannot be counterevidence")

    _valid_text(root["answer"], path="$.answer")
    expected_answer = "\n\n".join(statement_index[item].text for item in answer_ids)
    if root["answer"] != expected_answer:
        _fail("answer_composition_mismatch", "$.answer", "answer does not replay from selected statements")
    _validate_reachability(statement_index, answer_ids=answer_ids, counterpoint_ids=counterpoint_ids)
    _validate_citation_usage(statements, citations)

    _validate_unavailable(root["unavailable"], status=str(root["status"]))
    limitations = _string_list(root["limitations"], path="$.limitations", minimum=1)
    _validate_model_contract(root["model_contract"], context=context)
    _validate_verification_results(root["verification_results"], context=context)
    if _valid_hash(root["audit_manifest_hash"], path="$.audit_manifest_hash") != context.audit_manifest_hash:
        _fail("audit_mismatch", "$.audit_manifest_hash", "audit hash differs from admission")

    visible_text = [statement.text for statement in statements]
    visible_text.extend(limitations)
    visible_text.extend(_unavailable_text(root["unavailable"]))
    _validate_prohibited_text(visible_text)

    try:
        canonical = json.dumps(
            root,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ResearchAnswerValidationError(
            "invalid_shape", "$", "document is not canonical JSON data"
        ) from error
    return ValidatedResearchAnswer(canonical_json=canonical, content_hash=sha256(canonical).hexdigest())


def _validate_entities(value: object, *, context: ResearchAnswerValidationContext) -> None:
    items = _list(value, path="$.entities", minimum=1)
    parsed: list[EntityBinding] = []
    fields = frozenset({"entity_id", "entity_type", "display_name"})
    for index, item in enumerate(items):
        path = f"$.entities[{index}]"
        entity = _exact_mapping(item, fields, path=path)
        entity_id = _valid_text(entity["entity_id"], path=f"{path}.entity_id")
        entity_type = _valid_enum(entity["entity_type"], _ENTITY_TYPES, path=f"{path}.entity_type")
        display_name = _valid_text(entity["display_name"], path=f"{path}.display_name")
        parsed.append(EntityBinding(entity_id=entity_id, entity_type=entity_type, display_name=display_name))
    if tuple(parsed) != context.entities:
        _fail("scope_mismatch", "$.entities", "entities differ from admission")


def _validate_release_scope(value: object, *, context: ResearchAnswerValidationContext) -> None:
    scope = _exact_mapping(
        value,
        frozenset({"catalogs", "release_ids", "manifest_hashes", "observed_through"}),
        path="$.release_scope",
    )
    catalogs = _string_list(scope["catalogs"], path="$.release_scope.catalogs", minimum=1)
    for index, catalog in enumerate(catalogs):
        _valid_enum(catalog, _CATALOGS, path=f"$.release_scope.catalogs[{index}]")
    release_ids = _string_list(scope["release_ids"], path="$.release_scope.release_ids", minimum=1)
    hashes_raw = _list(scope["manifest_hashes"], path="$.release_scope.manifest_hashes", minimum=1)
    hashes = tuple(
        _valid_hash(item, path=f"$.release_scope.manifest_hashes[{index}]")
        for index, item in enumerate(hashes_raw)
    )
    if len(set(hashes)) != len(hashes):
        _fail("duplicate_identifier", "$.release_scope.manifest_hashes", "manifest hashes must be unique")
    _valid_datetime(scope["observed_through"], path="$.release_scope.observed_through")
    expected = (
        context.catalogs,
        tuple(binding.release_id for binding in context.release_bindings),
        tuple(binding.manifest_hash for binding in context.release_bindings),
        context.observed_through,
    )
    if (catalogs, release_ids, hashes, scope["observed_through"]) != expected:
        _fail("scope_mismatch", "$.release_scope", "release scope differs from admission")


def _citation_document_key(citation: Mapping[str, object], *, path: str) -> tuple[object, ...]:
    source_span_value = citation["source_span"]
    source_span: tuple[int, int] | None
    if source_span_value is None:
        source_span = None
    else:
        span = _exact_mapping(
            source_span_value,
            frozenset({"start_char", "end_char"}),
            path=f"{path}.source_span",
        )
        start, end = span["start_char"], span["end_char"]
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not 0 <= start < end
        ):
            _fail("invalid_value", f"{path}.source_span", "source span is invalid")
        source_span = (start, end)
    evidence_id = citation["evidence_id"]
    if evidence_id is not None:
        evidence_id = _valid_text(evidence_id, path=f"{path}.evidence_id")
    chunk_hash = citation["chunk_hash"]
    if chunk_hash is not None:
        chunk_hash = _valid_hash(chunk_hash, path=f"{path}.chunk_hash")
    return (
        citation["source_type"],
        citation["verification_role"],
        _valid_hash(citation["release_manifest_hash"], path=f"{path}.release_manifest_hash"),
        _valid_text(citation["source_record_id"], path=f"{path}.source_record_id"),
        _valid_url(citation["source_url"], path=f"{path}.source_url"),
        evidence_id,
        chunk_hash,
        source_span,
    )


def _validate_citations(
    value: object,
    *,
    context: ResearchAnswerValidationContext,
) -> dict[str, _ParsedCitation]:
    items = _list(value, path="$.citations")
    fields = frozenset(
        {
            "citation_id",
            "source_type",
            "verification_role",
            "release_manifest_hash",
            "source_record_id",
            "source_url",
            "evidence_id",
            "chunk_hash",
            "source_span",
        }
    )
    authorizations = {citation.document_key: citation for citation in context.authorized_citations}
    parsed: dict[str, _ParsedCitation] = {}
    used_keys: set[tuple[object, ...]] = set()
    for index, item in enumerate(items):
        path = f"$.citations[{index}]"
        citation = _exact_mapping(item, fields, path=path)
        citation_id = _valid_id(citation["citation_id"], path=f"{path}.citation_id")
        if citation_id in parsed:
            _fail("duplicate_identifier", f"{path}.citation_id", "citation ID is duplicated")
        _valid_enum(citation["source_type"], _SOURCE_TYPES, path=f"{path}.source_type")
        _valid_enum(
            citation["verification_role"],
            _VERIFICATION_ROLES,
            path=f"{path}.verification_role",
        )
        key = _citation_document_key(citation, path=path)
        if key in used_keys:
            _fail("duplicate_identifier", path, "citation content is duplicated")
        authorization = authorizations.get(key)
        if authorization is None:
            _fail("citation_not_authorized", path, "citation is not in the admitted citation set")
        parsed[citation_id] = _ParsedCitation(citation_id, authorization)
        used_keys.add(key)
    return parsed


def _parse_measurement(value: object, *, path: str) -> _Measurement | None:
    if value is None:
        return None
    measurement = _exact_mapping(value, frozenset({"value", "unit"}), path=path)
    return _Measurement(
        value=_decimal(measurement["value"], path=f"{path}.value"),
        unit=_valid_text(measurement["unit"], path=f"{path}.unit"),
    )


def _parse_calculation(value: object, *, path: str) -> _Calculation | None:
    if value is None:
        return None
    calculation = _exact_mapping(
        value,
        frozenset({"operation", "inputs", "value", "unit", "decimal_places"}),
        path=path,
    )
    operation = _valid_enum(calculation["operation"], _OPERATIONS, path=f"{path}.operation")
    inputs = _list(calculation["inputs"], path=f"{path}.inputs", minimum=1)
    input_ids: list[str] = []
    for index, item in enumerate(inputs):
        input_path = f"{path}.inputs[{index}]"
        input_item = _exact_mapping(item, frozenset({"statement_id"}), path=input_path)
        input_ids.append(_valid_id(input_item["statement_id"], path=f"{input_path}.statement_id"))
    if len(set(input_ids)) != len(input_ids):
        _fail("duplicate_identifier", f"{path}.inputs", "calculation inputs must be unique")
    places = calculation["decimal_places"]
    if not isinstance(places, int) or isinstance(places, bool) or not 0 <= places <= 12:
        _fail("invalid_value", f"{path}.decimal_places", "decimal places must be between zero and twelve")
    return _Calculation(
        operation=operation,
        input_ids=tuple(input_ids),
        value=_decimal(calculation["value"], path=f"{path}.value"),
        unit=_valid_text(calculation["unit"], path=f"{path}.unit"),
        decimal_places=places,
    )


def _validate_statements(
    value: object,
    *,
    citations: Mapping[str, _ParsedCitation],
) -> tuple[_Statement, ...]:
    items = _list(value, path="$.statements", minimum=1)
    fields = frozenset(
        {
            "statement_id",
            "kind",
            "text",
            "citation_ids",
            "derived_from_statement_ids",
            "measurement",
            "calculation",
        }
    )
    statements: list[_Statement] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        path = f"$.statements[{index}]"
        raw = _exact_mapping(item, fields, path=path)
        statement_id = _valid_id(raw["statement_id"], path=f"{path}.statement_id")
        if statement_id in seen:
            _fail("duplicate_identifier", f"{path}.statement_id", "statement ID is duplicated")
        kind = _valid_enum(raw["kind"], _STATEMENT_KINDS, path=f"{path}.kind")
        text = _valid_text(raw["text"], path=f"{path}.text")
        citation_ids = _string_list(raw["citation_ids"], path=f"{path}.citation_ids", identifiers=True)
        derived_ids = _string_list(
            raw["derived_from_statement_ids"],
            path=f"{path}.derived_from_statement_ids",
            identifiers=True,
        )
        measurement = _parse_measurement(raw["measurement"], path=f"{path}.measurement")
        calculation = _parse_calculation(raw["calculation"], path=f"{path}.calculation")
        _validate_statement_type(
            statement_id=statement_id,
            kind=kind,
            text=text,
            citation_ids=citation_ids,
            derived_ids=derived_ids,
            measurement=measurement,
            calculation=calculation,
            citations=citations,
            path=path,
        )
        statements.append(
            _Statement(
                statement_id=statement_id,
                kind=kind,
                text=text,
                citation_ids=citation_ids,
                derived_from_ids=derived_ids,
                measurement=measurement,
                calculation=calculation,
            )
        )
        seen.add(statement_id)
    return tuple(statements)


def _validate_statement_type(
    *,
    statement_id: str,
    kind: str,
    text: str,
    citation_ids: tuple[str, ...],
    derived_ids: tuple[str, ...],
    measurement: _Measurement | None,
    calculation: _Calculation | None,
    citations: Mapping[str, _ParsedCitation],
    path: str,
) -> None:
    del statement_id
    for citation_id in citation_ids:
        if citation_id not in citations:
            _fail("unknown_reference", f"{path}.citation_ids", "citation reference is unknown")
    if kind == "released_fact":
        if not citation_ids or derived_ids or calculation is not None:
            _fail("invalid_shape", path, "released fact structure is invalid")
        authorizations = [citations[item].authorization for item in citation_ids]
        if any(item.source_type != "structured_fact" for item in authorizations):
            _fail("citation_role_invalid", f"{path}.citation_ids", "released facts require structured citations")
        if any(item.statement_text != text for item in authorizations):
            _fail("citation_not_authorized", f"{path}.text", "released fact text is not authorized")
        expected_measurements = {
            None
            if item.measurement_value is None
            else (item.measurement_value, item.measurement_unit)
            for item in authorizations
        }
        if len(expected_measurements) != 1:
            _fail("citation_not_authorized", f"{path}.measurement", "citation measurements conflict")
        expected = next(iter(expected_measurements))
        actual = None if measurement is None else (measurement.value, measurement.unit)
        if actual != expected:
            _fail("citation_not_authorized", f"{path}.measurement", "measurement is not authorized")
        return
    if kind == "narrative_context":
        if not citation_ids or derived_ids or measurement is not None or calculation is not None:
            _fail("invalid_shape", path, "narrative context structure is invalid")
        authorizations = [citations[item].authorization for item in citation_ids]
        if any(item.source_type not in {"narrative_disclosure", "licensed_news"} for item in authorizations):
            _fail("citation_role_invalid", f"{path}.citation_ids", "narrative context requires context citations")
        if any(item.statement_text != text for item in authorizations):
            _fail("citation_not_authorized", f"{path}.text", "context text is not authorized")
        return
    if kind == "deterministic_calculation":
        if citation_ids or not derived_ids or measurement is not None or calculation is None:
            _fail("invalid_shape", path, "deterministic calculation structure is invalid")
        if calculation.input_ids != derived_ids:
            _fail("calculation_invalid", f"{path}.calculation.inputs", "inputs differ from ordered derivation IDs")
        return
    if kind == "agent_interpretation":
        if citation_ids or not derived_ids or measurement is not None or calculation is not None:
            _fail("invalid_shape", path, "agent interpretation structure is invalid")
        return
    if citation_ids or measurement is not None or calculation is not None:
        _fail("invalid_shape", path, "open question structure is invalid")


def _validate_statement_graph(statements: Mapping[str, _Statement]) -> None:
    for statement in statements.values():
        for derived_id in statement.derived_from_ids:
            if derived_id not in statements:
                _fail("unknown_reference", f"$.statements.{statement.statement_id}", "derivation reference is unknown")
            if derived_id == statement.statement_id:
                _fail("cyclic_reference", f"$.statements.{statement.statement_id}", "statement derives from itself")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(statement_id: str) -> None:
        if statement_id in visiting:
            _fail("cyclic_reference", f"$.statements.{statement_id}", "statement derivation is cyclic")
        if statement_id in visited:
            return
        visiting.add(statement_id)
        for derived_id in statements[statement_id].derived_from_ids:
            visit(derived_id)
        visiting.remove(statement_id)
        visited.add(statement_id)

    for statement_id in statements:
        visit(statement_id)


def _statement_measurement(statement: _Statement, *, path: str) -> _Measurement:
    if statement.kind == "released_fact" and statement.measurement is not None:
        return statement.measurement
    if statement.kind == "deterministic_calculation" and statement.calculation is not None:
        return _Measurement(statement.calculation.value, statement.calculation.unit)
    _fail("calculation_invalid", path, "input is not a numeric fact or calculation")


def _validate_calculations(statements: Mapping[str, _Statement]) -> None:
    for statement in statements.values():
        calculation = statement.calculation
        if calculation is None:
            continue
        path = f"$.statements.{statement.statement_id}.calculation"
        inputs = [
            _statement_measurement(statements[input_id], path=f"{path}.inputs")
            for input_id in calculation.input_ids
        ]
        operation = calculation.operation
        if operation == "sum":
            if len(inputs) < 2 or len({item.unit for item in inputs}) != 1:
                _fail("calculation_invalid", path, "sum requires at least two inputs with one unit")
            raw_result = sum((item.value for item in inputs), Decimal(0))
            expected_unit = inputs[0].unit
        elif operation == "difference":
            if len(inputs) != 2 or inputs[0].unit != inputs[1].unit:
                _fail("calculation_invalid", path, "difference requires current and baseline with one unit")
            raw_result = inputs[0].value - inputs[1].value
            expected_unit = inputs[0].unit
        elif operation == "percent_change":
            if len(inputs) != 2 or inputs[0].unit != inputs[1].unit or inputs[1].value == 0:
                _fail("calculation_invalid", path, "percent change requires current and non-zero baseline with one unit")
            raw_result = (inputs[0].value - inputs[1].value) / abs(inputs[1].value) * Decimal(100)
            expected_unit = "percent"
        else:
            if len(inputs) != 2 or any(item.unit != "percent" for item in inputs):
                _fail("calculation_invalid", path, "percentage-point change requires two percentage inputs")
            raw_result = inputs[0].value - inputs[1].value
            expected_unit = "percentage_points"
        quantum = Decimal(1).scaleb(-calculation.decimal_places)
        expected_value = raw_result.quantize(quantum, rounding=ROUND_HALF_EVEN)
        if calculation.unit != expected_unit or calculation.value != expected_value:
            _fail("calculation_mismatch", path, "declared result does not replay")
        if statement.text != _calculation_text(calculation, expected_value):
            _fail("calculation_mismatch", f"$.statements.{statement.statement_id}.text", "calculation text does not replay")


def _calculation_text(calculation: _Calculation, value: Decimal) -> str:
    rendered = f"{value:.{calculation.decimal_places}f}"
    if calculation.operation == "sum":
        return f"Calculated sum: {rendered} {calculation.unit}."
    if calculation.operation == "difference":
        return f"Calculated difference: {rendered} {calculation.unit}."
    if calculation.operation == "percent_change":
        return f"Calculated percent change: {rendered}%."
    return f"Calculated percentage-point change: {rendered} percentage points."


def _validate_interpretations(
    statements: Mapping[str, _Statement],
    *,
    context: ResearchAnswerValidationContext,
) -> None:
    warrants = {warrant.as_tuple() for warrant in context.interpretation_warrants}
    for statement in statements.values():
        if statement.kind != "agent_interpretation":
            continue
        key = (statement.statement_id, statement.text, statement.derived_from_ids)
        if key not in warrants:
            _fail(
                "interpretation_not_warranted",
                f"$.statements.{statement.statement_id}",
                "interpretation lacks an independent exact warrant",
            )


def _validate_references(
    reference_ids: tuple[str, ...],
    statements: Mapping[str, _Statement],
    *,
    path: str,
) -> None:
    if any(item not in statements for item in reference_ids):
        _fail("unknown_reference", path, "statement reference is unknown")


def _validate_reachability(
    statements: Mapping[str, _Statement],
    *,
    answer_ids: tuple[str, ...],
    counterpoint_ids: tuple[str, ...],
) -> None:
    reachable: set[str] = set()

    def walk(statement_id: str) -> None:
        if statement_id in reachable:
            return
        reachable.add(statement_id)
        for derived_id in statements[statement_id].derived_from_ids:
            walk(derived_id)

    for root in (*answer_ids, *counterpoint_ids):
        walk(root)
    if reachable != set(statements):
        _fail("unreachable_statement", "$.statements", "every statement must support the answer or a counterpoint")


def _validate_citation_usage(
    statements: tuple[_Statement, ...],
    citations: Mapping[str, _ParsedCitation],
) -> None:
    used = {citation_id for statement in statements for citation_id in statement.citation_ids}
    if used != set(citations):
        _fail("unused_citation", "$.citations", "every citation must support a visible statement")


def _validate_unavailable(value: object, *, status: str) -> None:
    items = _list(value, path="$.unavailable")
    fields = frozenset({"request", "reason", "detail"})
    requests: set[str] = set()
    for index, item in enumerate(items):
        path = f"$.unavailable[{index}]"
        unavailable = _exact_mapping(item, fields, path=path)
        request = _valid_text(unavailable["request"], path=f"{path}.request")
        if request in requests:
            _fail("duplicate_identifier", f"{path}.request", "unavailable request is duplicated")
        _valid_enum(unavailable["reason"], _UNAVAILABLE_REASONS, path=f"{path}.reason")
        _valid_text(unavailable["detail"], path=f"{path}.detail")
        requests.add(request)
    if status == "unavailable" and not items:
        _fail("invalid_shape", "$.unavailable", "unavailable status requires an explicit unavailable item")


def _unavailable_text(value: object) -> list[str]:
    if not isinstance(value, list):  # already validated
        return []
    return [
        text
        for item in value
        if isinstance(item, Mapping)
        for text in (item.get("request"), item.get("detail"))
        if isinstance(text, str)
    ]


def _validate_model_contract(value: object, *, context: ResearchAnswerValidationContext) -> None:
    if value is None:
        if context.model_contract is not None:
            _fail("model_contract_mismatch", "$.model_contract", "model attribution is missing")
        return
    model = _exact_mapping(
        value,
        frozenset(
            {"provider", "model_id", "prompt_contract_hash", "tool_contract_hash", "provider_attempt_id"}
        ),
        path="$.model_contract",
    )
    parsed = ModelContract(
        provider=_valid_text(model["provider"], path="$.model_contract.provider"),
        model_id=_valid_text(model["model_id"], path="$.model_contract.model_id"),
        prompt_contract_hash=_valid_hash(
            model["prompt_contract_hash"], path="$.model_contract.prompt_contract_hash"
        ),
        tool_contract_hash=_valid_hash(
            model["tool_contract_hash"], path="$.model_contract.tool_contract_hash"
        ),
        provider_attempt_id=_valid_text(
            model["provider_attempt_id"], path="$.model_contract.provider_attempt_id"
        ),
    )
    if context.model_contract is None or parsed.as_tuple() != context.model_contract.as_tuple():
        _fail("model_contract_mismatch", "$.model_contract", "model attribution differs from admission")


def _validate_verification_results(
    value: object,
    *,
    context: ResearchAnswerValidationContext,
) -> None:
    items = _list(value, path="$.verification_results")
    fields = frozenset(
        {"claim_id", "verdict", "authority", "evidence_scope_manifest_hash", "audit_manifest_hash"}
    )
    parsed: list[tuple[str, ...]] = []
    claim_ids: set[str] = set()
    for index, item in enumerate(items):
        path = f"$.verification_results[{index}]"
        result = _exact_mapping(item, fields, path=path)
        claim_id = _valid_text(result["claim_id"], path=f"{path}.claim_id")
        if claim_id in claim_ids:
            _fail("duplicate_identifier", f"{path}.claim_id", "claim ID is duplicated")
        verdict = _valid_enum(result["verdict"], _VERDICTS, path=f"{path}.verdict")
        if result["authority"] != "deterministic_verifier":
            _fail("verification_authority_mismatch", f"{path}.authority", "verifier authority is invalid")
        parsed.append(
            (
                claim_id,
                verdict,
                "deterministic_verifier",
                _valid_hash(
                    result["evidence_scope_manifest_hash"],
                    path=f"{path}.evidence_scope_manifest_hash",
                ),
                _valid_hash(result["audit_manifest_hash"], path=f"{path}.audit_manifest_hash"),
            )
        )
        claim_ids.add(claim_id)
    expected = [result.as_tuple() for result in context.verification_results]
    if parsed != expected:
        _fail(
            "verification_authority_mismatch",
            "$.verification_results",
            "verification results differ from deterministic verifier output",
        )


def _validate_prohibited_text(values: list[str]) -> None:
    for index, value in enumerate(values):
        if has_prohibited_investment_output(value):
            _fail(
                "prohibited_content",
                f"$.visible_text[{index}]",
                "advisory, allocation, price-target, or trade language is prohibited",
            )
