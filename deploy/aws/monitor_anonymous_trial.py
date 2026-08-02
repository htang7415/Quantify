"""Read-only health and quota monitor for Quantify's bounded anonymous trial."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys


def _environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"set {name}")
    return value


def _aws(*arguments: str) -> str:
    completed = subprocess.run(
        [os.environ.get("AWS_BIN", "aws"), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _parameters(*, stack_name: str, region: str) -> dict[str, str]:
    payload = _aws(
        "cloudformation",
        "describe-stacks",
        "--stack-name",
        stack_name,
        "--region",
        region,
        "--query",
        "Stacks[0].Parameters[].[ParameterKey,ParameterValue]",
        "--output",
        "json",
    )
    rows = json.loads(payload)
    if not isinstance(rows, list):
        raise RuntimeError("public-agent stack parameters are invalid")
    return {
        key: value
        for row in rows
        if isinstance(row, list)
        and len(row) == 2
        and isinstance((key := row[0]), str)
        and isinstance((value := row[1]), str)
    }


def _ledger_name(*, stack_name: str, region: str) -> str:
    value = _aws(
        "cloudformation",
        "describe-stack-resources",
        "--stack-name",
        stack_name,
        "--region",
        region,
        "--logical-resource-id",
        "AnonymousTrialLedger",
        "--query",
        "StackResources[0].PhysicalResourceId",
        "--output",
        "text",
    )
    if not value or value == "None":
        raise RuntimeError("anonymous trial ledger is unavailable")
    return value


def _daily_usage(*, table_name: str, day: str, region: str) -> tuple[int, int]:
    payload = _aws(
        "dynamodb",
        "get-item",
        "--table-name",
        table_name,
        "--key",
        json.dumps({"bucket": {"S": f"day#{day}"}}, separators=(",", ":")),
        "--projection-expression",
        "request_count,reserved_micro_usd",
        "--consistent-read",
        "--region",
        region,
        "--output",
        "json",
    )
    # AWS CLI emits no JSON document for a missing DynamoDB item. A new UTC
    # day has no ledger row until its first admitted trial request, which is
    # valid zero usage rather than a monitor failure.
    if not payload:
        return 0, 0
    item = json.loads(payload).get("Item", {})
    if not isinstance(item, dict):
        raise RuntimeError("anonymous trial ledger response is invalid")
    try:
        requests = int(item.get("request_count", {}).get("N", "0"))
        reserved = int(item.get("reserved_micro_usd", {}).get("N", "0"))
    except (TypeError, ValueError) as error:
        raise RuntimeError("anonymous trial ledger values are invalid") from error
    return requests, reserved


def main() -> None:
    region = _environment("AWS_REGION")
    stack_name = _environment("PUBLIC_AGENT_STACK_NAME")
    parameters = _parameters(stack_name=stack_name, region=region)
    required = (
        "TrialEnabled",
        "TrialExpiresAt",
        "TrialDailyRequestLimit",
        "TrialDailyCostLimitMicroUsd",
    )
    if any(not parameters.get(name) for name in required):
        raise RuntimeError("anonymous trial configuration is incomplete")
    expires_at = dt.datetime.fromisoformat(parameters["TrialExpiresAt"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.UTC)
    if parameters["TrialEnabled"] != "true" or now >= expires_at:
        raise RuntimeError("anonymous trial is disabled or expired")
    request_limit = int(parameters["TrialDailyRequestLimit"])
    cost_limit = int(parameters["TrialDailyCostLimitMicroUsd"])
    day = now.strftime("%Y-%m-%d")
    request_count, reserved = _daily_usage(
        table_name=_ledger_name(stack_name=stack_name, region=region), day=day, region=region
    )
    if request_count > request_limit or reserved > cost_limit:
        raise RuntimeError("anonymous trial quota exceeds its configured cap")
    print(
        json.dumps(
            {
                "day": day,
                "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "remaining_daily_requests": request_limit - request_count,
                "remaining_daily_cost_micro_usd": cost_limit - reserved,
                "reserved_micro_usd": reserved,
                "request_count": request_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify anonymous-trial monitor failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
