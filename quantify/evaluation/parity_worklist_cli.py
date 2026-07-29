"""Emit model-safe prompting-parity inputs and keep reference labels separate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .corpus import load_frozen_case_set
from .parity_worklist import build_prompting_parity_worklist


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a model-safe prompting-parity worklist."
    )
    parser.add_argument("--mechanical-cases", type=Path, required=True)
    parser.add_argument("--judgment-cases", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument(
        "--reference-mapping-output",
        type=Path,
        required=True,
        help="private evaluator-side mapping; do not send this file to the model",
    )
    args = parser.parse_args(argv)
    worklist = build_prompting_parity_worklist(
        mechanical_cases=load_frozen_case_set(
            path=args.mechanical_cases, snapshot_root=args.snapshot_root
        ),
        judgment_cases=load_frozen_case_set(
            path=args.judgment_cases, snapshot_root=args.snapshot_root
        ),
    )
    args.reference_mapping_output.write_text(
        json.dumps(worklist.reference_mapping(), sort_keys=True)
    )
    print(json.dumps(worklist.model_input(), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
