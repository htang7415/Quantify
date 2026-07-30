#!/usr/bin/env bash
# Deploy a digest-pinned, IAM-authenticated AWS staging stack.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_STAGING_DEPLOY:-}" != "1" ]]; then
  echo "Refusing AWS staging deploy; set QUANTIFY_AUTHORIZE_AWS_STAGING_DEPLOY=1." >&2
  exit 2
fi
for required in AWS_REGION AWS_STACK_NAME IMAGE_URI IMAGE_DIGEST GEMINI_SECRET_ARN \
  GEMINI_SECRET_VERSION_ID SMOKE_PRINCIPAL_ARN RESERVED_CONCURRENCY; do
  : "${!required:?set $required}"
done
[[ "$IMAGE_URI" =~ @sha256:[0-9a-f]{64}$ ]] || {
  echo "IMAGE_URI must be an immutable @sha256 reference." >&2
  exit 2
}
[[ "$IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  echo "IMAGE_DIGEST must be an sha256 digest." >&2
  exit 2
}
[[ "${IMAGE_URI##*@}" == "$IMAGE_DIGEST" ]] || {
  echo "IMAGE_URI and IMAGE_DIGEST must identify the same image." >&2
  exit 2
}
[[ "$GEMINI_SECRET_VERSION_ID" =~ ^[A-Za-z0-9-]{32,64}$ ]] || {
  echo "GEMINI_SECRET_VERSION_ID must be an immutable Secrets Manager version ID." >&2
  exit 2
}
[[ "$RESERVED_CONCURRENCY" =~ ^(0|[1-9][0-9]*)$ && "$RESERVED_CONCURRENCY" -le 900 ]] || {
  echo "RESERVED_CONCURRENCY must be a whole number from 0 through 900." >&2
  exit 2
}
aws_bin="${AWS_BIN:-aws}"
command -v "$aws_bin" >/dev/null 2>&1 || {
  echo "aws is unavailable; set AWS_BIN to its executable path." >&2
  exit 2
}

"$aws_bin" cloudformation deploy --template-file deploy/aws/template.yaml \
  --stack-name="$AWS_STACK_NAME" --region="$AWS_REGION" \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND --no-fail-on-empty-changeset \
  --parameter-overrides \
    "ImageUri=$IMAGE_URI" "ImageDigest=$IMAGE_DIGEST" \
    "GeminiSecretArn=$GEMINI_SECRET_ARN" \
    "GeminiSecretVersionId=$GEMINI_SECRET_VERSION_ID" \
    "SmokePrincipalArn=$SMOKE_PRINCIPAL_ARN" \
    "ReservedConcurrency=$RESERVED_CONCURRENCY"
