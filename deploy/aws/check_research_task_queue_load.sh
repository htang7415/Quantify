#!/usr/bin/env bash
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_RESEARCH_TASK_QUEUE_LOAD_CHECK:-}" != "1" ]]; then
  echo "Set QUANTIFY_AUTHORIZE_RESEARCH_TASK_QUEUE_LOAD_CHECK=1 to run the read-only research-task queue load check." >&2
  exit 2
fi

exec python3 "$(dirname "$0")/check_research_task_queue_load.py" "$@"
