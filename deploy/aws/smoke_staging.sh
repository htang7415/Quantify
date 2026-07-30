#!/usr/bin/env bash
# Authenticated, SigV4 staging smoke checks for the deployed AWS API Gateway.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_STAGING_SMOKE:-}" != "1" ]]; then
  echo "Refusing AWS staging smoke; set QUANTIFY_AUTHORIZE_AWS_STAGING_SMOKE=1." >&2
  exit 2
fi
for required in AWS_REGION STAGING_URL SMOKE_ROLE_ARN EXPECTED_IMAGE_DIGEST \
  EXPECTED_FIXTURE_MANIFEST_HASH; do
  : "${!required:?set $required}"
done
[[ "$EXPECTED_IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  echo "EXPECTED_IMAGE_DIGEST must be an sha256 digest." >&2
  exit 2
}
aws_bin="${AWS_BIN:-aws}"
command -v "$aws_bin" >/dev/null 2>&1 || {
  echo "aws is unavailable; set AWS_BIN to its executable path." >&2
  exit 2
}
exec python3 deploy/aws/smoke_staging.py
