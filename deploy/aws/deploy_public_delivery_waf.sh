#!/usr/bin/env bash
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_PUBLIC_DELIVERY_WAF_DEPLOY:-}" != "1" ]]; then
  echo "Refusing public-delivery WAF deploy; set QUANTIFY_AUTHORIZE_AWS_PUBLIC_DELIVERY_WAF_DEPLOY=1." >&2
  exit 2
fi
for required in AWS_REGION WAF_STACK_NAME WAF_RATE_LIMIT WAF_AGGREGATE_KEY_TYPE; do
  : "${!required:?set $required}"
done
[[ "$AWS_REGION" == "us-east-2" ]] || { echo "AWS_REGION must be us-east-2 for Quantify's primary operating region." >&2; exit 2; }
cloudfront_waf_region="${CLOUDFRONT_WAF_REGION:-us-east-1}"
[[ "$cloudfront_waf_region" == "us-east-1" ]] || { echo "CLOUDFRONT_WAF_REGION must be us-east-1 for a CloudFront WAF." >&2; exit 2; }
[[ "$WAF_RATE_LIMIT" =~ ^[0-9]+$ ]] && (( WAF_RATE_LIMIT >= 100 )) || { echo "WAF_RATE_LIMIT must be an integer of at least 100." >&2; exit 2; }
[[ "$WAF_AGGREGATE_KEY_TYPE" == "IP" || "$WAF_AGGREGATE_KEY_TYPE" == "FORWARDED_IP" ]] || { echo "WAF_AGGREGATE_KEY_TYPE must be IP or FORWARDED_IP." >&2; exit 2; }

aws_bin="${AWS_BIN:-aws}"
command -v "$aws_bin" >/dev/null 2>&1 || { echo "aws is unavailable; set AWS_BIN." >&2; exit 2; }
parameters=("RateLimit=$WAF_RATE_LIMIT" "AggregateKeyType=$WAF_AGGREGATE_KEY_TYPE")
if [[ "$WAF_AGGREGATE_KEY_TYPE" == "FORWARDED_IP" ]]; then
  : "${WAF_FORWARDED_IP_HEADER:?set WAF_FORWARDED_IP_HEADER for FORWARDED_IP aggregation}"
  parameters+=("ForwardedIpHeader=$WAF_FORWARDED_IP_HEADER")
fi

"$aws_bin" cloudformation deploy \
  --template-file deploy/aws/public_delivery_waf_template.yaml \
  --stack-name "$WAF_STACK_NAME" --region "$cloudfront_waf_region" \
  --no-fail-on-empty-changeset --parameter-overrides "${parameters[@]}"
"$aws_bin" cloudformation describe-stacks --stack-name "$WAF_STACK_NAME" --region "$cloudfront_waf_region" \
  --query 'Stacks[0].Outputs[?OutputKey==`PublicDeliveryWebAclArn`].OutputValue | [0]' --output text
