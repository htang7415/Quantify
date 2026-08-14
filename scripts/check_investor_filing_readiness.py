#!/usr/bin/env python3
"""Create a deterministic Form 13F quarter-readiness report from one local bundle.

The checker has no network fallback and cannot compile, approve, promote,
publish, deploy, or mutate an active release index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from scripts.build_investor_catalog import (
        MANAGERS,
        ManifestSecClient,
        SEC_SUBMISSIONS,
        filing_rows,
        information_table_xml,
    )
except ModuleNotFoundError:  # Direct `python scripts/...` invocation.
    from build_investor_catalog import MANAGERS, ManifestSecClient, SEC_SUBMISSIONS, filing_rows, information_table_xml


SCHEMA_VERSION = "investor-filing-readiness.v1"
QUARTER_ENDS = {(3, 31), (6, 30), (9, 30), (12, 31)}
ACCESSION_PATTERN = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def utc_timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be an exact UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an exact UTC timestamp ending in Z") from error
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise ValueError(f"{field} must be an exact UTC timestamp ending in Z")
    return parsed


def quarter_end(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as error:
        raise ValueError("target report period must be an exact quarter-end date") from error
    if (parsed.month, parsed.day) not in QUARTER_ENDS:
        raise ValueError("target report period must be an exact quarter-end date")
    return parsed.isoformat()


def exact_date(value: str, field: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an exact date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be an exact date")
    return value


def build_readiness_report(
    *,
    source_manifest_path: Path,
    target_report_period: str,
    checked_at: str,
) -> dict[str, Any]:
    target = quarter_end(target_report_period)
    checked_time = utc_timestamp(checked_at, "checked_at")
    client = ManifestSecClient(source_manifest_path)
    source_time = datetime.fromisoformat(client.created_at.replace("Z", "+00:00"))
    if checked_time < source_time:
        raise ValueError("readiness check time cannot precede source bundle creation")
    if datetime.strptime(target, "%Y-%m-%d").date() > checked_time.date():
        raise ValueError("target report period cannot follow the readiness check date")

    managers: list[dict[str, Any]] = []
    latest_filed_dates: list[str] = []
    for manager in MANAGERS:
        submissions = client.get_json(SEC_SUBMISSIONS.format(cik=manager.reporting_cik))
        filings = filing_rows(submissions, client.quarters)
        if len(filings) < 2:
            raise ValueError(f"{manager.firm} does not have two compatible recent 13F filings")
        for filing in filings:
            period = exact_date(filing.get("report_period"), "SEC report period")
            parsed_period = datetime.strptime(period, "%Y-%m-%d").date()
            if (parsed_period.month, parsed_period.day) not in QUARTER_ENDS:
                raise ValueError("SEC report period must be an exact quarter-end date")
            exact_date(filing.get("filed_date"), "SEC filing date")
            if not ACCESSION_PATTERN.fullmatch(filing.get("accession", "")):
                raise ValueError("SEC filing accession is invalid")
            information_table_xml(client, manager.reporting_cik, filing["accession"])
        latest = filings[0]
        latest_period = latest["report_period"]
        if latest_period == target:
            status = "ready"
        elif latest_period < target:
            status = "waiting"
        else:
            status = "ahead"
        latest_filed_dates.append(latest["filed_date"])
        managers.append({
            "reporting_manager_cik": manager.reporting_cik,
            "firm": manager.firm,
            "latest_report_period": latest_period,
            "latest_filed_date": latest["filed_date"],
            "latest_accession": latest["accession"],
            "status": status,
        })

    client.assert_complete()
    if source_time.date() < datetime.strptime(max(latest_filed_dates), "%Y-%m-%d").date():
        raise ValueError("source bundle creation date cannot precede the latest filing date")
    ready_count = sum(manager["status"] == "ready" for manager in managers)
    body = {
        "schema_version": SCHEMA_VERSION,
        "checked_at": checked_at,
        "source_manifest_sha256": client.manifest_sha256,
        "source_created_at": client.created_at,
        "target_report_period": target,
        "status": "complete" if ready_count == len(managers) else "incomplete",
        "candidate_build_authorized": False,
        "manager_count": len(managers),
        "ready_manager_count": ready_count,
        "managers": managers,
        "limitations": [
            "Readiness means each configured manager's latest compatible Form 13F filing matches the requested quarter; it is not source review or publication approval.",
            "The report reflects only the exact SEC submission snapshots bound to the declared local source bundle.",
        ],
    }
    digest = hashlib.sha256(canonical_bytes(body)).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "report_id": f"investor-filing-readiness-{target}-{digest[:12]}",
        **{key: value for key, value in body.items() if key != "schema_version"},
        "manifest_hash": digest,
    }


def write_new_report(path: Path, report: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError("readiness report output already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--target-report-period", required=True, help="Exact quarter-end date, for example 2026-06-30")
    parser.add_argument("--checked-at", required=True, help="Exact UTC timestamp ending in Z")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_readiness_report(
        source_manifest_path=args.source_manifest,
        target_report_period=args.target_report_period,
        checked_at=args.checked_at,
    )
    write_new_report(args.output, report)
    print(
        f"wrote {args.output} ({report['ready_manager_count']}/{report['manager_count']} managers ready; "
        "candidate build not authorized)"
    )


if __name__ == "__main__":
    main()
