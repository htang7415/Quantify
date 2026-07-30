#!/usr/bin/env bash
# Store the existing public OAuth client secret in this Mac's login Keychain.

set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_PUBLIC_AGENT_KEYCHAIN_PROVISION:-}" != "1" ]]; then
  echo "Refusing Keychain provisioning; set QUANTIFY_AUTHORIZE_PUBLIC_AGENT_KEYCHAIN_PROVISION=1." >&2
  exit 2
fi

env_file="${1:-.quantify-private/aws-production.env}"
[[ -r "$env_file" ]] || { echo "private production environment file is unreadable." >&2; exit 2; }

set -a
# shellcheck source=/dev/null
source "$env_file"
set +a

for required in AWS_REGION AWS_PROFILE PUBLIC_AGENT_STACK_NAME COGNITO_MACHINE_CLIENT_ID; do
  [[ -n "${!required:-}" ]] || { echo "private environment must set $required." >&2; exit 2; }
done

command -v aws >/dev/null || { echo "AWS CLI v2 is required." >&2; exit 2; }
command -v security >/dev/null || { echo "macOS Keychain utility is required." >&2; exit 2; }

user_pool_id="$(
  aws cloudformation describe-stacks \
    --region "$AWS_REGION" \
    --stack-name "$PUBLIC_AGENT_STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='CognitoUserPoolId'].OutputValue | [0]" \
    --output text
)"
[[ "$user_pool_id" != "None" && -n "$user_pool_id" ]] || { echo "Cognito user pool output is unavailable." >&2; exit 1; }

client_secret="$(
  aws cognito-idp describe-user-pool-client \
    --region "$AWS_REGION" \
    --user-pool-id "$user_pool_id" \
    --client-id "$COGNITO_MACHINE_CLIENT_ID" \
    --query 'UserPoolClient.ClientSecret' \
    --output text
)"
[[ "$client_secret" != "None" && -n "$client_secret" ]] || { echo "Cognito machine client secret is unavailable." >&2; exit 1; }

keychain_service="${PUBLIC_AGENT_KEYCHAIN_SERVICE:-quantify.public-agent.oauth-client-secret}"
security add-generic-password \
  -U \
  -s "$keychain_service" \
  -a "$COGNITO_MACHINE_CLIENT_ID" \
  -w "$client_secret" >/dev/null
unset client_secret

printf 'Stored the Quantify public-agent OAuth secret in macOS Keychain (%s).\n' "$keychain_service"
