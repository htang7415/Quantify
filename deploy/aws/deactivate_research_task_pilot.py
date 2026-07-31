"""Explicitly pause the bounded private research-task SQS consumer.

This operator-only control path removes the event-source mapping and sets
reserved worker concurrency to zero. It neither alters signed controls nor
deletes queued messages, so it safely supports offline recovery exercises.
It creates no public route and submits no task.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Mapping, Sequence


def _parameters(stack: Mapping[str, object]) -> list[dict[str, object]]:
    rows = stack.get("Parameters")
    if not isinstance(rows, list):
        raise RuntimeError("pilot stack parameter state is unavailable")
    current = {
        row.get("ParameterKey"): row.get("ParameterValue")
        for row in rows if isinstance(row, Mapping)
    }
    if current.get("WorkerReservedConcurrency") != "2" or current.get("EnableTaskConsumption") != "true":
        raise RuntimeError("pilot deactivation requires an active stack")
    return [
        {"ParameterKey": str(row["ParameterKey"]), "ParameterValue": "0"}
        if row.get("ParameterKey") == "WorkerReservedConcurrency"
        else {"ParameterKey": str(row["ParameterKey"]), "ParameterValue": "false"}
        if row.get("ParameterKey") == "EnableTaskConsumption"
        else {"ParameterKey": str(row["ParameterKey"]), "UsePreviousValue": True}
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("ParameterKey"), str)
    ]


def _worker(cf_client: object, *, stack_name: str) -> str:
    rows = cf_client.describe_stack_resources(StackName=stack_name).get("StackResources", [])
    for row in rows:
        if isinstance(row, Mapping) and row.get("LogicalResourceId") == "Worker" and isinstance(row.get("PhysicalResourceId"), str):
            return row["PhysicalResourceId"]
    raise RuntimeError("pilot stack has no worker")


def _verify_inactive(*, lambda_client: object, worker: str) -> None:
    concurrency = lambda_client.get_function_concurrency(FunctionName=worker)
    mappings = lambda_client.list_event_source_mappings(FunctionName=worker).get("EventSourceMappings")
    if not isinstance(concurrency, Mapping) or concurrency.get("ReservedConcurrentExecutions") != 0:
        raise RuntimeError("paused pilot worker has incorrect reserved concurrency")
    if mappings != []:
        raise RuntimeError("paused pilot worker still has an event-source mapping")


def _update(cf_client: object, *, stack_name: str, parameters: list[dict[str, object]]) -> None:
    cf_client.update_stack(
        StackName=stack_name, UsePreviousTemplate=True, Parameters=parameters,
        Capabilities=["CAPABILITY_IAM"],
    )
    cf_client.get_waiter("stack_update_complete").wait(StackName=stack_name)


def deactivate(*, cf_client: object, lambda_client: object, stack_name: str) -> dict[str, object]:
    stack = cf_client.describe_stacks(StackName=stack_name)["Stacks"][0]
    if not isinstance(stack, Mapping) or stack.get("StackStatus") != "UPDATE_COMPLETE":
        raise RuntimeError("pilot stack must be stable before deactivation")
    parameters = _parameters(stack)
    worker = _worker(cf_client, stack_name=stack_name)
    mappings = lambda_client.list_event_source_mappings(FunctionName=worker).get("EventSourceMappings")
    if not isinstance(mappings, list) or len(mappings) != 1:
        raise RuntimeError("pilot deactivation requires exactly one active event-source mapping")
    _update(cf_client, stack_name=stack_name, parameters=parameters)
    _verify_inactive(lambda_client=lambda_client, worker=worker)
    return {"mode": "inactive", "maximum_task_concurrency": 0, "worker_reserved_concurrency": 0}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack-name", required=True)
    parser.add_argument("--region", required=True)
    args = parser.parse_args(argv)
    if args.region != "us-east-2":
        raise ValueError("pilot deactivation is limited to us-east-2")
    try:
        import boto3
    except ImportError as error:  # pragma: no cover - operational dependency.
        raise RuntimeError("boto3 is required for private pilot deactivation") from error
    print(json.dumps(deactivate(
        cf_client=boto3.client("cloudformation", region_name=args.region),
        lambda_client=boto3.client("lambda", region_name=args.region),
        stack_name=args.stack_name,
    ), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify research-task pilot deactivation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
