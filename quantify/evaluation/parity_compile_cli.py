"""Compile two provider outcome files into a validated prompting-parity artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .parity_compile import (
    compile_prompting_parity_artifact,
    load_model_outcome_artifact,
    prompting_parity_artifact_as_dict,
)
from .parity_worklist import load_prompting_parity_references


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile opaque model outcomes into a prompting-parity artifact."
    )
    parser.add_argument("--reference-mapping", type=Path, required=True)
    parser.add_argument("--prompt-only-outcomes", type=Path, required=True)
    parser.add_argument("--quantify-outcomes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    artifact = compile_prompting_parity_artifact(
        references=load_prompting_parity_references(path=args.reference_mapping),
        prompt_only=load_model_outcome_artifact(path=args.prompt_only_outcomes),
        quantify=load_model_outcome_artifact(path=args.quantify_outcomes),
    )
    args.output.write_text(
        json.dumps(prompting_parity_artifact_as_dict(artifact=artifact), sort_keys=True)
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
