#!/usr/bin/env bash
set -euo pipefail

[[ "${QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_DELIVERY_DEPLOY:-}" == "1" ]] || {
  echo "Refusing private catalog delivery deployment; set QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_DELIVERY_DEPLOY=1." >&2; exit 2;
}
for required in AWS_STACK_NAME CATALOG_PUBLIC_KEY_ID CLOUDFRONT_WAF_WEB_ACL_ARN; do : "${!required:?set $required}"; done
[[ "$CATALOG_PUBLIC_KEY_ID" =~ ^K[A-Z0-9]+$ ]] || { echo "CATALOG_PUBLIC_KEY_ID is invalid." >&2; exit 2; }
aws cloudformation deploy --template-file deploy/aws/private_catalog_delivery_template.yaml \
  --stack-name "$AWS_STACK_NAME" --region us-east-2 --capabilities CAPABILITY_NAMED_IAM --no-fail-on-empty-changeset \
  --parameter-overrides "TrustedPublicKeyId=$CATALOG_PUBLIC_KEY_ID" "CloudFrontWebAclArn=$CLOUDFRONT_WAF_WEB_ACL_ARN"
