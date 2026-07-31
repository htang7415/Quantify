#!/usr/bin/env bash
# Offline release-factory action; the worker never compiles or acquires evidence.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_RESEARCH_TASK_RELEASE_COMPILE:-}" != "1" ]]; then
  echo "Refusing research-task release compilation; set QUANTIFY_AUTHORIZE_RESEARCH_TASK_RELEASE_COMPILE=1." >&2
  exit 2
fi

repository_root="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="$repository_root${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${QUANTIFY_PYTHON_BIN:-$repository_root/.venv/bin/python}"
[[ -x "$python_bin" ]] || python_bin="python3"
exec "$python_bin" "$repository_root/deploy/aws/compile_research_task_release.py" "$@"
