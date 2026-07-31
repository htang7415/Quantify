#!/usr/bin/env bash
# Explicitly enable the bounded private worker; no public route is created.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_ACTIVATION:-}" != "1" ]]; then
  echo "Refusing research-task pilot activation; set QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_ACTIVATION=1." >&2
  exit 2
fi

repository_root="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="$repository_root${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${QUANTIFY_PYTHON_BIN:-$repository_root/.venv/bin/python}"
[[ -x "$python_bin" ]] || python_bin="python3"
exec "$python_bin" "$repository_root/deploy/aws/activate_research_task_pilot.py" "$@"
