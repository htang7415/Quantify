#!/usr/bin/env bash
# Read-only validation for the intentionally inactive private task pilot.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_CHECK:-}" != "1" ]]; then
  echo "Refusing research-task pilot check; set QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_CHECK=1." >&2
  exit 2
fi

exec python3 deploy/aws/check_research_task_pilot.py "$@"
