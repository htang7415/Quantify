"""Read-only cross-artifact validation before private policy publication."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

from quantify.aws_lambda import S3SignedPolicyArtifactLoader
from quantify.indexed_release_archive import IndexedReleaseArchive
from quantify.policy_control import ArtifactKind, PolicyControlPointers, ReleaseGatePolicy, RuntimePolicyBundle
from quantify.release_operations import ReleaseApprovalRecord, ReleaseLane


def _object(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"bundle input is unreadable: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"bundle input must be an object: {path.name}")
    return value


def _runtime(path: Path) -> RuntimePolicyBundle:
    artifact = S3SignedPolicyArtifactLoader._artifact_from_payload(kind=ArtifactKind.RUNTIME_POLICY, payload=_object(path))
    assert isinstance(artifact, RuntimePolicyBundle)
    if artifact.allowed_tools != ("verify_claims",) or artifact.disabled_tools or artifact.allowed_sources != ("structured_fact",):
        raise ValueError("bundle runtime policy exceeds the private-pilot contract")
    return artifact


def _gate_policy(path: Path) -> ReleaseGatePolicy:
    artifact = S3SignedPolicyArtifactLoader._artifact_from_payload(kind=ArtifactKind.RELEASE_GATE_POLICY, payload=_object(path))
    assert isinstance(artifact, ReleaseGatePolicy)
    return artifact


def _approval(path: Path) -> ReleaseApprovalRecord:
    payload = dict(_object(path))
    declared_hash = payload.pop("manifest_hash", None)
    try:
        payload["source_validation_hashes"] = tuple(payload["source_validation_hashes"])
        payload["lane"] = ReleaseLane(payload["lane"])
        payload["reasons"] = tuple(payload["reasons"])
        record = ReleaseApprovalRecord(**payload)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("release approval record is invalid") from error
    if declared_hash != record.manifest_hash:
        raise ValueError("release approval record hash does not replay")
    if not record.approved:
        raise ValueError("release approval record is not approved")
    return record


def _pointers(path: Path) -> PolicyControlPointers:
    payload = _object(path)
    if set(payload) != {"evidence_release_manifest_hash", "runtime_policy_bundle_hash", "release_gate_policy_hash"}:
        raise ValueError("pointer document has an invalid schema")
    return PolicyControlPointers(**payload)


def validate_bundle(*, archive: bytes, runtime: RuntimePolicyBundle, gate_policy: ReleaseGatePolicy, approval: ReleaseApprovalRecord, pointers: PolicyControlPointers) -> dict[str, object]:
    indexed = IndexedReleaseArchive.load(archive).indexed_release
    release_hash = indexed.evidence_release.manifest_hash
    if approval.release_manifest_hash != release_hash or pointers.evidence_release_manifest_hash != release_hash:
        raise ValueError("archive and evidence-release pointer do not match the approval record")
    if approval.release_gate_policy_hash != gate_policy.content_hash or pointers.release_gate_policy_hash != gate_policy.content_hash:
        raise ValueError("release-gate policy does not match the approval record")
    if pointers.runtime_policy_bundle_hash != runtime.content_hash:
        raise ValueError("runtime policy does not match the selected pointers")
    return {
        "evidence_release_manifest_hash": release_hash,
        "indexed_release_manifest_hash": indexed.manifest_hash,
        "release_approval_manifest_hash": approval.manifest_hash,
        "release_gate_policy_hash": gate_policy.content_hash,
        "runtime_policy_bundle_hash": runtime.content_hash,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--runtime-policy", type=Path, required=True)
    parser.add_argument("--release-gate-policy", type=Path, required=True)
    parser.add_argument("--approval-record", type=Path, required=True)
    parser.add_argument("--pointers", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        archive = args.archive.read_bytes()
    except OSError as error:
        raise ValueError("indexed release archive is unreadable") from error
    print(json.dumps(validate_bundle(archive=archive, runtime=_runtime(args.runtime_policy), gate_policy=_gate_policy(args.release_gate_policy), approval=_approval(args.approval_record), pointers=_pointers(args.pointers)), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify research-task bundle validation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
