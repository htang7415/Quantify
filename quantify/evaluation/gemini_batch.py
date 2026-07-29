"""Minimal Gemini Batch adapter for the model-visible prompting-parity path."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from quantify.engine import ClaimVerdict

from .model_profiles import (
    EvaluationModelProfile,
    estimate_evaluation_cost,
    require_cost_within_budget,
)
from .parity_worklist import PromptingParityWorklist


_OUTCOMES = [*(item.value for item in ClaimVerdict), "unclassified"]
_BATCH_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchGenerateContent"
_BATCH_RESOURCE_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/{batch_name}"
_SUCCEEDED_STATES = {"BATCH_STATE_SUCCEEDED", "JOB_STATE_SUCCEEDED"}


class JsonTransport(Protocol):
    def post_json(self, *, url: str, headers: dict[str, str], body: dict) -> dict: ...

    def get_json(self, *, url: str, headers: dict[str, str]) -> dict: ...


class UrllibJsonTransport:
    """Production transport; the API key stays in an HTTP header, never the URL."""

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
                f"Gemini Batch request failed with HTTP {error.code}: {detail}"
            ) from error

    def get_json(self, *, url: str, headers: dict[str, str]) -> dict:
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS host
                return json.loads(response.read())
        except HTTPError as error:
            detail = error.read().decode(errors="replace")[:1000]
            raise RuntimeError(
                f"Gemini Batch status request failed with HTTP {error.code}: {detail}"
            ) from error


@dataclass(frozen=True, slots=True)
class GeminiBatchSubmission:
    batch_name: str
    request_ids: tuple[str, ...]
    estimated_total_cost_usd: float


@dataclass(frozen=True, slots=True)
class GeminiBatchStatus:
    """Provider status without provider output or private evaluation labels."""

    batch_name: str
    state: str
    done: bool


@dataclass(frozen=True, slots=True)
class GeminiPromptOnlyOutcomes:
    """Completed, schema-validated opaque prompt-only outputs."""

    batch_name: str
    model: str
    temperature: float
    prompt_hash: str
    outcomes: tuple[tuple[str, str], ...]


class GeminiBatchClient:
    """Submit one cost-preflighted inline Gemini Batch job without persisting secrets."""

    def __init__(
        self,
        *,
        api_key: str,
        transport: JsonTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required")
        self._api_key = api_key
        self._transport = transport or UrllibJsonTransport()

    def submit_prompt_only(
        self,
        *,
        profile: EvaluationModelProfile,
        worklist: PromptingParityWorklist,
    ) -> GeminiBatchSubmission:
        """Submit the 30 safe report-only classifications as one inline Batch job."""

        estimate = estimate_evaluation_cost(
            profile=profile, case_count=len(worklist.items), paths_per_case=1
        )
        require_cost_within_budget(estimate=estimate)
        requests = [
            {
                "request": _generate_content_request(
                    report_text=item.report_text, profile=profile
                ),
                "metadata": {"key": item.request_id},
            }
            for item in worklist.items
        ]
        body = {
            "batch": {
                "display_name": "quantify-prompt-only-parity-v1",
                "input_config": {"requests": {"requests": requests}},
            }
        }
        response = self._transport.post_json(
            url=_BATCH_ENDPOINT.format(model=profile.model),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_key,
            },
            body=body,
        )
        batch_name = response.get("name")
        if not isinstance(batch_name, str) or not batch_name:
            raise ValueError("Gemini Batch response did not include a batch name")
        return GeminiBatchSubmission(
            batch_name=batch_name,
            request_ids=tuple(item.request_id for item in worklist.items),
            estimated_total_cost_usd=estimate.total_cost_usd,
        )

    def get_status(self, *, batch_name: str) -> GeminiBatchStatus:
        """Read one known batch resource without accepting a user-controlled URL."""

        _validate_batch_name(batch_name)
        payload = self._transport.get_json(
            url=_BATCH_RESOURCE_ENDPOINT.format(batch_name=batch_name),
            headers={"x-goog-api-key": self._api_key},
        )
        state = _batch_state(payload)
        done = payload.get("done")
        if not isinstance(done, bool):
            done = state in _SUCCEEDED_STATES or state.endswith(
                ("FAILED", "CANCELLED", "EXPIRED")
            )
        return GeminiBatchStatus(batch_name=batch_name, state=state, done=done)

    def collect_prompt_only_outcomes(
        self,
        *,
        batch_name: str,
        profile: EvaluationModelProfile,
        request_ids: tuple[str, ...],
    ) -> GeminiPromptOnlyOutcomes:
        """Accept only a successful inline batch with every expected JSON result.

        This does not join evaluator-only reference data.  Its result is safe to
        persist as the external prompt-only outcome artifact.
        """

        _validate_batch_name(batch_name)
        payload = self._transport.get_json(
            url=_BATCH_RESOURCE_ENDPOINT.format(batch_name=batch_name),
            headers={"x-goog-api-key": self._api_key},
        )
        state = _batch_state(payload)
        if state not in _SUCCEEDED_STATES:
            raise ValueError(f"Gemini batch has not succeeded: {state}")
        outcomes = _parse_inline_outcomes(payload=payload, request_ids=request_ids)
        return GeminiPromptOnlyOutcomes(
            batch_name=batch_name,
            model=profile.model,
            temperature=profile.temperature,
            prompt_hash=prompt_only_prompt_hash(profile=profile),
            outcomes=outcomes,
        )


def _generate_content_request(
    *, report_text: str, profile: EvaluationModelProfile
) -> dict:
    return {
        "system_instruction": {
            "parts": [
                {
                    "text": (
                        "You are a conservative financial-claim classifier. "
                        "Return one outcome only. With report text alone, do not "
                        "invent evidence or infer SEC facts. Use unclassified when "
                        "the report does not itself establish a closed factual verdict."
                    )
                }
            ]
        },
        "contents": [{"role": "user", "parts": [{"text": report_text}]}],
        "generation_config": {
            "temperature": profile.temperature,
            "max_output_tokens": profile.max_output_tokens_per_request,
            "response_mime_type": "application/json",
            "response_schema": {
                "type": "OBJECT",
                "properties": {
                    "outcome": {"type": "STRING", "enum": _OUTCOMES}
                },
                "required": ["outcome"],
            },
        },
    }


def prompt_only_prompt_hash(*, profile: EvaluationModelProfile) -> str:
    """Hash the fixed model-visible prompt contract, excluding report text."""

    template = _generate_content_request(
        report_text="<frozen-report-text>", profile=profile
    )
    canonical = json.dumps(template, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode()).hexdigest()


def prompt_only_outcome_artifact_as_dict(*, outcomes: GeminiPromptOnlyOutcomes) -> dict:
    """Render the opaque artifact consumed by the parity compiler."""

    return {
        "artifact_version": "1.0.0",
        "path": "prompt_only",
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


def _validate_batch_name(batch_name: str) -> None:
    if not isinstance(batch_name, str) or not batch_name.startswith("batches/"):
        raise ValueError("Gemini batch name must have the batches/{id} form")
    identifier = batch_name.removeprefix("batches/")
    if (
        not identifier
        or "/" in identifier
        or any(character.isspace() for character in identifier)
    ):
        raise ValueError("Gemini batch name must have the batches/{id} form")


def _batch_state(payload: dict) -> str:
    if not isinstance(payload, dict):
        raise ValueError("Gemini batch response must be an object")
    metadata = payload.get("metadata")
    state = metadata.get("state") if isinstance(metadata, dict) else payload.get("state")
    if not isinstance(state, str) or not state:
        raise ValueError("Gemini batch response does not include a state")
    return state


def _parse_inline_outcomes(
    *, payload: dict, request_ids: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    if len(request_ids) != 30 or len(set(request_ids)) != len(request_ids):
        raise ValueError("Gemini prompt-only batch requires exactly 30 unique request IDs")
    response = payload.get("response")
    if not isinstance(response, dict):
        response = payload.get("output")
    if not isinstance(response, dict):
        raise ValueError("successful Gemini batch does not include inline results")
    inline = response.get("inlinedResponses")
    if isinstance(inline, dict):
        inline = inline.get("inlinedResponses")
    if not isinstance(inline, list) or len(inline) != len(request_ids):
        raise ValueError("Gemini batch must return one inline result per request")

    parsed: list[tuple[str, str]] = []
    for expected_request_id, item in zip(request_ids, inline, strict=True):
        if not isinstance(item, dict):
            raise ValueError("Gemini inline result must be an object")
        metadata = item.get("metadata")
        request_id = metadata.get("key") if isinstance(metadata, dict) else None
        if request_id != expected_request_id:
            raise ValueError("Gemini inline result key does not match the submitted order")
        if item.get("error") is not None:
            raise ValueError("Gemini batch contains a failed inline request")
        text = _response_text(item.get("response"))
        try:
            result = json.loads(text)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("Gemini outcome is not valid JSON") from error
        outcome = (
            result.get("outcome")
            if isinstance(result, dict) and set(result) == {"outcome"}
            else None
        )
        if not isinstance(outcome, str) or outcome not in _OUTCOMES:
            raise ValueError("Gemini outcome is not a supported closed verdict")
        parsed.append((request_id, outcome))
    return tuple(parsed)


def _response_text(response: object) -> str:
    if not isinstance(response, dict):
        raise ValueError("Gemini inline result does not include a response")
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise ValueError("Gemini inline result must include exactly one candidate")
    candidate = candidates[0]
    content = candidate.get("content") if isinstance(candidate, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list) or not parts:
        raise ValueError("Gemini inline result does not include text content")
    texts = [
        part.get("text")
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    if len(texts) != 1:
        raise ValueError("Gemini inline result must include exactly one text part")
    return texts[0]
