"""Explicitly activate the bounded private research-task SQS consumer.

This operator-only control path verifies the selected signed controls and
archived release before enabling exactly one SQS event-source mapping with a
AWS-supported bounded maximum concurrency of two. It creates no public route
and submits no task.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Mapping, Sequence

from quantify.aws_lambda import (
    DynamoDbPolicyControlStore,
    DynamoDbReloadingPolicyControlPlane,
    S3SignedPolicyArtifactLoader,
)
from quantify.indexed_release_archive import S3IndexedReleaseArchiveStore
from quantify.policy_control import KmsPolicyVerifier


def _parameters(stack: Mapping[str, object], *, active: bool) -> list[dict[str, object]]:
    rows = stack.get("Parameters")
    if not isinstance(rows, list):
        raise RuntimeError("pilot stack parameter state is unavailable")
    current = {
        row.get("ParameterKey"): row.get("ParameterValue")
        for row in rows if isinstance(row, Mapping)
    }
    if current.get("WorkerReservedConcurrency") != "0" or current.get("EnableTaskConsumption") != "false":
        raise RuntimeError("pilot activation requires an inactive stack")
    return [
        {"ParameterKey": str(row["ParameterKey"]), "ParameterValue": "true" if row["ParameterKey"] == "EnableTaskConsumption" else "2"}
        if row.get("ParameterKey") in {"WorkerReservedConcurrency", "EnableTaskConsumption", "TaskMaximumConcurrency"}
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


def _verify_active(*, lambda_client: object, worker: str) -> None:
    concurrency = lambda_client.get_function_concurrency(FunctionName=worker)
    mappings = lambda_client.list_event_source_mappings(FunctionName=worker).get("EventSourceMappings")
    if not isinstance(concurrency, Mapping) or concurrency.get("ReservedConcurrentExecutions") != 2:
        raise RuntimeError("activated pilot worker has incorrect reserved concurrency")
    if not isinstance(mappings, list) or len(mappings) != 1:
        raise RuntimeError("activated pilot worker has incorrect event-source mapping count")
    mapping = mappings[0]
    scaling = mapping.get("ScalingConfig") if isinstance(mapping, Mapping) else None
    if not isinstance(mapping, Mapping) or mapping.get("State") != "Enabled" or not isinstance(scaling, Mapping) or scaling.get("MaximumConcurrency") != 2:
        raise RuntimeError("activated pilot worker event source mapping is not bounded")


def _update(cf_client: object, *, stack_name: str, parameters: list[dict[str, object]]) -> None:
    cf_client.update_stack(
        StackName=stack_name, UsePreviousTemplate=True, Parameters=parameters,
        Capabilities=["CAPABILITY_IAM"],
    )
    cf_client.get_waiter("stack_update_complete").wait(StackName=stack_name)


def activate(*, cf_client: object, lambda_client: object, stack_name: str) -> dict[str, object]:
    stack = cf_client.describe_stacks(StackName=stack_name)["Stacks"][0]
    if not isinstance(stack, Mapping) or stack.get("StackStatus") != "UPDATE_COMPLETE":
        raise RuntimeError("pilot stack must be stable before activation")
    parameters = _parameters(stack, active=True)
    worker = _worker(cf_client, stack_name=stack_name)
    if lambda_client.list_event_source_mappings(FunctionName=worker).get("EventSourceMappings") != []:
        raise RuntimeError("pilot activation requires no existing event-source mapping")
    _update(cf_client, stack_name=stack_name, parameters=parameters)
    _verify_active(lambda_client=lambda_client, worker=worker)
    return {"mode": "active", "maximum_task_concurrency": 2, "worker_reserved_concurrency": 2}


def _preflight(*, cf_client: object, dynamodb_client: object, s3_client: object, kms_client: object, stack_name: str) -> None:
    outputs = {
        row["OutputKey"]: row["OutputValue"]
        for row in cf_client.describe_stacks(StackName=stack_name)["Stacks"][0].get("Outputs", [])
        if isinstance(row, Mapping)
    }
    try:
        signer = KmsPolicyVerifier(key_id=outputs["PolicySigningKeyArn"], client=kms_client)
        control = DynamoDbReloadingPolicyControlPlane(
            registry=DynamoDbPolicyControlStore(table_name=outputs["PolicyControlTableName"], client=dynamodb_client),
            artifacts=S3SignedPolicyArtifactLoader(bucket_name=outputs["PolicyArtifactBucketName"], client=s3_client, signer=signer),
            signer=signer,
        )
        pointers = control.current_pointers()
        control.authorize_tool(task_pointers=pointers, tool_name="verify_claims")
        S3IndexedReleaseArchiveStore(bucket_name=outputs["PolicyArtifactBucketName"], client=s3_client).load(evidence_release_manifest_hash=pointers.evidence_release_manifest_hash)
    except (KeyError, TypeError) as error:
        raise RuntimeError("pilot control-plane outputs are unavailable") from error


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack-name", required=True)
    parser.add_argument("--region", required=True)
    args = parser.parse_args(argv)
    if args.region != "us-east-2":
        raise ValueError("pilot activation is limited to us-east-2")
    try:
        import boto3
    except ImportError as error:  # pragma: no cover - operational dependency.
        raise RuntimeError("boto3 is required for private pilot activation") from error
    cloudformation = boto3.client("cloudformation", region_name=args.region)
    _preflight(
        cf_client=cloudformation, dynamodb_client=boto3.client("dynamodb", region_name=args.region),
        s3_client=boto3.client("s3", region_name=args.region), kms_client=boto3.client("kms", region_name=args.region),
        stack_name=args.stack_name,
    )
    print(json.dumps(activate(
        cf_client=cloudformation, lambda_client=boto3.client("lambda", region_name=args.region),
        stack_name=args.stack_name,
    ), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify research-task pilot activation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
