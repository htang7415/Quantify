"""Compile two completed parity trials into a repeated-run stability artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .parity import load_prompting_parity_artifact
from .stability import (
    evaluate_repeated_run_stability,
    repeated_run_stability_as_dict,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score two frozen parity trials for extraction stability."
    )
    parser.add_argument("--first-trial", type=Path, required=True)
    parser.add_argument("--second-trial", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    stability = evaluate_repeated_run_stability(
        first_trial=load_prompting_parity_artifact(args.first_trial),
        second_trial=load_prompting_parity_artifact(args.second_trial),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(repeated_run_stability_as_dict(stability=stability), sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "quantify_mechanical_verified_defeated_flips": (
                    stability.quantify.mechanical_verified_defeated_flips
                ),
            }
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
