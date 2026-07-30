#!/usr/bin/env bash
# Exercise the bounded anonymous trial through CloudFront after explicit approval.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_ANONYMOUS_TRIAL_SMOKE:-}" != "1" ]]; then
  echo "Refusing anonymous-trial smoke; set QUANTIFY_AUTHORIZE_AWS_ANONYMOUS_TRIAL_SMOKE=1." >&2
  exit 2
fi
: "${WEB_PREVIEW_URL:?set WEB_PREVIEW_URL}"
exec python3 deploy/aws/smoke_anonymous_trial.py
