"""Run one non-consuming private-worker bootstrap smoke and restore inactivity.

The procedure temporarily grants exactly two reserved Lambda executions while
keeping SQS consumption disabled, invokes the function once with an empty SQS
record list, and unconditionally restores reserved concurrency to zero.  It
does not enqueue a task or invoke a model provider.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Mapping, Sequence


def _parameters(stack: Mapping[str, object]) -> dict[str, str]:
    rows = stack.get("Parameters")
    if not isinstance(rows, list):
        raise RuntimeError("pilot stack parameter state is unavailable")
    values = {
        row["ParameterKey"]: row["ParameterValue"]
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("ParameterKey"), str)
        and isinstance(row.get("ParameterValue"), str)
    }
    if values.get("WorkerReservedConcurrency") != "0":
        raise RuntimeError("worker bootstrap smoke requires inactive reserved concurrency")
    if values.get("EnableTaskConsumption") != "false":
        raise RuntimeError("worker bootstrap smoke requires task consumption disabled")
    return values


def _resources(cf_client: object, *, stack_name: str) -> dict[str, str]:
    rows = cf_client.describe_stack_resources(StackName=stack_name).get("StackResources", [])
    resources = {
        row["LogicalResourceId"]: row["PhysicalResourceId"]
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("LogicalResourceId"), str)
        and isinstance(row.get("PhysicalResourceId"), str)
    }
    if "Worker" not in resources:
        raise RuntimeError("pilot stack has no worker resource")
    return resources


def _update_parameters(values: Mapping[str, str], *, concurrency: str) -> list[dict[str, object]]:
    return [
        {"ParameterKey": key, "ParameterValue": concurrency if key == "WorkerReservedConcurrency" else "false"}
        if key in {"WorkerReservedConcurrency", "EnableTaskConsumption"}
        else {"ParameterKey": key, "UsePreviousValue": True}
        for key in values
    ]


def _update_stack(cf_client: object, *, stack_name: str, parameters: list[dict[str, object]]) -> None:
    cf_client.update_stack(
        StackName=stack_name,
        UsePreviousTemplate=True,
        Parameters=parameters,
        Capabilities=["CAPABILITY_IAM"],
    )
    cf_client.get_waiter("stack_update_complete").wait(StackName=stack_name)


def bootstrap_smoke(*, cf_client: object, lambda_client: object, stack_name: str) -> dict[str, object]:
    """Run an empty-event bootstrap with a guaranteed inactive restoration."""

    stack = cf_client.describe_stacks(StackName=stack_name)["Stacks"][0]
    if not isinstance(stack, Mapping) or stack.get("StackStatus") != "UPDATE_COMPLETE":
        raise RuntimeError("pilot stack must be stable before bootstrap smoke")
    values = _parameters(stack)
    worker = _resources(cf_client, stack_name=stack_name)["Worker"]
    account = lambda_client.get_account_settings().get("AccountLimit", {})
    unreserved = account.get("UnreservedConcurrentExecutions") if isinstance(account, Mapping) else None
    if not isinstance(unreserved, int) or unreserved < 12:
        raise RuntimeError(
            "worker bootstrap smoke requires at least 12 unreserved Lambda executions"
        )
    mappings = lambda_client.list_event_source_mappings(FunctionName=worker).get("EventSourceMappings")
    if mappings != []:
        raise RuntimeError("worker bootstrap smoke requires no event-source mapping")

    activated = False
    invoke_status = None
    try:
        _update_stack(
            cf_client, stack_name=stack_name,
            parameters=_update_parameters(values, concurrency="2"),
        )
        activated = True
        response = lambda_client.invoke(
            FunctionName=worker,
            InvocationType="RequestResponse",
            Payload=b'{"Records":[]}',
        )
        invoke_status = response.get("StatusCode")
        if response.get("FunctionError") or invoke_status != 200:
            raise RuntimeError("empty-event worker bootstrap invocation failed")
    finally:
        if activated:
            _update_stack(
                cf_client, stack_name=stack_name,
                parameters=_update_parameters(values, concurrency="0"),
            )
    restored = lambda_client.get_function_concurrency(FunctionName=worker)
    if restored.get("ReservedConcurrentExecutions") != 0:
        raise RuntimeError("worker bootstrap smoke did not restore inactive concurrency")
    if lambda_client.list_event_source_mappings(FunctionName=worker).get("EventSourceMappings") != []:
        raise RuntimeError("worker bootstrap smoke did not preserve disabled consumption")
    return {"bootstrap_smoke": "passed", "invoke_status": invoke_status, "restored_mode": "inactive"}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack-name", required=True)
    parser.add_argument("--region", required=True)
    args = parser.parse_args(argv)
    if args.region != "us-east-2":
        raise ValueError("worker bootstrap smoke is limited to us-east-2")
    try:
        import boto3
    except ImportError as error:  # pragma: no cover - operational dependency.
        raise RuntimeError("boto3 is required for the worker bootstrap smoke") from error
    print(json.dumps(bootstrap_smoke(
        cf_client=boto3.client("cloudformation", region_name=args.region),
        lambda_client=boto3.client("lambda", region_name=args.region),
        stack_name=args.stack_name,
    ), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify research-task worker bootstrap smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
