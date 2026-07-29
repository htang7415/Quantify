#!/usr/bin/env bash
# Authenticated smoke checks for an already-created, tagged private revision.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_STAGING_SMOKE:-}" != "1" ]]; then
  echo "Refusing to call staging; set QUANTIFY_AUTHORIZE_STAGING_SMOKE=1." >&2
  exit 2
fi
: "${STAGING_URL:?set STAGING_URL to the tagged revision URL}"
: "${EXPECTED_IMAGE_DIGEST:?set EXPECTED_IMAGE_DIGEST to the deployed sha256 digest}"
: "${EXPECTED_FIXTURE_MANIFEST_HASH:?set EXPECTED_FIXTURE_MANIFEST_HASH}"
gcloud_bin="${GCLOUD_BIN:-gcloud}"
if ! command -v "$gcloud_bin" >/dev/null 2>&1; then
  echo "gcloud is unavailable; set GCLOUD_BIN to its executable path." >&2
  exit 2
fi

token="$("$gcloud_bin" auth print-identity-token --audiences="$STAGING_URL")"
headers=(-H "Authorization: Bearer $token" -H "Content-Type: application/json")
health="$(curl --fail-with-body --silent --show-error "${headers[@]}" "$STAGING_URL/healthz")"
verify="$(curl --fail-with-body --silent --show-error "${headers[@]}" \
  --data '{"analysis":"Microsoft revenue increased from fiscal 2023 to fiscal 2024.","as_of_date":"2024-07-30","forms":["10-K"]}' \
  "$STAGING_URL/v1/companies/789019/verify")"

python3 -c 'import json, sys; assert json.load(sys.stdin) == {"status": "ok"}' <<<"$health"
printf '%s' "$verify" | python3 -c '
import json
import os
import sys

payload = json.load(sys.stdin)
audit = payload["audit_manifest"]
assert audit["deployment_image_digest"] == os.environ["EXPECTED_IMAGE_DIGEST"]
assert audit["evidence_fixture_manifest_hash"] == os.environ["EXPECTED_FIXTURE_MANIFEST_HASH"]
assert "claim_results" in payload and "verification_cache_hit" in payload
'

for internal_path in \
  "/v1/companies/789019/review" \
  "/v1/companies/789019/resolve" \
  "/v1/verify/batch"; do
  status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
    "${headers[@]}" --data '{}' "$STAGING_URL$internal_path")"
  [[ "$status" == "404" ]] || {
    echo "Internal route $internal_path is unexpectedly available ($status)." >&2
    exit 1
  }
done
