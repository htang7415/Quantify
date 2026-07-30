#!/usr/bin/env bash
# Exercise the authenticated public agent endpoint only after explicit approval.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_SMOKE:-}" != "1" ]]; then
  echo "Refusing public-agent smoke; set QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_SMOKE=1." >&2
  exit 2
fi
for required in PUBLIC_AGENT_URL OAUTH_TOKEN_ENDPOINT COGNITO_MACHINE_CLIENT_ID \
  COGNITO_MACHINE_CLIENT_SECRET_FILE OAUTH_VERIFY_SCOPE; do
  : "${!required:?set $required}"
done
[[ -r "$COGNITO_MACHINE_CLIENT_SECRET_FILE" ]] || { echo "Cognito machine client secret source is unreadable." >&2; exit 2; }
exec python3 deploy/aws/smoke_public_agent.py
