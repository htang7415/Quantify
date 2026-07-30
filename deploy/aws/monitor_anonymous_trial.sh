#!/usr/bin/env bash
# Read anonymous-trial usage without accessing report text or private credentials.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_ANONYMOUS_TRIAL_MONITOR:-}" != "1" ]]; then
  echo "Refusing anonymous-trial monitor; set QUANTIFY_AUTHORIZE_AWS_ANONYMOUS_TRIAL_MONITOR=1." >&2
  exit 2
fi
for required in AWS_REGION PUBLIC_AGENT_STACK_NAME; do
  : "${!required:?set $required}"
done
exec python3 deploy/aws/monitor_anonymous_trial.py
