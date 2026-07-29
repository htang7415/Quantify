"""Compile final interactive-runtime readiness evidence from private artifacts."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .interactive import compile_interactive_runtime_artifact, load_interactive_repeated_run_stability, load_interactive_runtime_trial

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile interactive readiness evidence.")
    parser.add_argument("--trial", type=Path, required=True)
    parser.add_argument("--stability", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = compile_interactive_runtime_artifact(
            trial=load_interactive_runtime_trial(path=args.trial),
            stability=load_interactive_repeated_run_stability(path=args.stability),
        )
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
