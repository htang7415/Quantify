#!/usr/bin/env bash
# Publish a tested browser build to the existing private Quantify preview only.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_WEB_PREVIEW_ASSET_DEPLOY:-}" != "1" ]]; then
  echo "Refusing web-preview asset deploy; set QUANTIFY_AUTHORIZE_AWS_WEB_PREVIEW_ASSET_DEPLOY=1." >&2
  exit 2
fi
for required in AWS_REGION WEB_PREVIEW_STACK_NAME COGNITO_DOMAIN_PREFIX OAUTH_RESOURCE_SERVER_IDENTIFIER; do
  : "${!required:?set $required}"
done
TRIAL_ENABLED="${TRIAL_ENABLED:-false}"
[[ "$TRIAL_ENABLED" == "false" || "$TRIAL_ENABLED" == "true" ]] || { echo "TRIAL_ENABLED must be true or false." >&2; exit 2; }

aws_bin="${AWS_BIN:-aws}"
command -v "$aws_bin" >/dev/null 2>&1 || { echo "aws is unavailable; set AWS_BIN." >&2; exit 2; }

preview_output() {
  "$aws_bin" cloudformation describe-stacks --stack-name "$WEB_PREVIEW_STACK_NAME" --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text
}

preview_bucket="$(preview_output PreviewBucketName)"
preview_url="$(preview_output PreviewUrl)"
browser_client_id="$(preview_output BrowserClientId)"
distribution_id="$(preview_output PreviewDistributionId)"
[[ "$preview_bucket" != "None" && "$preview_url" != "None" && "$browser_client_id" != "None" && "$distribution_id" != "None" ]] || {
  echo "web-preview stack has invalid outputs." >&2
  exit 1
}

trial_url=""
if [[ "$TRIAL_ENABLED" == "true" ]]; then
  trial_url="/v1/trial/verify"
fi
VITE_QUANTIFY_AGENT_URL="/v1/agent/verify" \
VITE_QUANTIFY_TRIAL_URL="$trial_url" \
VITE_COGNITO_DOMAIN="https://${COGNITO_DOMAIN_PREFIX}.auth.${AWS_REGION}.amazoncognito.com" \
VITE_COGNITO_CLIENT_ID="$browser_client_id" \
VITE_COGNITO_REDIRECT_URI="$preview_url" \
VITE_COGNITO_VERIFY_SCOPE="${OAUTH_RESOURCE_SERVER_IDENTIFIER}/verify" \
npm --prefix web run build

# macOS network volumes can create AppleDouble sidecars during the build. They
# are never web assets and must not be published to the preview bucket.
find web/dist -type f -name '._*' -delete

"$aws_bin" s3 sync web/dist "s3://${preview_bucket}" --delete --only-show-errors
"$aws_bin" cloudfront create-invalidation --distribution-id "$distribution_id" --paths '/*' --output text >/dev/null
printf '%s\n' "Quantify web preview assets deployed: ${preview_url}"
