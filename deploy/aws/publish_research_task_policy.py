"""Guarded offline publication of signed private-pilot policy artifacts.

This command is intentionally not callable by the worker and never accepts
research input. It signs two validated policy documents, persists their
content-addressed encrypted objects, then atomically publishes their statuses
and the three selected pointers.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Mapping, Sequence

from quantify.aws_lambda import DynamoDbPolicyControlPublisher, S3SignedPolicyArtifactLoader, S3SignedPolicyArtifactStore
from quantify.policy_control import ArtifactKind, KmsPolicySigner, PolicyControlPointers, ReleaseGatePolicy, RuntimePolicyBundle


def _load_json(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"policy input is unreadable: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"policy input must be an object: {path.name}")
    return value


def _runtime(path: Path) -> RuntimePolicyBundle:
    artifact = S3SignedPolicyArtifactLoader._artifact_from_payload(
        kind=ArtifactKind.RUNTIME_POLICY, payload=_load_json(path)
    )
    assert isinstance(artifact, RuntimePolicyBundle)
    if artifact.allowed_tools != ("verify_claims",) or artifact.disabled_tools:
        raise ValueError("private pilot runtime policy must permit only verify_claims")
    if artifact.allowed_sources != ("structured_fact",):
        raise ValueError("private pilot runtime policy must permit only structured facts")
    return artifact


def _release_gate(path: Path) -> ReleaseGatePolicy:
    artifact = S3SignedPolicyArtifactLoader._artifact_from_payload(
        kind=ArtifactKind.RELEASE_GATE_POLICY, payload=_load_json(path)
    )
    assert isinstance(artifact, ReleaseGatePolicy)
    return artifact


def _pointers(path: Path) -> PolicyControlPointers:
    payload = _load_json(path)
    if set(payload) != {
        "evidence_release_manifest_hash",
        "runtime_policy_bundle_hash",
        "release_gate_policy_hash",
    }:
        raise ValueError("expected pointer document has an invalid schema")
    return PolicyControlPointers(**payload)


def publish(
    *,
    runtime: RuntimePolicyBundle,
    release_gate: ReleaseGatePolicy,
    evidence_release_manifest_hash: str,
    expected_current: PolicyControlPointers | None,
    policy_bucket: str,
    policy_table: str,
    signing_key_arn: str,
    signer_key_id: str,
    s3_client: object,
    dynamodb_client: object,
    kms_client: object,
) -> PolicyControlPointers:
    """Validate, sign, persist, and atomically select one policy pair."""

    signer = KmsPolicySigner(
        key_id=signing_key_arn, signer_key_id=signer_key_id, client=kms_client
    )
    runtime_envelope = signer.sign(kind=ArtifactKind.RUNTIME_POLICY, artifact=runtime)
    gate_envelope = signer.sign(kind=ArtifactKind.RELEASE_GATE_POLICY, artifact=release_gate)
    pointers = PolicyControlPointers(
        evidence_release_manifest_hash=evidence_release_manifest_hash,
        runtime_policy_bundle_hash=runtime_envelope.artifact_hash,
        release_gate_policy_hash=gate_envelope.artifact_hash,
    )
    store = S3SignedPolicyArtifactStore(
        bucket_name=policy_bucket, client=s3_client, signer=signer
    )
    # Immutable artifacts must exist before the atomic control-pointer change.
    store.persist(runtime_envelope)
    store.persist(gate_envelope)
    DynamoDbPolicyControlPublisher(
        table_name=policy_table, client=dynamodb_client, signer=signer
    ).publish(
        runtime=runtime_envelope,
        release_gate=gate_envelope,
        pointers=pointers,
        expected_current=expected_current,
    )
    return pointers


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-policy", type=Path, required=True)
    parser.add_argument("--release-gate-policy", type=Path, required=True)
    parser.add_argument("--evidence-release-manifest-hash", required=True)
    parser.add_argument("--policy-bucket", required=True)
    parser.add_argument("--policy-table", required=True)
    parser.add_argument("--signing-key-arn", required=True)
    parser.add_argument("--signer-key-id", required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--expected-current-pointers", type=Path)
    selection.add_argument("--initial-publication", action="store_true")
    args = parser.parse_args(argv)
    expected = _pointers(args.expected_current_pointers) if args.expected_current_pointers else None
    try:
        import boto3
    except ImportError as error:  # pragma: no cover - operational dependency.
        raise RuntimeError("boto3 is required for offline policy publication") from error
    pointers = publish(
        runtime=_runtime(args.runtime_policy),
        release_gate=_release_gate(args.release_gate_policy),
        evidence_release_manifest_hash=args.evidence_release_manifest_hash,
        expected_current=expected,
        policy_bucket=args.policy_bucket,
        policy_table=args.policy_table,
        signing_key_arn=args.signing_key_arn,
        signer_key_id=args.signer_key_id,
        s3_client=boto3.client("s3"),
        dynamodb_client=boto3.client("dynamodb"),
        kms_client=boto3.client("kms"),
    )
    print(json.dumps({"evidence_release_manifest_hash": pointers.evidence_release_manifest_hash, "release_gate_policy_hash": pointers.release_gate_policy_hash, "runtime_policy_bundle_hash": pointers.runtime_policy_bundle_hash}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify research-task policy publication failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
