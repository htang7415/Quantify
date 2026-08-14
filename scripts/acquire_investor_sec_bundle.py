#!/usr/bin/env python3
"""Acquire an exact SEC Form 13F source bundle for later offline compilation.

This is an explicitly run offline factory command. It writes a new source
bundle atomically and has no catalog publication, promotion, deployment, or
active-index mutation path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from scripts.build_investor_catalog import (
        MANAGERS,
        SEC_SUBMISSIONS,
        SOURCE_BUNDLE_SCHEMA_VERSION,
        SecClient,
        filing_rows,
        information_table_xml,
    )
except ModuleNotFoundError:  # Direct `python scripts/...` invocation.
    from build_investor_catalog import (
        MANAGERS,
        SEC_SUBMISSIONS,
        SOURCE_BUNDLE_SCHEMA_VERSION,
        SecClient,
        filing_rows,
        information_table_xml,
    )


class RecordingClient:
    def __init__(self, client: Any) -> None:
        self.client = client
        self.resources: dict[str, tuple[bytes, str]] = {}

    def get_bytes(self, url: str) -> bytes:
        payload = self.client.get_bytes(url)
        media_type = "application/json" if url.endswith(".json") else "application/xml"
        existing = self.resources.get(url)
        if existing is not None and existing != (payload, media_type):
            raise ValueError("SEC acquisition returned different bytes for the same URL")
        self.resources[url] = (payload, media_type)
        return payload

    def get_json(self, url: str) -> dict[str, Any]:
        try:
            value = json.loads(self.get_bytes(url))
        except json.JSONDecodeError as error:
            raise ValueError("SEC acquisition returned invalid JSON") from error
        if not isinstance(value, dict):
            raise ValueError("SEC acquisition JSON must be an object")
        return value


def validate_created_at(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("created_at must be a timestamp with a timezone") from error
    if parsed.tzinfo is None:
        raise ValueError("created_at must include a timezone")


def acquire_bundle(
    *,
    client: Any,
    target_directory: Path,
    created_at: str,
    quarters: int,
) -> dict[str, Any]:
    validate_created_at(created_at)
    if quarters < 2 or quarters > 8:
        raise ValueError("quarters must be between 2 and 8")
    if target_directory.exists():
        raise ValueError("source bundle target directory already exists")

    recorder = RecordingClient(client)
    for manager in MANAGERS:
        submissions = recorder.get_json(SEC_SUBMISSIONS.format(cik=manager.reporting_cik))
        filings = filing_rows(submissions, quarters)
        if len(filings) < 2:
            raise ValueError(f"{manager.firm} does not have two compatible recent 13F filings")
        for filing in filings:
            information_table_xml(recorder, manager.reporting_cik, filing["accession"])

    resources = []
    artifact_payloads: dict[str, bytes] = {}
    for url, (payload, media_type) in sorted(recorder.resources.items()):
        extension = "json" if media_type == "application/json" else "xml"
        relative_path = f"resources/{hashlib.sha256(url.encode('utf-8')).hexdigest()}.{extension}"
        artifact_payloads[relative_path] = payload
        resources.append({
            "url": url,
            "path": relative_path,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "media_type": media_type,
        })
    manifest = {
        "schema_version": SOURCE_BUNDLE_SCHEMA_VERSION,
        "source_id": "sec-edgar-public-filings",
        "created_at": created_at,
        "quarters": quarters,
        "manager_ciks": [manager.reporting_cik for manager in MANAGERS],
        "resources": resources,
    }
    artifact_payloads["manifest.json"] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    target_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target_directory.name}.", dir=target_directory.parent))
    try:
        for relative_path, payload in artifact_payloads.items():
            destination = temporary / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        if target_directory.exists():
            raise ValueError("source bundle target directory already exists")
        os.replace(temporary, target_directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-agent", required=True, help="Application name and contact email for SEC requests")
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/investor-sec"))
    parser.add_argument("--target-directory", type=Path, required=True)
    parser.add_argument("--created-at", required=True, help="Acquisition timestamp with timezone")
    parser.add_argument("--quarters", type=int, default=5)
    args = parser.parse_args()
    manifest = acquire_bundle(
        client=SecClient(args.user_agent, args.cache_dir),
        target_directory=args.target_directory,
        created_at=args.created_at,
        quarters=args.quarters,
    )
    print(f"wrote {args.target_directory} ({len(manifest['resources'])} exact SEC resources; review required)")


if __name__ == "__main__":
    main()
