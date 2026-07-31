"""Read-only fail-closed readiness check for the private task pilot."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def _environment(path: Path) -> dict[str, str]:
    values = dict(os.environ)
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", maxsplit=1)
            if name.strip():
                values[name.strip()] = value.strip().strip("\"'")
    return values


def _required(environment: dict[str, str], name: str) -> str:
    value = environment.get(name)
    if not value:
        raise RuntimeError(f"pilot environment must set {name}")
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


def _json(*arguments: str, environment: dict[str, str]) -> object:
    try:
        return json.loads(_aws(*arguments, environment=environment))
    except json.JSONDecodeError as error:
        raise RuntimeError("AWS check returned invalid JSON") from error


def _resources(*, stack_name: str, region: str, environment: dict[str, str]) -> dict[str, str]:
    payload = _json(
        "cloudformation", "describe-stack-resources", "--stack-name", stack_name,
        "--region", region, "--output", "json", environment=environment,
    )
    rows = payload.get("StackResources") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("pilot stack resources are invalid")
    resources = {
        row["LogicalResourceId"]: row["PhysicalResourceId"]
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("LogicalResourceId"), str)
        and isinstance(row.get("PhysicalResourceId"), str)
    }
    required = {"TaskTable", "PolicyControlTable", "TaskQueue", "TaskDlq", "Worker", "PolicyArtifactBucket"}
    if not required.issubset(resources):
        raise RuntimeError("pilot stack is missing required private resources")
    return resources


def _require_stack_complete(*, stack_name: str, region: str, environment: dict[str, str]) -> None:
    status = _aws(
        "cloudformation", "describe-stacks", "--stack-name", stack_name, "--region", region,
        "--query", "Stacks[0].StackStatus", "--output", "text", environment=environment,
    )
    if status != "UPDATE_COMPLETE":
        raise RuntimeError(f"pilot stack is not stable ({status or 'missing status'})")


def _require_pitr(*, table_name: str, region: str, environment: dict[str, str]) -> None:
    payload = _json("dynamodb", "describe-continuous-backups", "--table-name", table_name, "--region", region, "--output", "json", environment=environment)
    status = payload.get("ContinuousBackupsDescription", {}).get("PointInTimeRecoveryDescription", {}).get("PointInTimeRecoveryStatus") if isinstance(payload, dict) else None
    if status != "ENABLED":
        raise RuntimeError(f"point-in-time recovery is not enabled for {table_name}")


def _require_queue(*, queue_url: str, region: str, environment: dict[str, str], dlq: bool) -> None:
    payload = _json("sqs", "get-queue-attributes", "--queue-url", queue_url, "--attribute-names", "KmsMasterKeyId", "RedrivePolicy", "--region", region, "--output", "json", environment=environment)
    attributes = payload.get("Attributes") if isinstance(payload, dict) else None
    if not isinstance(attributes, dict) or not attributes.get("KmsMasterKeyId"):
        raise RuntimeError(f"queue encryption is not configured for {queue_url}")
    if not dlq and not attributes.get("RedrivePolicy"):
        raise RuntimeError("task queue has no redrive policy")


def _require_bucket(*, bucket_name: str, region: str, environment: dict[str, str]) -> None:
    encryption = _json("s3api", "get-bucket-encryption", "--bucket", bucket_name, "--region", region, "--output", "json", environment=environment)
    versioning = _json("s3api", "get-bucket-versioning", "--bucket", bucket_name, "--region", region, "--output", "json", environment=environment)
    block = _json("s3api", "get-public-access-block", "--bucket", bucket_name, "--region", region, "--output", "json", environment=environment)
    rules = encryption.get("ServerSideEncryptionConfiguration", {}).get("Rules", []) if isinstance(encryption, dict) else []
    public = block.get("PublicAccessBlockConfiguration") if isinstance(block, dict) else None
    if not rules or not isinstance(versioning, dict) or versioning.get("Status") != "Enabled" or not isinstance(public, dict) or not all(public.get(key) is True for key in ("BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets")):
        raise RuntimeError(f"bucket controls are incomplete for {bucket_name}")


def _require_worker(*, worker_name: str, region: str, environment: dict[str, str], mode: str) -> str:
    concurrency = _json("lambda", "get-function-concurrency", "--function-name", worker_name, "--region", region, "--output", "json", environment=environment)
    expected_concurrency = 0 if mode == "inactive" else 2
    if not isinstance(concurrency, dict) or concurrency.get("ReservedConcurrentExecutions") != expected_concurrency:
        raise RuntimeError(f"pilot worker must have reserved concurrency {expected_concurrency}")
    configuration = _json("lambda", "get-function-configuration", "--function-name", worker_name, "--region", region, "--output", "json", environment=environment)
    variables = configuration.get("Environment", {}).get("Variables") if isinstance(configuration, dict) else None
    digest = variables.get("QUANTIFY_IMAGE_DIGEST") if isinstance(variables, dict) else None
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise RuntimeError("pilot worker image digest is invalid")
    mappings = _json("lambda", "list-event-source-mappings", "--function-name", worker_name, "--region", region, "--output", "json", environment=environment)
    rows = mappings.get("EventSourceMappings") if isinstance(mappings, dict) else None
    if mode == "inactive" and rows != []:
        raise RuntimeError("pilot worker must have no active event source mapping")
    if mode == "active":
        if not isinstance(rows, list) or len(rows) != 1:
            raise RuntimeError("active pilot worker requires exactly one event source mapping")
        mapping = rows[0]
        maximum = mapping.get("ScalingConfig", {}).get("MaximumConcurrency") if isinstance(mapping, dict) and isinstance(mapping.get("ScalingConfig"), dict) else None
        if not isinstance(mapping, dict) or mapping.get("State") != "Enabled" or maximum != 2:
            raise RuntimeError("active pilot event source mapping is not bounded and enabled")
    return digest


def _require_alarms_ok(*, stack_name: str, region: str, environment: dict[str, str]) -> int:
    states = _json("cloudwatch", "describe-alarms", "--alarm-name-prefix", stack_name, "--region", region, "--query", "MetricAlarms[].StateValue", "--output", "json", environment=environment)
    if not isinstance(states, list) or len(states) < 4 or any(state != "OK" for state in states):
        raise RuntimeError("pilot alarms are missing or non-OK")
    return len(states)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--env-file", type=Path)
    source.add_argument("--stack-name")
    parser.add_argument("--region")
    parser.add_argument("--audit-bucket")
    parser.add_argument("--mode", choices=("inactive", "active"), default="inactive")
    args = parser.parse_args(argv)
    if args.env_file is not None:
        if not args.env_file.is_file():
            parser.error("private pilot environment file is unreadable")
        environment = _environment(args.env_file)
    elif args.stack_name is not None:
        if not args.region or not args.audit_bucket:
            parser.error("--stack-name requires --region and --audit-bucket")
        environment = {**os.environ, "AWS_REGION": args.region, "AWS_STACK_NAME": args.stack_name, "AUDIT_BUCKET_NAME": args.audit_bucket}
    else:
        default = Path(".quantify-private/research-task-pilot.env")
        if not default.is_file():
            parser.error("private pilot environment file is unreadable")
        environment = _environment(default)
    region = _required(environment, "AWS_REGION")
    if region != "us-east-2":
        raise RuntimeError("pilot region must be us-east-2")
    stack_name = _required(environment, "AWS_STACK_NAME")
    audit_bucket = _required(environment, "AUDIT_BUCKET_NAME")
    _require_stack_complete(stack_name=stack_name, region=region, environment=environment)
    resources = _resources(stack_name=stack_name, region=region, environment=environment)
    _require_pitr(table_name=resources["TaskTable"], region=region, environment=environment)
    _require_pitr(table_name=resources["PolicyControlTable"], region=region, environment=environment)
    _require_queue(queue_url=resources["TaskQueue"], region=region, environment=environment, dlq=False)
    _require_queue(queue_url=resources["TaskDlq"], region=region, environment=environment, dlq=True)
    _require_bucket(bucket_name=resources["PolicyArtifactBucket"], region=region, environment=environment)
    _require_bucket(bucket_name=audit_bucket, region=region, environment=environment)
    digest = _require_worker(worker_name=resources["Worker"], region=region, environment=environment, mode=args.mode)
    alarm_count = _require_alarms_ok(stack_name=stack_name, region=region, environment=environment)
    print(json.dumps({"alarm_count": alarm_count, "image_digest": digest, "mode": args.mode, "stack": stack_name}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify research-task pilot check failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
