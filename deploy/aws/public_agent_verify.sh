#!/usr/bin/env bash
# Invoke Quantify's public agent API with a scoped token from macOS Keychain.

set -euo pipefail

env_file="${QUANTIFY_PUBLIC_AGENT_ENV_FILE:-.quantify-private/aws-production.env}"
[[ -r "$env_file" ]] || { echo "private production environment file is unreadable." >&2; exit 2; }
set -a
# shellcheck source=/dev/null
source "$env_file"
set +a

for required in PUBLIC_AGENT_URL OAUTH_TOKEN_ENDPOINT COGNITO_MACHINE_CLIENT_ID OAUTH_VERIFY_SCOPE; do
  [[ -n "${!required:-}" ]] || { echo "private environment must set $required." >&2; exit 2; }
done

exec python3 deploy/aws/public_agent_verify.py "$@"
