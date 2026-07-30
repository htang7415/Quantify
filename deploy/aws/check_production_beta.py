"""Read-only production-beta health check with no report or credential output."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def _load_private_environment(path: Path) -> dict[str, str]:
    values = dict(os.environ)
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", maxsplit=1)
        name = name.strip()
        if name:
            values[name] = value.strip().strip("\"'")
    return values


def _required(environment: dict[str, str], name: str) -> str:
    value = environment.get(name)
    if not value:
        raise RuntimeError(f"private production environment must set {name}")
    return value


def _aws(*arguments: str, environment: dict[str, str]) -> str:
    completed = subprocess.run(
        [environment.get("AWS_BIN", "aws"), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return completed.stdout.strip()


def _stack_outputs(*, stack_name: str, region: str, environment: dict[str, str]) -> dict[str, str]:
    payload = _aws(
        "cloudformation",
        "describe-stacks",
        "--stack-name",
        stack_name,
        "--region",
        region,
        "--query",
        "Stacks[0].Outputs[].{key:OutputKey,value:OutputValue}",
        "--output",
        "json",
        environment=environment,
    )
    outputs = json.loads(payload)
    if not isinstance(outputs, list):
        raise RuntimeError(f"{stack_name} has invalid CloudFormation outputs")
    return {
        item["key"]: item["value"]
        for item in outputs
        if isinstance(item, dict)
        and isinstance(item.get("key"), str)
        and isinstance(item.get("value"), str)
    }


def _require_stack_complete(*, stack_name: str, region: str, environment: dict[str, str]) -> None:
    status = _aws(
        "cloudformation",
        "describe-stacks",
        "--stack-name",
        stack_name,
        "--region",
        region,
        "--query",
        "Stacks[0].StackStatus",
        "--output",
        "text",
        environment=environment,
    )
    if status != "UPDATE_COMPLETE":
        raise RuntimeError(f"{stack_name} is not stable ({status or 'missing status'})")


def _require_alarms_ok(*, stack_name: str, region: str, environment: dict[str, str]) -> int:
    payload = _aws(
        "cloudwatch",
        "describe-alarms",
        "--alarm-name-prefix",
        stack_name,
        "--region",
        region,
        "--query",
        "MetricAlarms[].StateValue",
        "--output",
        "json",
        environment=environment,
    )
    states = json.loads(payload)
    if not isinstance(states, list) or not states:
        raise RuntimeError(f"{stack_name} exposes no metric alarms")
    if any(state != "OK" for state in states):
        raise RuntimeError(f"{stack_name} has a non-OK alarm")
    return len(states)


def _audit_manifest_count(*, bucket_name: str, region: str, environment: dict[str, str]) -> int:
    raw_count = _aws(
        "s3api",
        "list-objects-v2",
        "--bucket",
        bucket_name,
        "--prefix",
        "audit-manifests/",
        "--region",
        region,
        "--query",
        "length(Contents)",
        "--output",
        "text",
        environment=environment,
    )
    try:
        count = int(raw_count)
    except ValueError as error:
        raise RuntimeError("audit manifest object count is invalid") from error
    if count < 1:
        raise RuntimeError("production audit store has no canonical manifests")
    return count


def _reserved_micro_usd(*, table_name: str, region: str, environment: dict[str, str]) -> tuple[str, int]:
    month = dt.datetime.now(dt.UTC).strftime("%Y-%m")
    payload = _aws(
        "dynamodb",
        "get-item",
        "--table-name",
        table_name,
        "--key",
        json.dumps({"month": {"S": month}}, separators=(",", ":")),
        "--projection-expression",
        "reserved_micro_usd",
        "--consistent-read",
        "--region",
        region,
        "--output",
        "json",
        environment=environment,
    )
    item = json.loads(payload).get("Item", {})
    raw_value = item.get("reserved_micro_usd", {}).get("N", "0") if isinstance(item, dict) else "0"
    try:
        reserved = int(raw_value)
    except (TypeError, ValueError) as error:
        raise RuntimeError("monthly cost reservation is invalid") from error
    if reserved < 0:
        raise RuntimeError("monthly cost reservation is invalid")
    return month, reserved


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".quantify-private/aws-production.env"))
    args = parser.parse_args(argv)
    if not args.env_file.is_file():
        parser.error("private production environment file is unreadable")
    environment = _load_private_environment(args.env_file)
    region = _required(environment, "AWS_REGION")
    core_stack = _required(environment, "PRODUCTION_CORE_STACK_NAME")
    public_stack = _required(environment, "PUBLIC_AGENT_STACK_NAME")
    monthly_limit = int(_required(environment, "MONTHLY_COST_LIMIT_MICRO_USD"))
    if monthly_limit <= 0:
        parser.error("MONTHLY_COST_LIMIT_MICRO_USD must be positive")

    _require_stack_complete(stack_name=core_stack, region=region, environment=environment)
    _require_stack_complete(stack_name=public_stack, region=region, environment=environment)
    core_alarm_count = _require_alarms_ok(stack_name=core_stack, region=region, environment=environment)
    public_alarm_count = _require_alarms_ok(stack_name=public_stack, region=region, environment=environment)
    core_outputs = _stack_outputs(stack_name=core_stack, region=region, environment=environment)
    audit_count = _audit_manifest_count(
        bucket_name=_required(core_outputs, "AuditManifestBucketName"),
        region=region,
        environment=environment,
    )
    month, reserved = _reserved_micro_usd(
        table_name=_required(core_outputs, "MonthlyCostLedgerName"),
        region=region,
        environment=environment,
    )
    if reserved > monthly_limit:
        raise RuntimeError("monthly model-cost reservation exceeds the configured cap")
    print(
        json.dumps(
            {
                "audit_manifest_count": audit_count,
                "core_alarm_count": core_alarm_count,
                "core_stack": core_stack,
                "month": month,
                "public_alarm_count": public_alarm_count,
                "public_stack": public_stack,
                "remaining_micro_usd": monthly_limit - reserved,
                "reserved_micro_usd": reserved,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify production beta check failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
