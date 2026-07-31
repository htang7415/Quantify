#!/usr/bin/env bash
# Read-only factory-to-control-plane handoff validation.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_RESEARCH_TASK_BUNDLE_CHECK:-}" != "1" ]]; then
  echo "Refusing research-task bundle validation; set QUANTIFY_AUTHORIZE_RESEARCH_TASK_BUNDLE_CHECK=1." >&2
  exit 2
fi

repository_root="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="$repository_root${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${QUANTIFY_PYTHON_BIN:-$repository_root/.venv/bin/python}"
[[ -x "$python_bin" ]] || python_bin="python3"
exec "$python_bin" "$repository_root/deploy/aws/validate_research_task_bundle.py" "$@"
