#!/usr/bin/env bash
# Validate the deployed private-staging log schemas without printing log content.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_OBSERVABILITY_CHECK:-}" != "1" ]]; then
  echo "Refusing AWS observability check; set QUANTIFY_AUTHORIZE_AWS_OBSERVABILITY_CHECK=1." >&2
  exit 2
fi
for required in AWS_REGION AWS_STACK_NAME; do
  : "${!required:?set $required}"
done
aws_bin="${AWS_BIN:-aws}"
command -v "$aws_bin" >/dev/null 2>&1 || {
  echo "aws is unavailable; set AWS_BIN to its executable path." >&2
  exit 2
}

resource_rows="$("$aws_bin" cloudformation describe-stack-resources \
  --stack-name "$AWS_STACK_NAME" --region "$AWS_REGION" \
  --query 'StackResources[?ResourceType==`AWS::Logs::LogGroup`].[LogicalResourceId,PhysicalResourceId]' \
  --output text)"
lambda_group="$(awk '$1 == "LambdaLogGroup" { print $2 }' <<<"$resource_rows")"
api_group="$(awk '$1 == "ApiAccessLogGroup" { print $2 }' <<<"$resource_rows")"
[[ -n "$lambda_group" && -n "$api_group" ]] || {
  echo "The stack does not expose both Lambda and API access log groups." >&2
  exit 1
}

latest_stream() {
  "$aws_bin" logs describe-log-streams --log-group-name "$1" \
    --order-by LastEventTime --descending --limit 1 --region "$AWS_REGION" \
    --query 'logStreams[0].logStreamName' --output text
}
lambda_stream="$(latest_stream "$lambda_group")"
api_stream="$(latest_stream "$api_group")"
[[ "$lambda_stream" != "None" && "$api_stream" != "None" ]] || {
  echo "Expected recent Lambda and API log streams; run the authenticated smoke first." >&2
  exit 1
}
lambda_payload="$("$aws_bin" logs get-log-events --log-group-name "$lambda_group" \
  --log-stream-name "$lambda_stream" --limit 100 --region "$AWS_REGION" --output json)"
api_payload="$("$aws_bin" logs get-log-events --log-group-name "$api_group" \
  --log-stream-name "$api_stream" --limit 100 --region "$AWS_REGION" --output json)"

LAMBDA_PAYLOAD="$lambda_payload" API_PAYLOAD="$api_payload" python3 - <<'PY'
import json
import os

from quantify.harness.observability import RequestMetrics


def values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from values(nested)


def json_values(message):
    yield message
    try:
        decoded = json.loads(message)
    except json.JSONDecodeError:
        return
    yield from values(decoded)


lambda_events = json.loads(os.environ["LAMBDA_PAYLOAD"])["events"]
api_events = json.loads(os.environ["API_PAYLOAD"])["events"]
lambda_text = [event["message"] for event in lambda_events]
api_text = [event["message"] for event in api_events]

# Deliberately inspect locally and report only counts. This is a smoke-specific
# regression guard, not permission to place request content in CloudWatch.
banned_fragments = (
    "Microsoft revenue increased from fiscal 2023 to fiscal 2024.",
    "GEMINI_API_KEY",
    "gemini_api_key",
    "api_key",
    "companyfacts",
)
assert not any(
    fragment in message
    for fragment in banned_fragments
    for message in lambda_text + api_text
), "redaction violation"

metric_messages = [
    candidate
    for message in lambda_text
    for candidate in json_values(message)
    if candidate.startswith("quantify_request_metrics=")
]
assert metric_messages, "missing request-metrics record"
metric_records = [
    json.loads(message.removeprefix("quantify_request_metrics="))
    for message in metric_messages
]
expected_metric_keys = {"observability_schema_version", *RequestMetrics.__dataclass_fields__}
for record in metric_records:
    assert set(record) == expected_metric_keys, "metric schema drift"
    assert record["observability_schema_version"] == "1.0.0"
    assert "report" not in record and "claim_text" not in record

api_records = [json.loads(message) for message in api_text]
allowed_api_keys = {"requestId", "status", "routeKey", "responseLength", "integrationError"}
for record in api_records:
    assert set(record) == allowed_api_keys, "API access-log schema drift"

print(
    "observability_redaction_check=passed "
    f"lambda_events={len(lambda_events)} "
    f"metric_records={len(metric_records)} "
    f"api_records={len(api_records)}"
)
PY
