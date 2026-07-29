"""Write an explicit no-secret campaign authorization artifact for Gemini runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .campaign import (
    plan_scheduled_evaluation_campaign,
    scheduled_evaluation_campaign_as_dict,
)
from .model_profiles import load_evaluation_model_profile


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan the complete cost envelope for a repeated parity run."
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--max-total-cost-usd", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    campaign = plan_scheduled_evaluation_campaign(
        profile=load_evaluation_model_profile(path=args.profile),
        trial_count=args.trials,
        max_total_cost_usd=args.max_total_cost_usd,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(scheduled_evaluation_campaign_as_dict(campaign=campaign), sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "estimated_total_cost_usd": campaign.estimated_total_cost_usd}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
