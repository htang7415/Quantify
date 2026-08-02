#!/usr/bin/env bash
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_PUBLIC_DELIVERY_WAF_ALARM_DEPLOY:-}" != "1" ]]; then
  echo "Refusing public-delivery WAF alarm deploy; set QUANTIFY_AUTHORIZE_AWS_PUBLIC_DELIVERY_WAF_ALARM_DEPLOY=1." >&2
  exit 2
fi
for required in AWS_REGION WAF_ALARM_STACK_NAME WAF_METRIC_NAME WAF_RULE_METRIC_NAME \
  WAF_BLOCKED_REQUESTS_ALARM_THRESHOLD WAF_ALARM_EMAIL; do
  : "${!required:?set $required}"
done
[[ "$AWS_REGION" == "us-east-2" ]] || { echo "AWS_REGION must be us-east-2 for Quantify's primary operating region." >&2; exit 2; }
cloudfront_waf_region="${CLOUDFRONT_WAF_REGION:-us-east-1}"
[[ "$cloudfront_waf_region" == "us-east-1" ]] || { echo "CLOUDFRONT_WAF_REGION must be us-east-1 for a CloudFront WAF alarm." >&2; exit 2; }
[[ "$WAF_BLOCKED_REQUESTS_ALARM_THRESHOLD" =~ ^[0-9]+$ ]] && (( WAF_BLOCKED_REQUESTS_ALARM_THRESHOLD >= 1 )) || {
  echo "WAF_BLOCKED_REQUESTS_ALARM_THRESHOLD must be a positive integer." >&2
  exit 2
}

aws_bin="${AWS_BIN:-aws}"
command -v "$aws_bin" >/dev/null 2>&1 || { echo "aws is unavailable; set AWS_BIN." >&2; exit 2; }
"$aws_bin" cloudformation deploy \
  --template-file deploy/aws/public_delivery_waf_alarm_template.yaml \
  --stack-name "$WAF_ALARM_STACK_NAME" --region "$cloudfront_waf_region" \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "WebAclMetricName=$WAF_METRIC_NAME" \
    "RuleMetricName=$WAF_RULE_METRIC_NAME" \
    "BlockedRequestsThreshold=$WAF_BLOCKED_REQUESTS_ALARM_THRESHOLD" \
    "AlarmEmail=$WAF_ALARM_EMAIL"
"$aws_bin" cloudformation describe-stacks --stack-name "$WAF_ALARM_STACK_NAME" --region "$cloudfront_waf_region" \
  --query 'Stacks[0].Outputs[?OutputKey==`PublicDeliveryWafBlockedRequestsAlarmName`].OutputValue | [0]' --output text
