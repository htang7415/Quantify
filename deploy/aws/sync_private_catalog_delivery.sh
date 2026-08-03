#!/usr/bin/env bash
set -euo pipefail

[[ "${QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_DELIVERY_SYNC:-}" == "1" ]] || {
  echo "Refusing private catalog delivery sync; set QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_DELIVERY_SYNC=1." >&2; exit 2;
}
for required in CATALOG_SOURCE_BUCKET CATALOG_DELIVERY_BUCKET CATALOG_DELIVERY_KMS_KEY_ARN; do : "${!required:?set $required}"; done
[[ "$CATALOG_SOURCE_BUCKET" != "$CATALOG_DELIVERY_BUCKET" ]] || {
  echo "Refusing catalog sync: source and delivery buckets must differ." >&2; exit 2;
}
# Do not delete destination versions: a stage copy is additive and reversible.
aws s3 sync "s3://$CATALOG_SOURCE_BUCKET/release-catalogs/v1/" "s3://$CATALOG_DELIVERY_BUCKET/release-catalogs/v1/" \
  --sse aws:kms --sse-kms-key-id "$CATALOG_DELIVERY_KMS_KEY_ARN" --only-show-errors
