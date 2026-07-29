"""Run an explicitly authorized interactive Gemini readiness measurement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from quantify.harness import GeminiExtractionConfig, GeminiStructuredExtractor
from quantify.harness.credentials import load_gemini_api_key

from .corpus import load_frozen_case_set
from .interactive import (
    InteractiveRuntimeAuthorization,
    interactive_runtime_artifact_as_dict,
    run_interactive_runtime_evaluation,
    validate_interactive_runtime_inputs,
)
from .stability import load_repeated_run_stability


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute one authorized 30-case interactive Quantify evaluation."
    )
    parser.add_argument("--mechanical-cases", type=Path, required=True)
    parser.add_argument("--judgment-cases", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--stability-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default="gemini-3.1-flash-lite")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--input-price-per-million-usd", type=float, required=True)
    parser.add_argument("--output-price-per-million-usd", type=float, required=True)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--request-timeout-seconds", type=float, default=4.0)
    parser.add_argument("--max-total-cost-usd", type=float, required=True)
    parser.add_argument("--max-request-cost-usd", type=float, required=True)
    execution = parser.add_mutually_exclusive_group(required=True)
    execution.add_argument(
        "--execute",
        action="store_true",
        help="acknowledge that this command makes standard, non-Batch provider requests",
    )
    execution.add_argument(
        "--preflight",
        action="store_true",
        help="validate the frozen corpus, authorization, and stability with no provider request",
    )
    args = parser.parse_args(argv)

    try:
        config = GeminiExtractionConfig(
            model=args.model,
            temperature=args.temperature,
            input_price_per_million_usd=args.input_price_per_million_usd,
            output_price_per_million_usd=args.output_price_per_million_usd,
            max_output_tokens=args.max_output_tokens,
            request_timeout_seconds=args.request_timeout_seconds,
        )
        authorization = InteractiveRuntimeAuthorization(
            authorization_version="1.0.0",
            provider="google",
            model=config.model,
            temperature=config.temperature,
            prompt_hash=config.prompt_hash,
            request_timeout_seconds=config.request_timeout_seconds,
            max_total_cost_usd=args.max_total_cost_usd,
            max_request_cost_usd=args.max_request_cost_usd,
        )
        mechanical_cases = load_frozen_case_set(
            path=args.mechanical_cases, snapshot_root=args.snapshot_root
        )
        judgment_cases = load_frozen_case_set(
            path=args.judgment_cases, snapshot_root=args.snapshot_root
        )
        stability = load_repeated_run_stability(path=args.stability_artifact)
        cases = validate_interactive_runtime_inputs(
            mechanical_cases=mechanical_cases,
            judgment_cases=judgment_cases,
            authorization=authorization,
            stability=stability,
        )
    except ValueError as error:
        parser.error(str(error))
    if args.preflight:
        print(
            json.dumps(
                {
                    "preflight": "ready_for_explicitly_authorized_execution",
                    "case_count": len(cases),
                    "model": config.model,
                    "prompt_hash": config.prompt_hash,
                    "max_total_cost_usd": authorization.max_total_cost_usd,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.output is None:
        parser.error("--output is required with --execute")
    try:
        measurement = run_interactive_runtime_evaluation(
            mechanical_cases=mechanical_cases,
            judgment_cases=judgment_cases,
            extractor=GeminiStructuredExtractor(
                api_key=load_gemini_api_key(), config=config
            ),
            authorization=authorization,
            stability=stability,
        )
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            interactive_runtime_artifact_as_dict(measurement=measurement),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - command-line entry point
    raise SystemExit(main())
