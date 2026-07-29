"""Minimal Gemini Batch adapter for the model-visible prompting-parity path."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Protocol
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


class JsonTransport(Protocol):
    def post_json(self, *, url: str, headers: dict[str, str], body: dict) -> dict: ...


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


@dataclass(frozen=True, slots=True)
class GeminiBatchSubmission:
    batch_name: str
    request_ids: tuple[str, ...]
    estimated_total_cost_usd: float


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
