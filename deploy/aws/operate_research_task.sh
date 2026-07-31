#!/usr/bin/env bash
# IAM-only lifecycle controls. It cannot submit research work.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_RESEARCH_TASK_OPERATION:-}" != "1" ]]; then
  echo "Refusing private research-task operation; set QUANTIFY_AUTHORIZE_RESEARCH_TASK_OPERATION=1." >&2
  exit 2
fi

repository_root="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="$repository_root${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${QUANTIFY_PYTHON_BIN:-$repository_root/.venv/bin/python}"
[[ -x "$python_bin" ]] || python_bin="python3"
exec "$python_bin" "$repository_root/deploy/aws/operate_research_task.py" "$@"
