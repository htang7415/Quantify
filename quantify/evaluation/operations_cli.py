"""Write readiness measurements from a completed scheduled-evaluation ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .campaign import load_campaign_ledger, load_scheduled_evaluation_campaign
from .operations import (
    compile_scheduled_operational_measurements,
    scheduled_operational_measurements_as_dict,
)
from .stability import load_repeated_run_stability


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile completed campaign timing/cost into readiness input."
    )
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--stability-artifact", type=Path, required=True)
    parser.add_argument("--sec-insufficiency-count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    campaign = load_scheduled_evaluation_campaign(path=args.campaign)
    measurements = compile_scheduled_operational_measurements(
        campaign=campaign,
        ledger=load_campaign_ledger(campaign=campaign, ledger_path=args.ledger),
        stability=load_repeated_run_stability(path=args.stability_artifact),
        sec_insufficiency_count=args.sec_insufficiency_count,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            scheduled_operational_measurements_as_dict(measurements=measurements),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "campaign_hash": measurements.campaign_hash}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
