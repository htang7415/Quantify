#!/usr/bin/env bash
# Provision the private, non-consuming research-task pilot foundation.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_DEPLOY:-}" != "1" ]]; then
  echo "Refusing research-task pilot deploy; set QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_DEPLOY=1." >&2
  exit 2
fi
for required in AWS_REGION AWS_STACK_NAME IMAGE_URI IMAGE_DIGEST AUDIT_BUCKET_NAME GEMINI_SECRET_ARN GEMINI_SECRET_VERSION_ID; do
  : "${!required:?set $required}"
done
[[ "$AWS_REGION" == "us-east-2" ]] || {
  echo "AWS_REGION must be us-east-2." >&2
  exit 2
}
[[ "$AWS_STACK_NAME" =~ ^[A-Za-z][A-Za-z0-9-]{0,127}$ ]] || {
  echo "AWS_STACK_NAME is invalid." >&2
  exit 2
}
[[ "$IMAGE_URI" =~ @sha256:[0-9a-f]{64}$ ]] || {
  echo "IMAGE_URI must be an immutable @sha256 reference." >&2
  exit 2
}
[[ "$IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ && "${IMAGE_URI##*@}" == "$IMAGE_DIGEST" ]] || {
  echo "IMAGE_URI and IMAGE_DIGEST must identify one matching immutable digest." >&2
  exit 2
}
[[ "$AUDIT_BUCKET_NAME" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]] || {
  echo "AUDIT_BUCKET_NAME is invalid." >&2
  exit 2
}
aws_bin="${AWS_BIN:-aws}"
command -v "$aws_bin" >/dev/null 2>&1 || {
  echo "aws is unavailable; set AWS_BIN to its executable path." >&2
  exit 2
}

"$aws_bin" cloudformation deploy \
  --template-file deploy/aws/research_task_pilot_template.yaml \
  --stack-name="$AWS_STACK_NAME" --region="$AWS_REGION" \
  --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
  --parameter-overrides "ImageUri=$IMAGE_URI" "ImageDigest=$IMAGE_DIGEST" "AuditBucketName=$AUDIT_BUCKET_NAME" \
    "GeminiSecretArn=$GEMINI_SECRET_ARN" "GeminiSecretVersionId=$GEMINI_SECRET_VERSION_ID" \
    "WorkerReservedConcurrency=0" "EnableTaskConsumption=false" "TaskMaximumConcurrency=1"
