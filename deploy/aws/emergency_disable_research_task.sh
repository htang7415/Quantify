#!/usr/bin/env bash
# Offline emergency stop.  Recovery requires a new approved publication.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_RESEARCH_TASK_EMERGENCY_DISABLE:-}" != "1" ]]; then
  echo "Refusing research-task emergency disable; set QUANTIFY_AUTHORIZE_RESEARCH_TASK_EMERGENCY_DISABLE=1." >&2
  exit 2
fi

repository_root="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="$repository_root${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${QUANTIFY_PYTHON_BIN:-$repository_root/.venv/bin/python}"
[[ -x "$python_bin" ]] || python_bin="python3"
exec "$python_bin" "$repository_root/deploy/aws/emergency_disable_research_task.py" "$@"
