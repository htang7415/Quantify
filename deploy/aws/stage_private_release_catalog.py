"""Guarded IAM-only staging for an immutable private release catalog.

This does not configure CloudFront or public access. It writes only encrypted
objects to the selected private artifact bucket and updates a compare-and-swap
stage pointer after a separately signed reviewer action.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
from pathlib import Path
from typing import Sequence

from quantify.private_catalog import (
    CatalogAction, CatalogStageAction, PrivateCatalogStore, sign_action,
)
from quantify.release_operations import CatalogEntry, ReleaseApprovalRecord, ReleaseCatalogManifest, ReleaseStatus


class KmsCatalogSigner:
    algorithm = "RSASSA_PSS_SHA_256"

    def __init__(self, *, key_id: str, client: object) -> None:
        self._key_id, self._client = key_id, client

    def sign(self, *, payload: bytes) -> bytes:
        result = self._client.sign(
            KeyId=self._key_id, Message=payload, SigningAlgorithm=self.algorithm, MessageType="RAW"
        )
        signature = result.get("Signature")
        if not isinstance(signature, bytes):
            raise ValueError("KMS catalog signing response is invalid")
        return signature

    def verify(self, *, payload: bytes, signature: bytes) -> None:
        result = self._client.verify(
            KeyId=self._key_id, Message=payload, Signature=signature,
            SigningAlgorithm=self.algorithm, MessageType="RAW",
        )
        if result.get("SignatureValid") is not True:
            raise ValueError("KMS catalog signature is invalid")


def _approval(path: Path, *, release_manifest_hash: str) -> ReleaseApprovalRecord:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = ReleaseApprovalRecord.from_dict(payload)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("release approval record is invalid") from error
    if not record.approved or record.release_manifest_hash != release_manifest_hash:
        raise ValueError("release approval record does not approve this release")
    return record


def stage(
    *, action_name: CatalogAction, stage_name: str, reviewer_id: str,
    release_id: str | None, release_manifest_hash: str | None,
    approval: ReleaseApprovalRecord | None, expected_current_action_hash: str | None,
    bucket_name: str, signer_key_arn: str, signer: KmsCatalogSigner, s3_client: object,
) -> dict[str, object]:
    catalog: ReleaseCatalogManifest | None = None
    if action_name is CatalogAction.PROMOTE:
        if not release_id or not release_manifest_hash or approval is None:
            raise ValueError("catalog promotion requires an approved release")
        catalog = ReleaseCatalogManifest(
            schema_version="1.0.0",
            entries=(CatalogEntry(release_id, release_manifest_hash, ReleaseStatus.APPROVED),),
        )
        stage_action = CatalogStageAction(
            stage=stage_name, action=action_name, reviewer_id=reviewer_id,
            occurred_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            catalog_manifest_hash=catalog.manifest_hash, release_manifest_hash=release_manifest_hash,
            release_approval_manifest_hash=approval.manifest_hash,
        )
    else:
        if any(value is not None for value in (release_id, release_manifest_hash, approval)):
            raise ValueError("catalog revocation cannot select a release")
        stage_action = CatalogStageAction(
            stage=stage_name, action=action_name, reviewer_id=reviewer_id,
            occurred_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            catalog_manifest_hash=None, release_manifest_hash=None, release_approval_manifest_hash=None,
        )
    signed = sign_action(action=stage_action, signer_key_id=reviewer_id, signer=signer)
    action_hash = PrivateCatalogStore(bucket_name=bucket_name, client=s3_client).stage(
        catalog=catalog, signed_action=signed, signer=signer,
        expected_current_action_hash=expected_current_action_hash,
    )
    return {
        "action": action_name.value, "catalog_manifest_hash": None if catalog is None else catalog.manifest_hash,
        "release_manifest_hash": release_manifest_hash, "stage": stage_name,
        "stage_action_manifest_hash": action_hash,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=[item.value for item in CatalogAction], required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--release-id")
    parser.add_argument("--release-manifest-hash")
    parser.add_argument("--approval-record", type=Path)
    parser.add_argument("--expected-current-action-hash")
    parser.add_argument("--catalog-bucket", required=True)
    parser.add_argument("--signing-key-arn", required=True)
    args = parser.parse_args(argv)
    action = CatalogAction(args.action)
    if action is CatalogAction.PROMOTE and not (args.release_id and args.release_manifest_hash and args.approval_record):
        parser.error("promotion requires --release-id, --release-manifest-hash, and --approval-record")
    if action is CatalogAction.REVOKE and any((args.release_id, args.release_manifest_hash, args.approval_record)):
        parser.error("revocation cannot accept release inputs")
    try:
        import boto3
    except ImportError as error:  # pragma: no cover - operational dependency.
        raise RuntimeError("boto3 is required for private catalog staging") from error
    approval = _approval(args.approval_record, release_manifest_hash=args.release_manifest_hash) if args.approval_record else None
    result = stage(
        action_name=action, stage_name=args.stage, reviewer_id=args.reviewer_id,
        release_id=args.release_id, release_manifest_hash=args.release_manifest_hash,
        approval=approval, expected_current_action_hash=args.expected_current_action_hash,
        bucket_name=args.catalog_bucket, signer_key_arn=args.signing_key_arn,
        signer=KmsCatalogSigner(key_id=args.signing_key_arn, client=boto3.client("kms")),
        s3_client=boto3.client("s3"),
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify private catalog staging failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
