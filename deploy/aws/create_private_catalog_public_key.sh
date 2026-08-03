#!/usr/bin/env bash
set -euo pipefail

[[ "${QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_KEY_CREATE:-}" == "1" ]] || {
  echo "Refusing private catalog key creation; set QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_KEY_CREATE=1." >&2; exit 2;
}
for required in CATALOG_PUBLIC_KEY_FILE CATALOG_PUBLIC_KEY_NAME CATALOG_PUBLIC_KEY_CALLER_REFERENCE; do : "${!required:?set $required}"; done
[[ -r "$CATALOG_PUBLIC_KEY_FILE" ]] || { echo "CATALOG_PUBLIC_KEY_FILE is unreadable." >&2; exit 2; }
config_file="$(mktemp)"
trap 'rm -f "$config_file"' EXIT
jq -n --rawfile key "$CATALOG_PUBLIC_KEY_FILE" --arg caller "$CATALOG_PUBLIC_KEY_CALLER_REFERENCE" --arg name "$CATALOG_PUBLIC_KEY_NAME" '{CallerReference:$caller,Name:$name,EncodedKey:$key}' > "$config_file"
aws cloudfront create-public-key --public-key-config "file://$config_file" --query 'PublicKey.Id' --output text
