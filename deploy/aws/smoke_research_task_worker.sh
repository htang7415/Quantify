#!/usr/bin/env bash
# Temporary non-consuming worker bootstrap check with mandatory restoration.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_RESEARCH_TASK_WORKER_BOOTSTRAP_SMOKE:-}" != "1" ]]; then
  echo "Refusing worker bootstrap smoke; set QUANTIFY_AUTHORIZE_RESEARCH_TASK_WORKER_BOOTSTRAP_SMOKE=1." >&2
  exit 2
fi

repository_root="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="$repository_root${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${QUANTIFY_PYTHON_BIN:-$repository_root/.venv/bin/python}"
[[ -x "$python_bin" ]] || python_bin="python3"
exec "$python_bin" "$repository_root/deploy/aws/smoke_research_task_worker.py" "$@"
