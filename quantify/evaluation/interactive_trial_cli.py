"""Execute or preflight one explicitly authorized normal-prompt trial."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from quantify.harness import GeminiExtractionConfig, GeminiStructuredExtractor
from quantify.harness.credentials import load_gemini_api_key

from .corpus import load_frozen_case_set
from .interactive import (
    InteractiveRuntimeAuthorization,
    interactive_runtime_trial_as_dict,
    run_interactive_runtime_trial,
    validate_interactive_runtime_inputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute one authorized 30-case normal-prompt Gemini trial."
    )
    parser.add_argument("--mechanical-cases", type=Path, required=True)
    parser.add_argument("--judgment-cases", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default="gemini-3.1-flash-lite")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--input-price-per-million-usd", type=float, required=True)
    parser.add_argument("--output-price-per-million-usd", type=float, required=True)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--max-input-tokens", type=int, default=6144)
    parser.add_argument("--request-timeout-seconds", type=float, default=4.0)
    parser.add_argument("--max-total-cost-usd", type=float, required=True)
    parser.add_argument("--max-request-cost-usd", type=float, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = GeminiExtractionConfig(
            model=args.model, temperature=args.temperature,
            input_price_per_million_usd=args.input_price_per_million_usd,
            output_price_per_million_usd=args.output_price_per_million_usd,
            max_output_tokens=args.max_output_tokens,
            max_input_payload_bytes=args.max_input_tokens,
            request_timeout_seconds=args.request_timeout_seconds,
        )
        authorization = InteractiveRuntimeAuthorization(
            authorization_version="1.0.0", provider="google", model=config.model,
            temperature=config.temperature, prompt_hash=config.prompt_hash,
            request_timeout_seconds=config.request_timeout_seconds,
            max_total_cost_usd=args.max_total_cost_usd,
            max_request_cost_usd=args.max_request_cost_usd,
            max_input_tokens=args.max_input_tokens,
        )
        mechanical = load_frozen_case_set(
            path=args.mechanical_cases, snapshot_root=args.snapshot_root
        )
        judgment = load_frozen_case_set(
            path=args.judgment_cases, snapshot_root=args.snapshot_root
        )
        # Reuse the exact corpus validation without requiring an unrelated
        # Batch stability artifact for a first normal-prompt trial.
        if len((*mechanical, *judgment)) != 30:
            raise ValueError("normal-prompt trial requires exactly 30 cases")
    except ValueError as error:
        parser.error(str(error))
    if args.preflight:
        print(json.dumps({"preflight": "ready_for_explicitly_authorized_execution", "case_count": 30, "model": config.model, "prompt_hash": config.prompt_hash, "max_total_cost_usd": authorization.max_total_cost_usd}, sort_keys=True))
        return 0
    if args.output is None:
        parser.error("--output is required with --execute")
    trial = run_interactive_runtime_trial(
        mechanical_cases=mechanical, judgment_cases=judgment,
        extractor=GeminiStructuredExtractor(api_key=load_gemini_api_key(), config=config),
        authorization=authorization,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(interactive_runtime_trial_as_dict(trial=trial), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
