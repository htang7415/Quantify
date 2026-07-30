#!/usr/bin/env bash
# Deploy the Cognito-JWT-protected public Quantify agent edge after core approval.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_DEPLOY:-}" != "1" ]]; then
  echo "Refusing public-agent deploy; set QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_DEPLOY=1." >&2
  exit 2
fi
for required in AWS_REGION PUBLIC_AGENT_STACK_NAME IMAGE_URI CORE_API_ID COGNITO_DOMAIN_PREFIX \
  OAUTH_RESOURCE_SERVER_IDENTIFIER ALARM_EMAIL; do
  : "${!required:?set $required}"
done

CORE_STAGE_NAME="${CORE_STAGE_NAME:-production}"
PUBLIC_API_THROTTLE_RATE_LIMIT="${PUBLIC_API_THROTTLE_RATE_LIMIT:-1}"
PUBLIC_API_THROTTLE_BURST_LIMIT="${PUBLIC_API_THROTTLE_BURST_LIMIT:-1}"
BROWSER_CLIENT_ID="${BROWSER_CLIENT_ID:-}"
[[ "$IMAGE_URI" =~ @sha256:[0-9a-f]{64}$ ]] || { echo "IMAGE_URI must be an immutable @sha256 reference." >&2; exit 2; }
[[ "$CORE_STAGE_NAME" =~ ^[a-z0-9-]+$ ]] || { echo "CORE_STAGE_NAME is invalid." >&2; exit 2; }
[[ "$COGNITO_DOMAIN_PREFIX" =~ ^[a-z][a-z0-9-]{0,61}[a-z0-9]$ ]] || { echo "COGNITO_DOMAIN_PREFIX is invalid." >&2; exit 2; }
[[ "$OAUTH_RESOURCE_SERVER_IDENTIFIER" =~ ^https://.+$ ]] || { echo "OAUTH_RESOURCE_SERVER_IDENTIFIER must be an https URI." >&2; exit 2; }
for value in "$PUBLIC_API_THROTTLE_RATE_LIMIT" "$PUBLIC_API_THROTTLE_BURST_LIMIT"; do
  [[ "$value" =~ ^[1-9][0-9]*$ && "$value" -le 10 ]] || { echo "public throttle settings must be integers from 1 through 10." >&2; exit 2; }
done
if [[ -n "$BROWSER_CLIENT_ID" && ! "$BROWSER_CLIENT_ID" =~ ^[A-Za-z0-9_-]{1,128}$ ]]; then
  echo "BROWSER_CLIENT_ID is invalid." >&2
  exit 2
fi

aws_bin="${AWS_BIN:-aws}"
command -v "$aws_bin" >/dev/null 2>&1 || { echo "aws is unavailable; set AWS_BIN." >&2; exit 2; }

parameters=(
  "ImageUri=$IMAGE_URI" "CoreApiId=$CORE_API_ID" "CoreStageName=$CORE_STAGE_NAME"
  "CognitoDomainPrefix=$COGNITO_DOMAIN_PREFIX"
  "OAuthResourceServerIdentifier=$OAUTH_RESOURCE_SERVER_IDENTIFIER"
  "AlarmEmail=$ALARM_EMAIL"
  "ApiThrottleRateLimit=$PUBLIC_API_THROTTLE_RATE_LIMIT"
  "ApiThrottleBurstLimit=$PUBLIC_API_THROTTLE_BURST_LIMIT"
)
if [[ -n "$BROWSER_CLIENT_ID" ]]; then
  parameters+=("BrowserClientId=$BROWSER_CLIENT_ID")
fi

"$aws_bin" cloudformation deploy --template-file deploy/aws/public_agent_template.yaml \
  --stack-name="$PUBLIC_AGENT_STACK_NAME" --region="$AWS_REGION" \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND --no-fail-on-empty-changeset \
  --parameter-overrides "${parameters[@]}"
