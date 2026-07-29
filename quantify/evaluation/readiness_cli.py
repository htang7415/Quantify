"""Command-line boundary for a reproducible, offline Week 6 readiness run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .corpus import load_frozen_case_set
from .parity import load_prompting_parity_artifact
from .readiness import ReadinessDecision
from .readiness_run import (
    load_operational_measurements,
    readiness_run_as_dict,
    run_readiness_evaluation,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Quantify's frozen-corpus commercial readiness gate."
    )
    parser.add_argument("--mechanical-cases", type=Path, required=True)
    parser.add_argument("--judgment-cases", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--parity-artifact", type=Path, required=True)
    parser.add_argument("--operations-artifact", type=Path, required=True)
    parser.add_argument(
        "--fail-on-pause",
        action="store_true",
        help="return exit status 2 when the resulting decision is pause",
    )
    args = parser.parse_args(argv)
    run = run_readiness_evaluation(
        mechanical_cases=load_frozen_case_set(
            path=args.mechanical_cases, snapshot_root=args.snapshot_root
        ),
        judgment_cases=load_frozen_case_set(
            path=args.judgment_cases, snapshot_root=args.snapshot_root
        ),
        parity_artifact=load_prompting_parity_artifact(args.parity_artifact),
        operations=load_operational_measurements(path=args.operations_artifact),
    )
    print(json.dumps(readiness_run_as_dict(run=run), sort_keys=True))
    if args.fail_on_pause and run.assessment.decision is ReadinessDecision.PAUSE:
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
