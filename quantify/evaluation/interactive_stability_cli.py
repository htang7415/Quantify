"""Compile two no-secret normal-prompt trial artifacts into stability evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .interactive import (
    evaluate_interactive_repeated_run_stability,
    interactive_repeated_run_stability_as_dict,
    load_interactive_runtime_trial,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile two normal interactive trials into stability evidence."
    )
    parser.add_argument("--first-trial", type=Path, required=True)
    parser.add_argument("--second-trial", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        stability = evaluate_interactive_repeated_run_stability(
            first_trial=load_interactive_runtime_trial(path=args.first_trial),
            second_trial=load_interactive_runtime_trial(path=args.second_trial),
        )
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            interactive_repeated_run_stability_as_dict(stability=stability),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
