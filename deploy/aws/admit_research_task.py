"""Guarded IAM-only admission for one private research task.

This offline operator command has no HTTP listener and is not available to the
worker.  It validates current signed controls and the selected immutable
archive before it can atomically admit a task and enqueue its identifier.
``--dry-run`` performs those checks without writing DynamoDB or SQS.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

from quantify.aws_lambda import (
    DynamoDbPolicyControlStore,
    DynamoDbReloadingPolicyControlPlane,
    S3SignedPolicyArtifactLoader,
)
from quantify.indexed_release_archive import S3IndexedReleaseArchiveStore
from quantify.policy_control import KmsPolicyVerifier
from quantify.research_tasks import (
    DeterministicShardedAdmission,
    DynamoDbResearchTaskStore,
    ResearchTaskRequest,
    ResearchTaskService,
    SqsResearchTaskQueue,
    TaskCapacityPolicy,
)
from quantify.harness.coverage import EvidenceRequestType
from quantify.harness.acquisition import approve_acquisition_requests


def _request(path: Path) -> ResearchTaskRequest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("research task request is unreadable") from error
    if not isinstance(raw, dict) or set(raw) - {
        "cik", "analysis", "as_of_date", "forms", "evidence_requests"
    } or not {"cik", "analysis", "as_of_date"}.issubset(raw):
        raise ValueError("research task request schema is invalid")
    try:
        forms = tuple(raw.get("forms", ("10-K", "10-Q")))
        evidence_requests = tuple(
            EvidenceRequestType(value) for value in raw.get("evidence_requests", ())
        )
        return ResearchTaskRequest(
            cik=raw["cik"], analysis=raw["analysis"],
            as_of_date=date.fromisoformat(raw["as_of_date"]), forms=forms,
            evidence_requests=evidence_requests,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("research task request is invalid") from error


def _policy(
    *, shard_count: int, daily_task_limit: int,
    monthly_reservation_limit_micro_usd: int, reservation_micro_usd: int,
) -> TaskCapacityPolicy:
    return TaskCapacityPolicy(
        shard_count=shard_count, daily_task_limit=daily_task_limit,
        monthly_reservation_limit_micro_usd=monthly_reservation_limit_micro_usd,
        reservation_micro_usd=reservation_micro_usd,
    )


def _verify_request_in_release(*, provider: object, request: ResearchTaskRequest) -> None:
    """Prove base and approved acquisition snapshots exist before admission."""

    try:
        base = provider.build(
            cik=request.cik, as_of_date=request.as_of_date, forms=request.forms
        )
        records = approve_acquisition_requests(
            snapshot=base.snapshot, requested=request.evidence_requests
        )
        if records:
            provider.build(
                cik=request.cik, as_of_date=request.as_of_date, forms=request.forms,
                acquisition_records=records,
            )
    except Exception as error:
        raise ValueError("selected evidence release does not contain the requested scope") from error


def admit(
    *, request: ResearchTaskRequest | None, retry_task_id: str | None,
    idempotency_key: str, dry_run: bool,
    task_table: str, task_queue_url: str, task_dlq_url: str,
    policy_bucket: str, policy_table: str, signing_key_arn: str,
    capacity_policy: TaskCapacityPolicy, s3_client: object, dynamodb_client: object,
    sqs_client: object, kms_client: object,
) -> dict[str, object]:
    """Validate release/policy state and optionally create one durable task."""

    signer = KmsPolicyVerifier(key_id=signing_key_arn, client=kms_client)
    control = DynamoDbReloadingPolicyControlPlane(
        registry=DynamoDbPolicyControlStore(table_name=policy_table, client=dynamodb_client),
        artifacts=S3SignedPolicyArtifactLoader(
            bucket_name=policy_bucket, client=s3_client, signer=signer
        ),
        signer=signer,
    )
    pointers = control.current_pointers()
    control.authorize_tool(task_pointers=pointers, tool_name="verify_claims")
    provider = S3IndexedReleaseArchiveStore(bucket_name=policy_bucket, client=s3_client).load(
        evidence_release_manifest_hash=pointers.evidence_release_manifest_hash
    )
    if request is not None:
        _verify_request_in_release(provider=provider, request=request)
    if dry_run:
        if request is None:
            raise ValueError("retry dry-run requires the original task to remain unread")
        return {
            "canonical_request_hash": request.canonical_request_hash,
            "mode": "validated_no_write",
            "release_gate_policy_hash": pointers.release_gate_policy_hash,
            "runtime_policy_bundle_hash": pointers.runtime_policy_bundle_hash,
            "evidence_release_manifest_hash": pointers.evidence_release_manifest_hash,
        }
    store = DynamoDbResearchTaskStore(
        table_name=task_table, client=dynamodb_client, policy=capacity_policy
    )
    queue = SqsResearchTaskQueue(
        queue_url=task_queue_url, dead_letter_queue_url=task_dlq_url, client=sqs_client
    )
    service = ResearchTaskService(
        policy_control=control,
        admission=DeterministicShardedAdmission(policy=capacity_policy),
        store=store, queue=queue,
    )
    if retry_task_id is not None:
        _verify_request_in_release(provider=provider, request=store.get(task_id=retry_task_id).request)
        return service.retry(task_id=retry_task_id, idempotency_key=idempotency_key)
    if request is None:
        raise ValueError("research task request is required")
    return service.submit(request=request, idempotency_key=idempotency_key)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--request", type=Path)
    operation.add_argument("--retry-task-id")
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--task-table", required=True)
    parser.add_argument("--task-queue-url", required=True)
    parser.add_argument("--task-dlq-url", required=True)
    parser.add_argument("--policy-bucket", required=True)
    parser.add_argument("--policy-table", required=True)
    parser.add_argument("--signing-key-arn", required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--daily-task-limit", type=int, required=True)
    parser.add_argument("--monthly-reservation-limit-micro-usd", type=int, required=True)
    parser.add_argument("--reservation-micro-usd", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        import boto3
    except ImportError as error:  # pragma: no cover - operational dependency.
        raise RuntimeError("boto3 is required for private task admission") from error
    result = admit(
        request=_request(args.request) if args.request else None,
        retry_task_id=args.retry_task_id, idempotency_key=args.idempotency_key,
        dry_run=args.dry_run, task_table=args.task_table,
        task_queue_url=args.task_queue_url, task_dlq_url=args.task_dlq_url,
        policy_bucket=args.policy_bucket, policy_table=args.policy_table,
        signing_key_arn=args.signing_key_arn,
        capacity_policy=_policy(
            shard_count=args.shard_count, daily_task_limit=args.daily_task_limit,
            monthly_reservation_limit_micro_usd=args.monthly_reservation_limit_micro_usd,
            reservation_micro_usd=args.reservation_micro_usd,
        ),
        s3_client=boto3.client("s3"), dynamodb_client=boto3.client("dynamodb"),
        sqs_client=boto3.client("sqs"), kms_client=boto3.client("kms"),
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify private research-task admission failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
