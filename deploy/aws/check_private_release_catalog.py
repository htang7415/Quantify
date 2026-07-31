"""Read-only KMS verification for one private release-catalog stage."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from quantify.private_catalog import CatalogAction, PrivateCatalogStore

from stage_private_release_catalog import KmsCatalogSigner


def check(*, stage: str, bucket_name: str, signing_key_arn: str, s3_client: object, kms_client: object) -> dict[str, object]:
    signed, catalog = PrivateCatalogStore(bucket_name=bucket_name, client=s3_client).load_stage(
        stage=stage, signer=KmsCatalogSigner(key_id=signing_key_arn, client=kms_client)
    )
    action = signed.action
    return {
        "action": action.action.value, "catalog_manifest_hash": action.catalog_manifest_hash,
        "release_manifest_hash": action.release_manifest_hash, "reviewer_id": action.reviewer_id,
        "stage": action.stage, "stage_action_manifest_hash": action.manifest_hash,
        "serving": action.action is CatalogAction.PROMOTE and catalog is not None,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--catalog-bucket", required=True)
    parser.add_argument("--signing-key-arn", required=True)
    args = parser.parse_args(argv)
    try:
        import boto3
    except ImportError as error:  # pragma: no cover - operational dependency.
        raise RuntimeError("boto3 is required for private catalog verification") from error
    print(json.dumps(check(
        stage=args.stage, bucket_name=args.catalog_bucket, signing_key_arn=args.signing_key_arn,
        s3_client=boto3.client("s3"), kms_client=boto3.client("kms"),
    ), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify private catalog check failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
