#!/usr/bin/env bash
# Read-only health gate for Quantify's controlled public beta.

set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_PRODUCTION_BETA_CHECK:-}" != "1" ]]; then
  echo "Refusing production-beta check; set QUANTIFY_AUTHORIZE_AWS_PRODUCTION_BETA_CHECK=1." >&2
  exit 2
fi

exec python3 deploy/aws/check_production_beta.py "$@"
