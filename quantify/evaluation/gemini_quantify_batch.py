"""Gemini Batch adapter for the model-proposes, Quantify-verifies parity path."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from typing import Protocol

from quantify.harness import verify_report
from quantify.harness.gemini import (
    GeminiExtractionConfig,
    _RESPONSE_SCHEMA,
    _SYSTEM_INSTRUCTION,
    _extraction_from_response,
)

from .gemini_batch import JsonTransport, UrllibJsonTransport
from .model_profiles import (
    EvaluationModelProfile,
    estimate_evaluation_cost,
    require_cost_within_budget,
)
from .regression import RegressionCase


_BATCH_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchGenerateContent"
_BATCH_RESOURCE_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/{batch_name}"
_SUCCEEDED_STATES = {"BATCH_STATE_SUCCEEDED", "JOB_STATE_SUCCEEDED"}
_CLAIM_TYPES = {"threshold", "comparison", "baseline"}


@dataclass(frozen=True, slots=True)
class QuantifyParityWorkItem:
    """Model-visible public report and frozen fact pool for one evaluation case."""

    request_id: str
    report_text: str
    evidence: tuple[dict[str, str], ...]


@dataclass(frozen=True, slots=True)
class QuantifyParityWorklist:
    """Public model worklist plus evaluator-only case objects for verification."""

    items: tuple[QuantifyParityWorkItem, ...]
    _cases_by_request_id: dict[str, RegressionCase]

    def model_input(self) -> dict:
        return {
            "worklist_version": "1.0.0",
            "items": [
                {
                    "request_id": item.request_id,
                    "report_text": item.report_text,
                    "evidence": list(item.evidence),
                }
                for item in self.items
            ],
        }

    def case_for(self, *, request_id: str) -> RegressionCase:
        try:
            return self._cases_by_request_id[request_id]
        except KeyError as error:
            raise ValueError("unknown Quantify parity request ID") from error


@dataclass(frozen=True, slots=True)
class GeminiQuantifyBatchSubmission:
    batch_name: str
    request_ids: tuple[str, ...]
    estimated_total_cost_usd: float


@dataclass(frozen=True, slots=True)
class GeminiQuantifyOutcomes:
    """Opaque final outcomes after deterministic local verification."""

    batch_name: str
    model: str
    temperature: float
    prompt_hash: str
    outcomes: tuple[tuple[str, str], ...]


def build_quantify_parity_worklist(
    *,
    mechanical_cases: tuple[RegressionCase, ...],
    judgment_cases: tuple[RegressionCase, ...],
) -> QuantifyParityWorklist:
    """Build a fixed public-facts worklist without exposing evaluator labels."""

    cases = tuple(sorted((*mechanical_cases, *judgment_cases), key=lambda item: item.case_id))
    if len(cases) != 30 or {item.category for item in cases} != {"mechanical", "judgment"}:
        raise ValueError("Quantify parity requires the fixed 20 mechanical + 10 judgment cases")
    request_ids = [sha256(item.case_id.encode()).hexdigest()[:16] for item in cases]
    if len(request_ids) != len(set(request_ids)):
        raise ValueError("Quantify parity request IDs must be unique")
    items = tuple(
        QuantifyParityWorkItem(
            request_id=request_id,
            report_text=case.report_text,
            evidence=tuple(
                {
                    "evidence_id": fact.evidence_id,
                    "metric": fact.metric,
                    "value": str(fact.value),
                    "unit": fact.unit,
                    "period_start": fact.period_start.isoformat(),
                    "period_end": fact.period_end.isoformat(),
                    "filed_at": fact.filed_at.isoformat(),
                }
                for fact in case.snapshot.evidence
                if fact.eligible
            ),
        )
        for request_id, case in zip(request_ids, cases, strict=True)
    )
    return QuantifyParityWorklist(
        items=items,
        _cases_by_request_id=dict(zip(request_ids, cases, strict=True)),
    )


def _extraction_config(*, profile: EvaluationModelProfile) -> GeminiExtractionConfig:
    """Map the pinned evaluation envelope to the deployed extraction contract."""

    return GeminiExtractionConfig(
        model=profile.model,
        temperature=profile.temperature,
        input_price_per_million_usd=profile.input_price_per_million_usd,
        output_price_per_million_usd=profile.output_price_per_million_usd,
        max_output_tokens=profile.max_output_tokens_per_request,
        max_input_payload_bytes=profile.max_input_tokens_per_request,
    )


class GeminiQuantifyBatchClient:
    """Run one structured extraction Batch; verification remains local and deterministic."""

    def __init__(self, *, api_key: str, transport: JsonTransport | None = None) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required")
        self._api_key = api_key
        self._transport = transport or UrllibJsonTransport()

    def submit(
        self, *, profile: EvaluationModelProfile, worklist: QuantifyParityWorklist
    ) -> GeminiQuantifyBatchSubmission:
        estimate = estimate_evaluation_cost(
            profile=profile, case_count=len(worklist.items), paths_per_case=1
        )
        require_cost_within_budget(estimate=estimate)
        requests = [
            {
                "request": _generate_content_request(item=item, profile=profile),
                "metadata": {"key": item.request_id},
            }
            for item in worklist.items
        ]
        response = self._transport.post_json(
            url=_BATCH_ENDPOINT.format(model=profile.model),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_key,
            },
            body={
                "batch": {
                    "display_name": "quantify-verified-parity-v1",
                    "input_config": {"requests": {"requests": requests}},
                }
            },
        )
        batch_name = response.get("name")
        _validate_batch_name(batch_name)
        return GeminiQuantifyBatchSubmission(
            batch_name=batch_name,
            request_ids=tuple(item.request_id for item in worklist.items),
            estimated_total_cost_usd=estimate.total_cost_usd,
        )

    def collect(
        self,
        *,
        batch_name: str,
        profile: EvaluationModelProfile,
        worklist: QuantifyParityWorklist,
    ) -> GeminiQuantifyOutcomes:
        """Fail closed unless the complete provider batch becomes valid local input."""

        _validate_batch_name(batch_name)
        payload = self._transport.get_json(
            url=_BATCH_RESOURCE_ENDPOINT.format(batch_name=batch_name),
            headers={"x-goog-api-key": self._api_key},
        )
        if _batch_state(payload) not in _SUCCEEDED_STATES:
            raise ValueError(f"Gemini batch has not succeeded: {_batch_state(payload)}")
        outcomes = tuple(
            (
                item.request_id,
                _verify_extraction(
                    case=worklist.case_for(request_id=item.request_id),
                    report_text=item.report_text,
                    response=_response_for(
                        payload=payload,
                        expected_request_id=item.request_id,
                        position=index,
                        expected_count=len(worklist.items),
                    ),
                    config=_extraction_config(profile=profile),
                ),
            )
            for index, item in enumerate(worklist.items)
        )
        return GeminiQuantifyOutcomes(
            batch_name=batch_name,
            model=profile.model,
            temperature=profile.temperature,
            prompt_hash=quantify_prompt_hash(profile=profile),
            outcomes=outcomes,
        )


def quantify_prompt_hash(*, profile: EvaluationModelProfile) -> str:
    """Return the exact deployed structured-extraction prompt identity."""

    return _extraction_config(profile=profile).prompt_hash


def quantify_outcome_artifact_as_dict(*, outcomes: GeminiQuantifyOutcomes) -> dict:
    return {
        "artifact_version": "1.0.0",
        "path": "quantify",
        "run": {
            "model": outcomes.model,
            "prompt_hash": outcomes.prompt_hash,
            "temperature": outcomes.temperature,
        },
        "outcomes": [
            {"request_id": request_id, "outcome": outcome}
            for request_id, outcome in outcomes.outcomes
        ],
    }


def _generate_content_request(
    *, item: QuantifyParityWorkItem, profile: EvaluationModelProfile
) -> dict:
    return {
        "system_instruction": {
            "parts": [
                {
                    "text": _SYSTEM_INSTRUCTION
                }
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": json.dumps(
                            {
                                "report_spans": [
                                    {"report_span_id": "report-s1", "text": item.report_text}
                                ],
                                "frozen_facts": item.evidence,
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    }
                ],
            }
        ],
        "generation_config": {
            "temperature": profile.temperature,
            "max_output_tokens": profile.max_output_tokens_per_request,
            "response_mime_type": "application/json",
            "response_schema": _RESPONSE_SCHEMA,
        },
    }


def _verify_extraction(
    *,
    case: RegressionCase,
    report_text: str,
    response: dict,
    config: GeminiExtractionConfig,
) -> str:
    extraction = _extraction_from_response(
        response=response,
        report_text=report_text,
        snapshot=case.snapshot,
        config=config,
    )
    initial = verify_report(
        report_text=report_text,
        snapshot=case.snapshot,
        extraction=extraction,
    )
    classified_claims = tuple(
        claim
        for statement in extraction.statements
        for claim in statement.claims
    )
    if len(classified_claims) != 1:
        return "unclassified"
    model_claim_id = classified_claims[0].claim_id
    assessment_by_evidence = {
        item.defeating_evidence_id: item for item in case.disclosure_assessments
    }
    assessments = tuple(
        replace(assessment_by_evidence[pair.evidence_id], claim_id=model_claim_id)
        for pair in initial.claim_analysis.counterevidence_pairs
        if pair.evidence_id in assessment_by_evidence
    )
    report = verify_report(
        report_text=report_text,
        snapshot=case.snapshot,
        extraction=extraction,
        disclosure_assessments=assessments,
    )
    if len(report.claim_verdicts) != 1:
        return "unclassified"
    return report.claim_verdicts[0].verdict.value


def _response_for(
    *, payload: dict, expected_request_id: str, position: int, expected_count: int
) -> dict:
    inline = _inline_responses(payload)
    if len(inline) != expected_count:
        raise ValueError("Gemini batch must return one inline result per request")
    item = inline[position]
    if not isinstance(item, dict):
        raise ValueError("Gemini inline result must be an object")
    metadata = item.get("metadata")
    request_id = metadata.get("key") if isinstance(metadata, dict) else None
    if request_id != expected_request_id:
        raise ValueError("Gemini inline result key does not match the submitted order")
    if item.get("error") is not None:
        raise ValueError("Gemini batch contains a failed inline request")
    response = item.get("response")
    if not isinstance(response, dict):
        raise ValueError("Gemini inline result does not include a response")
    _response_text(response)
    return response


def _inline_responses(payload: dict) -> list:
    response = payload.get("response")
    if not isinstance(response, dict):
        response = payload.get("output")
    if not isinstance(response, dict):
        raise ValueError("successful Gemini batch does not include inline results")
    inline = response.get("inlinedResponses")
    if isinstance(inline, dict):
        inline = inline.get("inlinedResponses")
    if not isinstance(inline, list):
        raise ValueError("successful Gemini batch does not include inline results")
    return inline


def _response_text(response: object) -> str:
    if not isinstance(response, dict):
        raise ValueError("Gemini inline result does not include a response")
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise ValueError("Gemini inline result must include exactly one candidate")
    candidate = candidates[0]
    content = candidate.get("content") if isinstance(candidate, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list) or len(parts) != 1:
        raise ValueError("Gemini inline result must include exactly one text part")
    text = parts[0].get("text") if isinstance(parts[0], dict) else None
    if not isinstance(text, str):
        raise ValueError("Gemini inline result does not include text content")
    return text


def _batch_state(payload: dict) -> str:
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    state = metadata.get("state") if isinstance(metadata, dict) else payload.get("state")
    if not isinstance(state, str) or not state:
        raise ValueError("Gemini batch response does not include a state")
    return state


def _validate_batch_name(batch_name: object) -> None:
    if not isinstance(batch_name, str) or not batch_name.startswith("batches/"):
        raise ValueError("Gemini batch name must have the batches/{id} form")
    identifier = batch_name.removeprefix("batches/")
    if (
        not identifier
        or "/" in identifier
        or any(character.isspace() for character in identifier)
    ):
        raise ValueError("Gemini batch name must have the batches/{id} form")
