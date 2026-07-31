#!/usr/bin/env bash
# Offline control-plane action. It can never run from the worker role.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_RESEARCH_TASK_POLICY_PUBLISH:-}" != "1" ]]; then
  echo "Refusing research-task policy publication; set QUANTIFY_AUTHORIZE_RESEARCH_TASK_POLICY_PUBLISH=1." >&2
  exit 2
fi

repository_root="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="$repository_root${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${QUANTIFY_PYTHON_BIN:-$repository_root/.venv/bin/python}"
[[ -x "$python_bin" ]] || python_bin="python3"
exec "$python_bin" "$repository_root/deploy/aws/publish_research_task_policy.py" "$@"
