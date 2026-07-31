"""Compile one declared frozen fixture release into an indexed task archive."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

from quantify.harness.acquisition import approve_acquisition_requests
from quantify.harness.coverage import EvidenceRequestType
from quantify.indexed_release import IndexedSnapshot, IndexedSnapshotRequest, compile_indexed_release
from quantify.indexed_release_archive import IndexedReleaseArchive, S3IndexedReleaseArchiveStore
from quantify.production import EmbeddedSecSnapshotProvider, validate_embedded_sec_fixtures
from quantify.release_factory import EvidenceRelease, build_evidence_release
from quantify.release_operations import ReleaseApprovalRecord


@dataclass(frozen=True, slots=True)
class ReleaseRequest:
    cik: str
    as_of_date: date
    forms: tuple[str, ...]
    evidence_requests: tuple[EvidenceRequestType, ...]


def _load_object(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"release input is unreadable: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"release input must be an object: {path.name}")
    return value


def load_requests(path: Path) -> tuple[ReleaseRequest, ...]:
    payload = _load_object(path)
    if payload.get("schema_version") != "1.0.0" or not isinstance(payload.get("requests"), list):
        raise ValueError("release compilation requests have an invalid schema")
    parsed: list[ReleaseRequest] = []
    for value in payload["requests"]:
        if not isinstance(value, dict) or set(value) != {"cik", "as_of_date", "forms", "evidence_requests"}:
            raise ValueError("release compilation request has an invalid schema")
        try:
            request = IndexedSnapshotRequest(
                cik=str(value["cik"]),
                as_of_date=date.fromisoformat(str(value["as_of_date"])),
                forms=tuple(value["forms"]),
            )
            evidence_requests = tuple(
                sorted({EvidenceRequestType(item) for item in value["evidence_requests"]}, key=lambda item: item.value)
            )
        except (TypeError, ValueError) as error:
            raise ValueError("release compilation request is invalid") from error
        if len(evidence_requests) != len(value["evidence_requests"]) or len(evidence_requests) > 2:
            raise ValueError("release compilation evidence requests are invalid")
        parsed.append(ReleaseRequest(request.cik, request.as_of_date, request.forms, evidence_requests))
    identities = {(item.cik, item.as_of_date, item.forms, item.evidence_requests) for item in parsed}
    if not parsed or len(identities) != len(parsed):
        raise ValueError("release compilation requests must be non-empty and unique")
    return tuple(sorted(parsed, key=lambda item: (item.cik, item.as_of_date, item.forms, item.evidence_requests)))


def _release(*, fixtures_directory: Path, declaration_path: Path) -> EvidenceRelease:
    declaration = _load_object(declaration_path)
    try:
        return build_evidence_release(
            fixtures_directory=fixtures_directory,
            release_id=str(declaration["release_id"]),
            issuer_ciks=tuple(declaration["issuer_ciks"]),
            evaluation_corpus=fixtures_directory / str(declaration["evaluation_corpus"]),
            source_policy_version=str(declaration["source_policy_version"]),
            eligibility_policy_version=str(declaration["eligibility_policy_version"]),
            restatement_policy_version=str(declaration["restatement_policy_version"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("release declaration is invalid") from error


def compile_release(*, fixtures_directory: Path, declaration_path: Path, requests_path: Path):
    """Compile and replay-check the exact request set selected for one release."""

    release = _release(fixtures_directory=fixtures_directory, declaration_path=declaration_path)
    requests = load_requests(requests_path)
    if {item.cik for item in requests} != set(release.issuer_ciks):
        raise ValueError("release compilation requests must cover exactly the declared issuers")
    embedded = EmbeddedSecSnapshotProvider(fixtures=validate_embedded_sec_fixtures(fixtures_directory))
    snapshots: list[IndexedSnapshot] = []
    for item in requests:
        base_request = IndexedSnapshotRequest(cik=item.cik, as_of_date=item.as_of_date, forms=item.forms)
        base_build = embedded.build(cik=item.cik, as_of_date=item.as_of_date, forms=item.forms)
        snapshots.append(IndexedSnapshot(request=base_request, build=base_build))
        acquisition_records = approve_acquisition_requests(snapshot=base_build.snapshot, requested=item.evidence_requests)
        if acquisition_records:
            expanded_request = IndexedSnapshotRequest(
                cik=item.cik,
                as_of_date=item.as_of_date,
                forms=item.forms,
                acquisition_records=tuple((record.request_type.value, record.reason) for record in acquisition_records),
            )
            expanded_build = embedded.build(
                cik=item.cik, as_of_date=item.as_of_date, forms=item.forms,
                acquisition_records=acquisition_records,
            )
            snapshots.append(IndexedSnapshot(request=expanded_request, build=expanded_build))
    indexed = compile_indexed_release(evidence_release=release, snapshots=tuple(snapshots))
    archived = IndexedReleaseArchive.load(IndexedReleaseArchive.dump(indexed))
    for item in indexed.snapshots:
        replayed = archived.build(
            cik=item.request.cik, as_of_date=item.request.as_of_date,
            forms=item.request.forms, acquisition_records=(),
        ) if not item.request.acquisition_records else archived.build(
            cik=item.request.cik, as_of_date=item.request.as_of_date,
            forms=item.request.forms,
            acquisition_records=approve_acquisition_requests(
                snapshot=embedded.build(cik=item.request.cik, as_of_date=item.request.as_of_date, forms=item.request.forms).snapshot,
                requested=tuple(EvidenceRequestType(request_type) for request_type, _ in item.request.acquisition_records),
            ),
        )
        if replayed.snapshot.manifest_hash != item.build.snapshot.manifest_hash or replayed.audit_manifest.manifest_hash != item.build.audit_manifest.manifest_hash:
            raise ValueError("compiled release archive does not replay")
    return indexed


def _approved_record(*, path: Path, release: EvidenceRelease) -> ReleaseApprovalRecord:
    payload = _load_object(path)
    try:
        record = ReleaseApprovalRecord.from_dict(payload)
    except ValueError as error:
        raise ValueError("release approval record is invalid") from error
    if payload["manifest_hash"] != record.manifest_hash or not record.approved:
        raise ValueError("release approval record is not an approved immutable record")
    if record.release_manifest_hash != release.manifest_hash:
        raise ValueError("release approval record selects a different release")
    return record


def persist_approval_record(
    *, client: object, bucket_name: str, record: ReleaseApprovalRecord
) -> str:
    """Persist the approved immutable gate record before its archive.

    A second attempt is permitted only when the stored content is byte-for-byte
    identical. This is intentionally independent from policy pointers.
    """

    payload = json.dumps(record.as_dict(), sort_keys=True, separators=(",", ":")).encode()
    key = (
        f"evidence-releases/v1/{record.release_manifest_hash}/approval-records/"
        f"{record.manifest_hash}.json"
    )
    try:
        client.put_object(
            Bucket=bucket_name, Key=key, Body=payload, ContentType="application/json",
            ServerSideEncryption="aws:kms", BucketKeyEnabled=True, IfNoneMatch="*",
        )
    except Exception as error:
        response = getattr(error, "response", None)
        code = response.get("Error", {}).get("Code") if isinstance(response, Mapping) else None
        if code not in {"PreconditionFailed", "412"}:
            raise ValueError("release approval record could not be persisted") from error
        try:
            existing = client.get_object(Bucket=bucket_name, Key=key)["Body"]
            existing_payload = existing.read() if hasattr(existing, "read") else existing
        except Exception as read_error:
            raise ValueError("existing release approval record cannot be verified") from read_error
        if existing_payload != payload:
            raise ValueError("existing release approval record does not match")
    return key


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures-directory", type=Path, required=True)
    parser.add_argument("--release-declaration", type=Path, required=True)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--policy-bucket")
    parser.add_argument("--approval-record", type=Path)
    parser.add_argument("--archive-output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    if sum(bool(value) for value in (args.policy_bucket, args.archive_output, args.validate_only)) != 1:
        parser.error("provide exactly one of --policy-bucket, --archive-output, or --validate-only")
    if args.policy_bucket and args.approval_record is None:
        parser.error("--policy-bucket requires --approval-record")
    if not args.policy_bucket and args.approval_record is not None:
        parser.error("--approval-record is only valid with --policy-bucket")
    indexed = compile_release(
        fixtures_directory=args.fixtures_directory,
        declaration_path=args.release_declaration,
        requests_path=args.requests,
    )
    if args.policy_bucket:
        approval = _approved_record(path=args.approval_record, release=indexed.evidence_release)
        try:
            import boto3
        except ImportError as error:  # pragma: no cover - operational dependency.
            raise RuntimeError("boto3 is required for archive persistence") from error
        s3_client = boto3.client("s3")
        persist_approval_record(client=s3_client, bucket_name=args.policy_bucket, record=approval)
        S3IndexedReleaseArchiveStore(bucket_name=args.policy_bucket, client=s3_client).persist(indexed)
    if args.archive_output:
        with args.archive_output.open("xb") as output:
            output.write(IndexedReleaseArchive.dump(indexed))
    print(json.dumps({"evidence_release_manifest_hash": indexed.evidence_release.manifest_hash, "indexed_release_manifest_hash": indexed.manifest_hash, "snapshot_count": len(indexed.snapshots)}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify research-task release compilation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
