#!/usr/bin/env bash
# Create the private ECR repository and pinned Gemini secret for AWS staging.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_BOOTSTRAP:-}" != "1" ]]; then
  echo "Refusing AWS bootstrap; set QUANTIFY_AUTHORIZE_AWS_BOOTSTRAP=1." >&2
  exit 2
fi
for required in AWS_REGION ECR_REPOSITORY GEMINI_SECRET_NAME GEMINI_SECRET_FILE; do
  : "${!required:?set $required}"
done
[[ -s "$GEMINI_SECRET_FILE" ]] || {
  echo "GEMINI_SECRET_FILE must name a non-empty private file." >&2
  exit 2
}
aws_bin="${AWS_BIN:-aws}"
command -v "$aws_bin" >/dev/null 2>&1 || {
  echo "aws is unavailable; set AWS_BIN to its executable path." >&2
  exit 2
}

if ! "$aws_bin" ecr describe-repositories --region="$AWS_REGION" \
  --repository-names="$ECR_REPOSITORY" >/dev/null 2>&1; then
  "$aws_bin" ecr create-repository --region="$AWS_REGION" \
    --repository-name="$ECR_REPOSITORY" --image-tag-mutability=IMMUTABLE \
    --image-scanning-configuration scanOnPush=true >/dev/null
fi
if ! "$aws_bin" secretsmanager describe-secret --region="$AWS_REGION" \
  --secret-id="$GEMINI_SECRET_NAME" >/dev/null 2>&1; then
  "$aws_bin" secretsmanager create-secret --region="$AWS_REGION" \
    --name="$GEMINI_SECRET_NAME" --secret-string="file://$GEMINI_SECRET_FILE" >/dev/null
fi

secret_arn="$("$aws_bin" secretsmanager describe-secret --region="$AWS_REGION" \
  --secret-id="$GEMINI_SECRET_NAME" --query ARN --output text)"
version_id="$("$aws_bin" secretsmanager list-secret-version-ids --region="$AWS_REGION" \
  --secret-id="$secret_arn" --include-deprecated \
  --query "Versions[?contains(VersionStages, 'AWSCURRENT')].VersionId | [0]" --output text)"
[[ "$version_id" != "None" && -n "$version_id" ]] || {
  echo "The Gemini secret has no AWSCURRENT version." >&2
  exit 1
}
printf 'GEMINI_SECRET_ARN=%s\nGEMINI_SECRET_VERSION_ID=%s\n' "$secret_arn" "$version_id"
