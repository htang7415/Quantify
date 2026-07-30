#!/usr/bin/env bash
# Invite one named tester to the existing Cognito-protected Quantify preview.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_WEB_PREVIEW_INVITE:-}" != "1" ]]; then
  echo "Refusing web-preview invitation; set QUANTIFY_AUTHORIZE_AWS_WEB_PREVIEW_INVITE=1." >&2
  exit 2
fi
for required in AWS_REGION PUBLIC_AGENT_STACK_NAME TESTER_EMAIL; do
  : "${!required:?set $required}"
done
[[ "$TESTER_EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]] || {
  echo "TESTER_EMAIL is invalid." >&2
  exit 2
}

aws_bin="${AWS_BIN:-aws}"
command -v "$aws_bin" >/dev/null 2>&1 || { echo "aws is unavailable; set AWS_BIN." >&2; exit 2; }
user_pool_id="$(
  "$aws_bin" cloudformation describe-stacks --stack-name "$PUBLIC_AGENT_STACK_NAME" --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='CognitoUserPoolId'].OutputValue | [0]" --output text
)"
[[ "$user_pool_id" != "None" && -n "$user_pool_id" ]] || { echo "Cognito user-pool output is unavailable." >&2; exit 1; }

"$aws_bin" cognito-idp admin-create-user \
  --user-pool-id "$user_pool_id" \
  --username "$TESTER_EMAIL" \
  --user-attributes "Name=email,Value=$TESTER_EMAIL" "Name=email_verified,Value=true" \
  --desired-delivery-mediums EMAIL \
  --region "$AWS_REGION" >/dev/null
printf '%s\n' "Quantify preview invitation sent."
