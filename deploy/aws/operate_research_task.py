"""Guarded IAM-only status, cancellation, and reconciliation for one task.

This offline operator command never accepts research text and exposes only the
task service's safe result. It does not create a public route or provider
fallback. Reconciliation uses the configured unavailable reconciler unless an
attributable provider adapter is separately implemented and approved.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Sequence

from quantify.aws_lambda import (
    DynamoDbPolicyControlStore,
    DynamoDbReloadingPolicyControlPlane,
    S3SignedPolicyArtifactLoader,
)
from quantify.policy_control import KmsPolicyVerifier
from quantify.research_tasks import (
    DeterministicShardedAdmission,
    DynamoDbResearchTaskStore,
    ResearchTaskService,
    TaskCapacityPolicy,
    TaskQueueUnavailableError,
)


_TASK_ID = re.compile(r"^[0-9a-f]{32}$")


class _NoSubmitQueue:
    """Prevents status/control operations from accidentally queuing work."""

    def enqueue(self, *, task_id: str) -> None:
        del task_id
        raise TaskQueueUnavailableError("operator lifecycle command cannot enqueue work")

    def receive(self):
        return None

    def acknowledge(self, *, message) -> None:
        del message

    def fail(self, *, message) -> None:
        del message


def operate(
    *, operation: str, task_id: str, task_table: str, policy_bucket: str,
    policy_table: str, signing_key_arn: str, capacity_policy: TaskCapacityPolicy,
    s3_client: object, dynamodb_client: object, kms_client: object,
) -> dict[str, object]:
    if operation not in {"status", "cancel", "reconcile"}:
        raise ValueError("task operation is invalid")
    if not _TASK_ID.fullmatch(task_id):
        raise ValueError("task id is invalid")
    signer = KmsPolicyVerifier(key_id=signing_key_arn, client=kms_client)
    control = DynamoDbReloadingPolicyControlPlane(
        registry=DynamoDbPolicyControlStore(table_name=policy_table, client=dynamodb_client),
        artifacts=S3SignedPolicyArtifactLoader(bucket_name=policy_bucket, client=s3_client, signer=signer),
        signer=signer,
    )
    store = DynamoDbResearchTaskStore(
        table_name=task_table, client=dynamodb_client, policy=capacity_policy
    )
    service = ResearchTaskService(
        policy_control=control,
        admission=DeterministicShardedAdmission(policy=capacity_policy),
        store=store, queue=_NoSubmitQueue(),
    )
    if operation == "status":
        return service.status(task_id=task_id)
    if operation == "cancel":
        return service.cancel(task_id=task_id)
    return service.reconcile(task_id=task_id)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=("status", "cancel", "reconcile"), required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-table", required=True)
    parser.add_argument("--policy-bucket", required=True)
    parser.add_argument("--policy-table", required=True)
    parser.add_argument("--signing-key-arn", required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--daily-task-limit", type=int, required=True)
    parser.add_argument("--monthly-reservation-limit-micro-usd", type=int, required=True)
    parser.add_argument("--reservation-micro-usd", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        import boto3
    except ImportError as error:  # pragma: no cover - operational dependency.
        raise RuntimeError("boto3 is required for private task operation") from error
    result = operate(
        operation=args.operation, task_id=args.task_id, task_table=args.task_table,
        policy_bucket=args.policy_bucket, policy_table=args.policy_table,
        signing_key_arn=args.signing_key_arn,
        capacity_policy=TaskCapacityPolicy(
            shard_count=args.shard_count, daily_task_limit=args.daily_task_limit,
            monthly_reservation_limit_micro_usd=args.monthly_reservation_limit_micro_usd,
            reservation_micro_usd=args.reservation_micro_usd,
        ),
        s3_client=boto3.client("s3"), dynamodb_client=boto3.client("dynamodb"),
        kms_client=boto3.client("kms"),
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify private research-task operation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
