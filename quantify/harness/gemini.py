"""Gemini structured-extraction adapter; final claim verdicts remain deterministic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from quantify.engine import (
    CalibrationMethod,
    CounterevidencePair,
    DisclosureAssessment,
    DisclosureStatus,
    EvidenceSnapshot,
    MetricBaselineClaim,
    MetricComparisonClaim,
    MetricThresholdClaim,
    Relation,
    ReportSpan,
    StatementClassification,
    build_upper_baseline_calibration,
)

from .extraction import ExtractedStatement, ExtractionResult
from .disclosure import DisclosureContext


_GENERATE_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class JsonTransport(Protocol):
    def post_json(self, *, url: str, headers: dict[str, str], body: dict) -> dict: ...


class UrllibJsonTransport:
    """Production HTTPS transport; credentials are never placed in the URL."""

    def post_json(self, *, url: str, headers: dict[str, str], body: dict) -> dict:
        request = Request(
            url,
            data=json.dumps(body, separators=(",", ":")).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS host
                return json.loads(response.read())
        except HTTPError as error:
            detail = error.read().decode(errors="replace")[:1000]
            raise RuntimeError(
                f"Gemini extraction request failed with HTTP {error.code}: {detail}"
            ) from error


@dataclass(frozen=True, slots=True)
class GeminiExtractionConfig:
    """Pinned extraction contract and explicit price inputs for observability."""

    model: str = "gemini-3.1-flash-lite"
    temperature: float = 0.0
    input_price_per_million_usd: float = 0.0
    output_price_per_million_usd: float = 0.0
    max_output_tokens: int = 2048
    schema_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not self.model or not 0.0 <= self.temperature <= 2.0:
            raise ValueError("Gemini extraction config has an invalid model or temperature")
        if (
            self.input_price_per_million_usd < 0
            or self.output_price_per_million_usd < 0
            or self.max_output_tokens <= 0
        ):
            raise ValueError("Gemini extraction config has invalid limits or pricing")

    @property
    def prompt_hash(self) -> str:
        return sha256(
            json.dumps(
                {
                    "model": self.model,
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_output_tokens,
                    "schema_version": self.schema_version,
                    "instruction": _SYSTEM_INSTRUCTION,
                    "schema": _RESPONSE_SCHEMA,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()


class GeminiStructuredExtractor:
    """One untrusted Gemini extraction call over a declared frozen evidence pool."""

    def __init__(
        self,
        *,
        api_key: str,
        config: GeminiExtractionConfig = GeminiExtractionConfig(),
        transport: JsonTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required")
        self._api_key = api_key
        self.config = config
        self._transport = transport or UrllibJsonTransport()

    def extract(
        self, *, report_text: str, snapshot: EvidenceSnapshot
    ) -> ExtractionResult:
        response = self._transport.post_json(
            url=_GENERATE_ENDPOINT.format(model=self.config.model),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_key,
            },
            body=_request_body(
                report_text=report_text, snapshot=snapshot, config=self.config
            ),
        )
        return _extraction_from_response(
            response=response,
            report_text=report_text,
            snapshot=snapshot,
            config=self.config,
        )


@dataclass(frozen=True, slots=True)
class GeminiDisclosureConfig:
    """Pinned semantic-disclosure assessment contract for the bounded agent step."""

    model: str = "gemini-3.1-flash-lite"
    temperature: float = 0.0
    schema_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not self.model or not 0.0 <= self.temperature <= 2.0:
            raise ValueError("Gemini disclosure config has an invalid model or temperature")

    @property
    def detector_version(self) -> str:
        return f"gemini-{self.model}-{self.schema_version}"

    @property
    def prompt_hash(self) -> str:
        return sha256(
            json.dumps(
                {
                    "model": self.model,
                    "temperature": self.temperature,
                    "schema_version": self.schema_version,
                    "instruction": _DISCLOSURE_SYSTEM_INSTRUCTION,
                    "schema": _DISCLOSURE_RESPONSE_SCHEMA,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()


class GeminiDisclosureDetector:
    """One conservative assessment call for each bounded disclosure-resolution step."""

    def __init__(
        self,
        *,
        api_key: str,
        config: GeminiDisclosureConfig = GeminiDisclosureConfig(),
        transport: JsonTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required")
        self._api_key = api_key
        self.config = config
        self._transport = transport or UrllibJsonTransport()

    def assess(
        self,
        *,
        report_text: str,
        counterevidence_pairs: tuple[CounterevidencePair, ...],
        contexts: tuple[DisclosureContext, ...],
    ) -> tuple[DisclosureAssessment, ...]:
        if not counterevidence_pairs:
            return ()
        if len(contexts) != len(counterevidence_pairs):
            raise ValueError("Gemini disclosure assessment requires every pair context")
        response = self._transport.post_json(
            url=_GENERATE_ENDPOINT.format(model=self.config.model),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_key,
            },
            body=_disclosure_request_body(
                report_text=report_text, contexts=contexts, config=self.config
            ),
        )
        try:
            return _disclosure_assessments_from_response(
                response=response,
                counterevidence_pairs=counterevidence_pairs,
                config=self.config,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return tuple(
                DisclosureAssessment(
                    claim_id=pair.claim_id,
                    defeating_evidence_id=pair.evidence_id,
                    status=DisclosureStatus.AMBIGUOUS,
                    detector_version=self.config.detector_version,
                    prompt_hash=self.config.prompt_hash,
                )
                for pair in counterevidence_pairs
            )


_SYSTEM_INSTRUCTION = (
    "Extract closed factual financial claims from the report using only the "
    "provided frozen SEC facts and their evidence IDs. Do not decide whether a "
    "claim is true, do not invent facts, and classify interpretation or unclear "
    "language conservatively. Copy each report sentence and claim fragment exactly."
)

_DISCLOSURE_SYSTEM_INSTRUCTION = (
    "Assess whether each supplied defeating SEC fact is clearly acknowledged "
    "in the report. Return not_disclosed only for clear absence, disclosed_* "
    "only for clear acknowledgement, and ambiguous for indirect, incomplete, "
    "or uncertain language. Do not infer facts outside the supplied report and "
    "frozen evidence context."
)

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "statements": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "classification": {
                        "type": "STRING",
                        "enum": [
                            "classified",
                            "unclassified",
                            "non_factual",
                            "requires_agent_resolution",
                        ],
                    },
                    "sentence_text": {"type": "STRING"},
                    "claim_fragment": {"type": "STRING"},
                    "claim_type": {
                        "type": "STRING",
                        "enum": ["threshold", "comparison", "baseline", "none"],
                    },
                    "relation": {
                        "type": "STRING",
                        "enum": [
                            Relation.GREATER_THAN.value,
                            Relation.LESS_THAN.value,
                            Relation.OUTSIDE_UPPER_BASELINE.value,
                        ],
                    },
                    "cited_evidence_id": {"type": "STRING"},
                    "left_evidence_id": {"type": "STRING"},
                    "right_evidence_id": {"type": "STRING"},
                    "threshold": {"type": "STRING"},
                    "historical_evidence_ids": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                    },
                    "historical_cutoff": {"type": "STRING"},
                },
                "required": ["classification", "sentence_text", "claim_type"],
            },
        }
    },
    "required": ["statements"],
}

_DISCLOSURE_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "assessments": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "claim_id": {"type": "STRING"},
                    "defeating_evidence_id": {"type": "STRING"},
                    "status": {
                        "type": "STRING",
                        "enum": [
                            item.value for item in DisclosureStatus
                        ],
                    },
                },
                "required": ["claim_id", "defeating_evidence_id", "status"],
            },
        }
    },
    "required": ["assessments"],
}


def _request_body(
    *, report_text: str, snapshot: EvidenceSnapshot, config: GeminiExtractionConfig
) -> dict:
    visible_ids = set(snapshot.visible_evidence_ids or ())
    facts = [
        {
            "evidence_id": item.evidence_id,
            "metric": item.metric,
            "value": str(item.value),
            "unit": item.unit,
            "period_start": item.period_start.isoformat(),
            "period_end": item.period_end.isoformat(),
            "filed_at": item.filed_at.isoformat(),
        }
        for item in snapshot.evidence
        if item.eligible
        and (snapshot.visible_evidence_ids is None or item.evidence_id in visible_ids)
    ]
    return {
        "system_instruction": {"parts": [{"text": _SYSTEM_INSTRUCTION}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": json.dumps(
                            {"report_text": report_text, "frozen_facts": facts},
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    }
                ],
            }
        ],
        "generation_config": {
            "temperature": config.temperature,
            "max_output_tokens": config.max_output_tokens,
            "response_mime_type": "application/json",
            "response_schema": _RESPONSE_SCHEMA,
        },
    }


def _disclosure_request_body(
    *,
    report_text: str,
    contexts: tuple[DisclosureContext, ...],
    config: GeminiDisclosureConfig,
) -> dict:
    return {
        "system_instruction": {
            "parts": [{"text": _DISCLOSURE_SYSTEM_INSTRUCTION}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": json.dumps(
                            {
                                "report_text": report_text,
                                "counterevidence": [
                                    {
                                        "claim_id": context.claim.claim_id,
                                        "claim": _claim_as_dict(context.claim),
                                        "defeating_evidence": _evidence_as_dict(
                                            context.defeating_evidence
                                        ),
                                    }
                                    for context in contexts
                                ],
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    }
                ],
            }
        ],
        "generation_config": {
            "temperature": config.temperature,
            "max_output_tokens": 1024,
            "response_mime_type": "application/json",
            "response_schema": _DISCLOSURE_RESPONSE_SCHEMA,
        },
    }


def _extraction_from_response(
    *,
    response: dict,
    report_text: str,
    snapshot: EvidenceSnapshot,
    config: GeminiExtractionConfig,
) -> ExtractionResult:
    try:
        payload = json.loads(_response_text(response))
        statements = payload["statements"]
        if not isinstance(statements, list):
            raise ValueError("Gemini statements must be a list")
        extracted = tuple(
            _statement_from_payload(
                item=item,
                index=index,
                report_text=report_text,
                snapshot=snapshot,
            )
            for index, item in enumerate(statements, start=1)
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, InvalidOperation):
        extracted = (_resolution_statement(report_text=report_text),)
    input_tokens, output_tokens = _usage_tokens(response)
    return ExtractionResult(
        statements=extracted,
        extractor_version=f"gemini-{config.model}-{config.schema_version}",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_cost=(
            input_tokens / 1_000_000 * config.input_price_per_million_usd
            + output_tokens / 1_000_000 * config.output_price_per_million_usd
        ),
    )


def _statement_from_payload(
    *, item: object, index: int, report_text: str, snapshot: EvidenceSnapshot
) -> ExtractedStatement:
    if not isinstance(item, dict):
        raise ValueError("Gemini statement must be an object")
    classification = StatementClassification(_string(item, "classification"))
    sentence_text = _string(item, "sentence_text")
    claim_fragment = _string(item, "claim_fragment", default=sentence_text)
    sentence_start = _unique_offset(text=report_text, fragment=sentence_text)
    fragment_offset = _unique_offset(text=sentence_text, fragment=claim_fragment)
    statement_id = f"gemini-s{index}"
    span = ReportSpan(
        span_id=f"{statement_id}-span",
        sentence_text=sentence_text,
        sentence_start=sentence_start,
        sentence_end=sentence_start + len(sentence_text),
        claim_fragment=claim_fragment,
        fragment_start=sentence_start + fragment_offset,
        fragment_end=sentence_start + fragment_offset + len(claim_fragment),
    )
    if classification is not StatementClassification.CLASSIFIED:
        return ExtractedStatement(
            statement_id=statement_id, classification=classification, report_span=span
        )
    claim = _claim_from_payload(
        item=item, claim_id=f"{statement_id}-claim", snapshot=snapshot
    )
    return ExtractedStatement(
        statement_id=statement_id,
        classification=classification,
        report_span=span,
        claims=(claim,),
    )


def _claim_from_payload(*, item: dict, claim_id: str, snapshot: EvidenceSnapshot):
    claim_type = _string(item, "claim_type")
    relation = Relation(_string(item, "relation"))
    if claim_type == "threshold" and relation in {
        Relation.GREATER_THAN,
        Relation.LESS_THAN,
    }:
        return MetricThresholdClaim(
            claim_id=claim_id,
            cited_evidence_id=_string(item, "cited_evidence_id"),
            relation=relation,
            threshold=Decimal(_string(item, "threshold")),
        )
    if claim_type == "comparison" and relation in {
        Relation.GREATER_THAN,
        Relation.LESS_THAN,
    }:
        return MetricComparisonClaim(
            claim_id=claim_id,
            left_evidence_id=_string(item, "left_evidence_id"),
            relation=relation,
            right_evidence_id=_string(item, "right_evidence_id"),
        )
    if claim_type == "baseline" and relation is Relation.OUTSIDE_UPPER_BASELINE:
        return MetricBaselineClaim(
            claim_id=claim_id,
            cited_evidence_id=_string(item, "cited_evidence_id"),
            relation=relation,
            calibration=build_upper_baseline_calibration(
                snapshot=snapshot,
                historical_evidence_ids=_string_list(item, "historical_evidence_ids"),
                historical_cutoff=date.fromisoformat(
                    _string(item, "historical_cutoff")
                ),
                method=CalibrationMethod.HISTORICAL_RANGE,
            ),
        )
    raise ValueError("unsupported Gemini typed claim")


def _resolution_statement(*, report_text: str) -> ExtractedStatement:
    return ExtractedStatement(
        statement_id="gemini-schema-failure",
        classification=StatementClassification.REQUIRES_AGENT_RESOLUTION,
        report_span=ReportSpan(
            span_id="gemini-schema-failure-span",
            sentence_text=report_text,
            sentence_start=0,
            sentence_end=len(report_text),
            claim_fragment=report_text,
            fragment_start=0,
            fragment_end=len(report_text),
        ),
    )


def _response_text(response: dict) -> str:
    candidates = response.get("candidates") if isinstance(response, dict) else None
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise ValueError("Gemini response must include one candidate")
    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list) or len(parts) != 1:
        raise ValueError("Gemini response must include one text part")
    text = parts[0].get("text") if isinstance(parts[0], dict) else None
    if not isinstance(text, str):
        raise ValueError("Gemini response is missing text")
    return text


def _disclosure_assessments_from_response(
    *,
    response: dict,
    counterevidence_pairs: tuple[CounterevidencePair, ...],
    config: GeminiDisclosureConfig,
) -> tuple[DisclosureAssessment, ...]:
    payload = json.loads(_response_text(response))
    raw_assessments = payload["assessments"]
    if not isinstance(raw_assessments, list):
        raise ValueError("Gemini disclosure assessments must be a list")
    expected_pairs = {(item.claim_id, item.evidence_id) for item in counterevidence_pairs}
    by_pair: dict[tuple[str, str], DisclosureStatus] = {}
    for item in raw_assessments:
        if not isinstance(item, dict):
            raise ValueError("Gemini disclosure assessment must be an object")
        claim_id = _string(item, "claim_id")
        evidence_id = _string(item, "defeating_evidence_id")
        pair = (claim_id, evidence_id)
        if pair in by_pair or pair not in expected_pairs:
            raise ValueError("Gemini disclosure response has invalid pair identity")
        by_pair[pair] = DisclosureStatus(_string(item, "status"))
    if set(by_pair) != expected_pairs:
        raise ValueError("Gemini disclosure response is incomplete")
    return tuple(
        DisclosureAssessment(
            claim_id=pair.claim_id,
            defeating_evidence_id=pair.evidence_id,
            status=by_pair[(pair.claim_id, pair.evidence_id)],
            detector_version=config.detector_version,
            prompt_hash=config.prompt_hash,
        )
        for pair in counterevidence_pairs
    )


def _claim_as_dict(claim: object) -> dict:
    if isinstance(claim, MetricThresholdClaim):
        return {
            "type": "threshold",
            "relation": claim.relation.value,
            "cited_evidence_id": claim.cited_evidence_id,
            "threshold": str(claim.threshold),
        }
    if isinstance(claim, MetricComparisonClaim):
        return {
            "type": "comparison",
            "relation": claim.relation.value,
            "left_evidence_id": claim.left_evidence_id,
            "right_evidence_id": claim.right_evidence_id,
        }
    if isinstance(claim, MetricBaselineClaim):
        return {
            "type": "baseline",
            "relation": claim.relation.value,
            "cited_evidence_id": claim.cited_evidence_id,
            "historical_evidence_ids": list(claim.calibration.historical_evidence_ids),
            "historical_cutoff": claim.calibration.historical_cutoff.isoformat(),
        }
    raise ValueError("unsupported disclosure claim")


def _evidence_as_dict(evidence) -> dict:
    return {
        "evidence_id": evidence.evidence_id,
        "metric": evidence.metric,
        "value": str(evidence.value),
        "unit": evidence.unit,
        "period_start": evidence.period_start.isoformat(),
        "period_end": evidence.period_end.isoformat(),
        "filed_at": evidence.filed_at.isoformat(),
    }


def _usage_tokens(response: dict) -> tuple[int, int]:
    usage = response.get("usageMetadata") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return 0, 0
    input_tokens = usage.get("promptTokenCount", 0)
    output_tokens = usage.get("candidatesTokenCount", 0)
    if (
        isinstance(input_tokens, bool)
        or isinstance(output_tokens, bool)
        or not isinstance(input_tokens, int)
        or not isinstance(output_tokens, int)
        or input_tokens < 0
        or output_tokens < 0
    ):
        return 0, 0
    return input_tokens, output_tokens


def _unique_offset(*, text: str, fragment: str) -> int:
    if not fragment:
        raise ValueError("Gemini report span cannot be empty")
    first = text.find(fragment)
    if first < 0 or first != text.rfind(fragment):
        raise ValueError("Gemini report span must occur exactly once")
    return first


def _string(payload: dict, name: str, *, default: str | None = None) -> str:
    value = payload.get(name, default)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Gemini output requires {name}")
    return value


def _string_list(payload: dict, name: str) -> tuple[str, ...]:
    value = payload.get(name)
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"Gemini output requires {name}")
    return tuple(value)
