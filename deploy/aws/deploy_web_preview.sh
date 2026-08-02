#!/usr/bin/env bash
# Build and publish a Cognito-protected Quantify browser preview without exposing the private core.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_WEB_PREVIEW_DEPLOY:-}" != "1" ]]; then
  echo "Refusing web-preview deploy; set QUANTIFY_AUTHORIZE_AWS_WEB_PREVIEW_DEPLOY=1." >&2
  exit 2
fi
if [[ "${QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_DEPLOY:-}" != "1" ]]; then
  echo "Refusing browser-client audience update; set QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_DEPLOY=1." >&2
  exit 2
fi
for required in AWS_REGION WEB_PREVIEW_STACK_NAME PUBLIC_AGENT_STACK_NAME COGNITO_DOMAIN_PREFIX \
  OAUTH_RESOURCE_SERVER_IDENTIFIER; do
  : "${!required:?set $required}"
done
TRIAL_ORIGIN_KEY="${TRIAL_ORIGIN_KEY:-}"
if [[ -n "$TRIAL_ORIGIN_KEY" && "${#TRIAL_ORIGIN_KEY}" -lt 32 ]]; then
  echo "TRIAL_ORIGIN_KEY must contain at least 32 characters when supplied." >&2
  exit 2
fi

aws_bin="${AWS_BIN:-aws}"
command -v "$aws_bin" >/dev/null 2>&1 || { echo "aws is unavailable; set AWS_BIN." >&2; exit 2; }

# Production keeps a separately pinned public-edge image.  Prefer it when the
# private production environment supplies one, while retaining the public
# deploy script's documented IMAGE_URI interface.
if [[ -n "${PUBLIC_AGENT_IMAGE_URI:-}" ]]; then
  IMAGE_URI="$PUBLIC_AGENT_IMAGE_URI"
  export IMAGE_URI
fi

stack_output() {
  "$aws_bin" cloudformation describe-stacks --stack-name "$PUBLIC_AGENT_STACK_NAME" --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text
}

user_pool_id="$(stack_output CognitoUserPoolId)"
public_api_id="$(stack_output PublicAgentApiId)"
if [[ "$user_pool_id" == "None" || "$public_api_id" == "None" ]]; then
  # Existing public-agent stacks predate the API-ID output. Add it before the
  # preview is created; this guarded update does not add a browser audience.
  deploy/aws/deploy_public_agent.sh
  user_pool_id="$(stack_output CognitoUserPoolId)"
  public_api_id="$(stack_output PublicAgentApiId)"
fi
[[ "$user_pool_id" != "None" && "$public_api_id" != "None" ]] || {
  echo "public-agent stack is missing the required browser-preview outputs after its guarded update." >&2
  exit 2
}

preview_parameters=(
  "CognitoUserPoolId=$user_pool_id" "LocalRedirectUri=${LOCAL_REDIRECT_URI:-http://127.0.0.1:5173/}"
  "OAuthResourceServerIdentifier=$OAUTH_RESOURCE_SERVER_IDENTIFIER" "PublicAgentApiId=$public_api_id"
)
if [[ -n "$TRIAL_ORIGIN_KEY" ]]; then
  preview_parameters+=("TrialOriginKey=$TRIAL_ORIGIN_KEY")
fi
if [[ -n "${PUBLIC_DELIVERY_WEB_ACL_ARN:-}" ]]; then
  preview_parameters+=("PublicDeliveryWebAclArn=$PUBLIC_DELIVERY_WEB_ACL_ARN")
fi

"$aws_bin" cloudformation deploy --template-file deploy/aws/web_preview_template.yaml \
  --stack-name="$WEB_PREVIEW_STACK_NAME" --region="$AWS_REGION" \
  --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
  --parameter-overrides "${preview_parameters[@]}"

preview_output() {
  "$aws_bin" cloudformation describe-stacks --stack-name "$WEB_PREVIEW_STACK_NAME" --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text
}

preview_bucket="$(preview_output PreviewBucketName)"
preview_url="$(preview_output PreviewUrl)"
browser_client_id="$(preview_output BrowserClientId)"
[[ "$preview_bucket" != "None" && "$preview_url" != "None" && "$browser_client_id" != "None" ]] || {
  echo "web-preview stack has invalid outputs." >&2
  exit 1
}

BROWSER_CLIENT_ID="$browser_client_id" deploy/aws/deploy_public_agent.sh

VITE_QUANTIFY_AGENT_URL="/v1/agent/verify" \
VITE_COGNITO_DOMAIN="https://${COGNITO_DOMAIN_PREFIX}.auth.${AWS_REGION}.amazoncognito.com" \
VITE_COGNITO_CLIENT_ID="$browser_client_id" \
VITE_COGNITO_REDIRECT_URI="$preview_url" \
VITE_COGNITO_VERIFY_SCOPE="${OAUTH_RESOURCE_SERVER_IDENTIFIER}/verify" \
npm --prefix web run build

"$aws_bin" s3 sync web/dist "s3://${preview_bucket}" --delete --only-show-errors
distribution_id="$(preview_output PreviewDistributionId)"
"$aws_bin" cloudfront create-invalidation --distribution-id "$distribution_id" --paths '/*' --output text >/dev/null
printf '%s\n' "Quantify web preview deployed: ${preview_url}"
