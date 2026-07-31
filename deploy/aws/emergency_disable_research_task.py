"""Guarded emergency stop for the private research-task worker.

This is an offline operator action.  It creates a newly signed runtime policy
that disables the sole pilot tool and atomically selects it using a full
three-hash compare-and-swap.  It never alters an evidence release, a release
gate, task data, or audit data.  Recovery is deliberately a separate approved
policy publication, with this command's output as its expected-current input.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

from quantify.aws_lambda import (
    DynamoDbPolicyControlPublisher,
    DynamoDbPolicyControlStore,
    S3SignedPolicyArtifactLoader,
    S3SignedPolicyArtifactStore,
)
from quantify.policy_control import (
    ArtifactKind,
    KmsPolicySigner,
    PolicyControlPointers,
    PolicyStatus,
    ReleaseGatePolicy,
    RuntimePolicyBundle,
)


def _object(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"emergency input is unreadable: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"emergency input must be an object: {path.name}")
    return value


def _runtime(path: Path) -> RuntimePolicyBundle:
    artifact = S3SignedPolicyArtifactLoader._artifact_from_payload(
        kind=ArtifactKind.RUNTIME_POLICY, payload=_object(path)
    )
    assert isinstance(artifact, RuntimePolicyBundle)
    if (
        artifact.allowed_tools != ("verify_claims",)
        or artifact.disabled_tools
        or artifact.allowed_sources != ("structured_fact",)
    ):
        raise ValueError("emergency disable requires the active private-pilot runtime policy")
    return artifact


def _gate(path: Path) -> ReleaseGatePolicy:
    artifact = S3SignedPolicyArtifactLoader._artifact_from_payload(
        kind=ArtifactKind.RELEASE_GATE_POLICY, payload=_object(path)
    )
    assert isinstance(artifact, ReleaseGatePolicy)
    return artifact


def _pointers(path: Path) -> PolicyControlPointers:
    payload = _object(path)
    required = {
        "evidence_release_manifest_hash",
        "runtime_policy_bundle_hash",
        "release_gate_policy_hash",
    }
    if set(payload) != required:
        raise ValueError("expected pointer document has an invalid schema")
    return PolicyControlPointers(**payload)


def emergency_disable(
    *,
    runtime: RuntimePolicyBundle,
    release_gate: ReleaseGatePolicy,
    expected_current: PolicyControlPointers,
    policy_bucket: str,
    policy_table: str,
    signing_key_arn: str,
    signer_key_id: str,
    s3_client: object,
    dynamodb_client: object,
    kms_client: object,
) -> PolicyControlPointers:
    """Disable the only allowed pilot tool after exact active-state checks."""

    if runtime.content_hash != expected_current.runtime_policy_bundle_hash:
        raise ValueError("runtime policy does not match the expected current pointer")
    if release_gate.content_hash != expected_current.release_gate_policy_hash:
        raise ValueError("release-gate policy does not match the expected current pointer")
    registry = DynamoDbPolicyControlStore(table_name=policy_table, client=dynamodb_client)
    if registry.current_pointers() != expected_current:
        raise ValueError("current control pointers changed; emergency compare-and-swap is unsafe")
    for kind, artifact_hash in (
        (ArtifactKind.EVIDENCE_RELEASE, expected_current.evidence_release_manifest_hash),
        (ArtifactKind.RUNTIME_POLICY, expected_current.runtime_policy_bundle_hash),
        (ArtifactKind.RELEASE_GATE_POLICY, expected_current.release_gate_policy_hash),
    ):
        if registry.status(kind=kind, artifact_hash=artifact_hash) is not PolicyStatus.ACTIVE:
            raise ValueError("emergency disable refuses to reactivate a non-active control")

    disabled = replace(runtime, disabled_tools=("verify_claims",))
    signer = KmsPolicySigner(
        key_id=signing_key_arn, signer_key_id=signer_key_id, client=kms_client
    )
    runtime_envelope = signer.sign(kind=ArtifactKind.RUNTIME_POLICY, artifact=disabled)
    gate_envelope = signer.sign(
        kind=ArtifactKind.RELEASE_GATE_POLICY, artifact=release_gate
    )
    pointers = PolicyControlPointers(
        evidence_release_manifest_hash=expected_current.evidence_release_manifest_hash,
        runtime_policy_bundle_hash=runtime_envelope.artifact_hash,
        release_gate_policy_hash=expected_current.release_gate_policy_hash,
    )
    store = S3SignedPolicyArtifactStore(
        bucket_name=policy_bucket, client=s3_client, signer=signer
    )
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
    parser.add_argument("--expected-current-pointers", type=Path, required=True)
    parser.add_argument("--policy-bucket", required=True)
    parser.add_argument("--policy-table", required=True)
    parser.add_argument("--signing-key-arn", required=True)
    parser.add_argument("--signer-key-id", required=True)
    args = parser.parse_args(argv)
    try:
        import boto3
    except ImportError as error:  # pragma: no cover - operational dependency.
        raise RuntimeError("boto3 is required for the emergency control path") from error
    pointers = emergency_disable(
        runtime=_runtime(args.runtime_policy),
        release_gate=_gate(args.release_gate_policy),
        expected_current=_pointers(args.expected_current_pointers),
        policy_bucket=args.policy_bucket,
        policy_table=args.policy_table,
        signing_key_arn=args.signing_key_arn,
        signer_key_id=args.signer_key_id,
        s3_client=boto3.client("s3"),
        dynamodb_client=boto3.client("dynamodb"),
        kms_client=boto3.client("kms"),
    )
    print(json.dumps({
        "evidence_release_manifest_hash": pointers.evidence_release_manifest_hash,
        "release_gate_policy_hash": pointers.release_gate_policy_hash,
        "runtime_policy_bundle_hash": pointers.runtime_policy_bundle_hash,
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify research-task emergency disable failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
