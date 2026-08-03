#!/usr/bin/env bash
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_RESEARCH_TASK_QUEUE_LOAD_CHECK:-}" != "1" ]]; then
  echo "Set QUANTIFY_AUTHORIZE_RESEARCH_TASK_QUEUE_LOAD_CHECK=1 to run the read-only research-task queue load check." >&2
  exit 2
fi

repository_root="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="$repository_root${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${QUANTIFY_PYTHON_BIN:-$repository_root/.venv/bin/python}"
[[ -x "$python_bin" ]] || python_bin="python3"
exec "$python_bin" "$repository_root/deploy/aws/check_research_task_queue_load.py" "$@"
