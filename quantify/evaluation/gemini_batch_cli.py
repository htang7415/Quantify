"""Credential-safe CLI for scheduled Gemini prompting-parity execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .campaign import (
    campaign_hash,
    load_scheduled_evaluation_campaign,
    record_campaign_collection,
    record_campaign_submission,
    require_campaign_collection,
    require_campaign_matches_profile,
    reserve_campaign_submission,
)
from .corpus import load_frozen_case_set
from .gemini_batch import GeminiBatchClient, prompt_only_outcome_artifact_as_dict
from .gemini_quantify_batch import (
    GeminiQuantifyBatchClient,
    build_quantify_parity_worklist,
    quantify_outcome_artifact_as_dict,
)
from .model_profiles import load_evaluation_model_profile
from .parity_worklist import build_prompting_parity_worklist
from quantify.harness.credentials import CredentialUnavailableError, load_gemini_api_key


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Submit or collect an opaque Gemini prompting-parity path."
    )
    parser.add_argument(
        "action",
        choices=(
            "submit-prompt-only",
            "collect-prompt-only",
            "submit-quantify",
            "collect-quantify",
        ),
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--mechanical-cases", type=Path, required=True)
    parser.add_argument("--judgment-cases", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-name")
    parser.add_argument("--campaign", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--trial", type=int)
    parser.add_argument("--api-key-env", default="GEMINI_API_KEY")
    args = parser.parse_args(argv)

    try:
        api_key = load_gemini_api_key(environment_variable=args.api_key_env)
    except CredentialUnavailableError as error:
        parser.error(str(error))
    if args.action.startswith("collect-") and not args.batch_name:
        parser.error("--batch-name is required for collection")
    if args.action.startswith("submit-") and args.batch_name:
        parser.error("--batch-name is only valid for collection")
    if (
        args.campaign is None or args.ledger is None or args.trial is None
    ):
        parser.error("scheduled actions require --campaign, --ledger, and --trial")

    profile = load_evaluation_model_profile(path=args.profile)
    mechanical = load_frozen_case_set(
        path=args.mechanical_cases, snapshot_root=args.snapshot_root
    )
    judgment = load_frozen_case_set(
        path=args.judgment_cases, snapshot_root=args.snapshot_root
    )

    campaign = load_scheduled_evaluation_campaign(path=args.campaign)
    require_campaign_matches_profile(campaign=campaign, profile=profile)

    if args.action == "submit-prompt-only":
        worklist = build_prompting_parity_worklist(
            mechanical_cases=mechanical, judgment_cases=judgment
        )
        reserve_campaign_submission(
            campaign=campaign,
            ledger_path=args.ledger,
            trial=args.trial,
            path="prompt_only",
        )
        submission = GeminiBatchClient(api_key=api_key).submit_prompt_only(
            profile=profile, worklist=worklist
        )
        payload = {
            "artifact_version": "1.0.0",
            "path": "prompt_only",
            "batch_name": submission.batch_name,
            "request_ids": list(submission.request_ids),
            "model": profile.model,
            "temperature": profile.temperature,
            "estimated_total_cost_usd": submission.estimated_total_cost_usd,
            "campaign_hash": campaign_hash(campaign=campaign),
            "trial": args.trial,
        }
        record_campaign_submission(
            campaign=campaign,
            ledger_path=args.ledger,
            trial=args.trial,
            path="prompt_only",
            batch_name=submission.batch_name,
        )
    elif args.action == "collect-prompt-only":
        worklist = build_prompting_parity_worklist(
            mechanical_cases=mechanical, judgment_cases=judgment
        )
        require_campaign_collection(
            campaign=campaign,
            ledger_path=args.ledger,
            trial=args.trial,
            path="prompt_only",
            batch_name=args.batch_name,
        )
        outcomes = GeminiBatchClient(api_key=api_key).collect_prompt_only_outcomes(
            batch_name=args.batch_name,
            profile=profile,
            request_ids=tuple(item.request_id for item in worklist.items),
        )
        payload = prompt_only_outcome_artifact_as_dict(outcomes=outcomes)
        payload["campaign_hash"] = campaign_hash(campaign=campaign)
        payload["trial"] = args.trial
        record_campaign_collection(
            campaign=campaign,
            ledger_path=args.ledger,
            trial=args.trial,
            path="prompt_only",
            batch_name=args.batch_name,
        )
    elif args.action == "submit-quantify":
        worklist = build_quantify_parity_worklist(
            mechanical_cases=mechanical, judgment_cases=judgment
        )
        reserve_campaign_submission(
            campaign=campaign,
            ledger_path=args.ledger,
            trial=args.trial,
            path="quantify",
        )
        submission = GeminiQuantifyBatchClient(api_key=api_key).submit(
            profile=profile, worklist=worklist
        )
        payload = {
            "artifact_version": "1.0.0",
            "path": "quantify",
            "batch_name": submission.batch_name,
            "request_ids": list(submission.request_ids),
            "model": profile.model,
            "temperature": profile.temperature,
            "estimated_total_cost_usd": submission.estimated_total_cost_usd,
            "campaign_hash": campaign_hash(campaign=campaign),
            "trial": args.trial,
        }
        record_campaign_submission(
            campaign=campaign,
            ledger_path=args.ledger,
            trial=args.trial,
            path="quantify",
            batch_name=submission.batch_name,
        )
    else:
        worklist = build_quantify_parity_worklist(
            mechanical_cases=mechanical, judgment_cases=judgment
        )
        require_campaign_collection(
            campaign=campaign,
            ledger_path=args.ledger,
            trial=args.trial,
            path="quantify",
            batch_name=args.batch_name,
        )
        outcomes = GeminiQuantifyBatchClient(api_key=api_key).collect(
            batch_name=args.batch_name,
            profile=profile,
            worklist=worklist,
        )
        payload = quantify_outcome_artifact_as_dict(outcomes=outcomes)
        payload["campaign_hash"] = campaign_hash(campaign=campaign)
        payload["trial"] = args.trial
        record_campaign_collection(
            campaign=campaign,
            ledger_path=args.ledger,
            trial=args.trial,
            path="quantify",
            batch_name=args.batch_name,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "path": payload["path"]}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
