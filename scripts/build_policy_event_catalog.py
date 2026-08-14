#!/usr/bin/env python3
"""Compile a frozen, typed policy-event release from reviewed official facts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "policy-event-catalog.v1"
SOURCE_SCHEMA_VERSION = "policy-event-source.v1"
OFFICIAL_HOSTS = {
    "www.federalreserve.gov",
    "www.sec.gov",
    "www.federalregister.gov",
}
CATEGORIES = {"monetary_policy", "financial_regulation", "trade_export_controls"}
ACTION_TYPES = {"decision", "final_rule"}
STATUSES = {"active", "scheduled_effective"}
DETAIL_KINDS = {"fomc_decision", "joint_data_standards", "advanced_computing_export_rule"}


def object_value(value: object, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(message)
    return value


def text(value: object, message: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(message)
    return value


def date_value(value: object, message: str) -> str:
    parsed = text(value, message)
    try:
        datetime.strptime(parsed, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError(message) from error
    return parsed


def official_url(value: object, message: str) -> str:
    parsed = text(value, message)
    if urlparse(parsed).scheme != "https" or urlparse(parsed).hostname not in OFFICIAL_HOSTS:
        raise ValueError(message)
    return parsed


def sha256_value(value: object, message: str) -> str:
    parsed = text(value, message)
    if not re.fullmatch(r"[a-f0-9]{64}", parsed):
        raise ValueError(message)
    return parsed


def string_list(value: object, message: str, minimum: int = 1) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(message)
    if len(set(value)) != len(value):
        raise ValueError(f"{message} Values must be unique")
    return value


def validate_fomc(details: dict[str, Any]) -> None:
    required = {
        "kind", "decision", "target_range_low_pct", "target_range_high_pct", "vote_for", "vote_against",
        "implementation_source_url", "implementation_source_sha256", "next_meeting_start", "next_meeting_end",
        "calendar_source_url", "calendar_source_sha256",
    }
    if set(details) != required or details.get("decision") != "maintained":
        raise ValueError("FOMC detail contract is invalid")
    low, high = details["target_range_low_pct"], details["target_range_high_pct"]
    if isinstance(low, bool) or isinstance(high, bool) or not isinstance(low, (int, float)) or not isinstance(high, (int, float)) or not 0 <= low < high <= 20:
        raise ValueError("FOMC target range is invalid")
    if not isinstance(details["vote_for"], int) or not isinstance(details["vote_against"], int) or details["vote_for"] < 1 or details["vote_against"] < 0:
        raise ValueError("FOMC vote is invalid")
    official_url(details["implementation_source_url"], "FOMC implementation source is invalid")
    sha256_value(details["implementation_source_sha256"], "FOMC implementation hash is invalid")
    start = date_value(details["next_meeting_start"], "FOMC next meeting start is invalid")
    end = date_value(details["next_meeting_end"], "FOMC next meeting end is invalid")
    if end < start:
        raise ValueError("FOMC next meeting dates are invalid")
    official_url(details["calendar_source_url"], "FOMC calendar source is invalid")
    sha256_value(details["calendar_source_sha256"], "FOMC calendar hash is invalid")


def validate_joint_standards(details: dict[str, Any]) -> None:
    required = {"kind", "rule_type", "release_numbers", "federal_register_publish_date", "reporting_requirements_change_at_effective_date", "agencies", "standard_domains"}
    if set(details) != required or details.get("rule_type") != "final" or details.get("reporting_requirements_change_at_effective_date") is not False:
        raise ValueError("Joint data standards detail contract is invalid")
    string_list(details["release_numbers"], "Joint data standards release numbers are invalid")
    date_value(details["federal_register_publish_date"], "Joint data standards publication date is invalid")
    agencies = string_list(details["agencies"], "Joint data standards agencies are invalid", 9)
    if len(agencies) != 9:
        raise ValueError("Joint data standards must name the nine issuing agencies")
    string_list(details["standard_domains"], "Joint data standards domains are invalid")


def validate_export_rule(details: dict[str, Any]) -> None:
    required = {"kind", "rule_type", "federal_register_citation", "review_policy_before", "review_policy_after", "destinations", "named_products", "related_company_tickers", "conditions"}
    if set(details) != required or details.get("rule_type") != "final":
        raise ValueError("Export-control detail contract is invalid")
    if details.get("review_policy_before") != "presumption_of_denial" or details.get("review_policy_after") != "case_by_case_if_conditions_met":
        raise ValueError("Export-control review policy is invalid")
    text(details["federal_register_citation"], "Federal Register citation is invalid")
    string_list(details["destinations"], "Export-control destinations are invalid")
    string_list(details["named_products"], "Export-control products are invalid")
    tickers = string_list(details["related_company_tickers"], "Export-control company tickers are invalid")
    if any(not re.fullmatch(r"[A-Z]{1,5}", ticker) for ticker in tickers):
        raise ValueError("Export-control company ticker is invalid")
    allowed_conditions = {"commercial_availability", "us_supply_capacity", "recipient_security_procedures", "independent_us_testing"}
    if set(string_list(details["conditions"], "Export-control conditions are invalid")) != allowed_conditions:
        raise ValueError("Export-control conditions are incomplete")


def validate_event(value: object) -> dict[str, Any]:
    event = object_value(value, "Policy event is invalid")
    required = {"event_id", "category", "authority_id", "authority_name", "title", "action_type", "status", "published_at", "effective_at", "source_document_id", "source_url", "source_sha256", "details"}
    if set(event) != required:
        raise ValueError("Policy event fields are invalid")
    if not re.fullmatch(r"[a-z0-9-]+", text(event["event_id"], "Policy event ID is invalid")):
        raise ValueError("Policy event ID is invalid")
    if event["category"] not in CATEGORIES or event["action_type"] not in ACTION_TYPES or event["status"] not in STATUSES:
        raise ValueError("Policy event classification is invalid")
    text(event["authority_id"], "Policy authority ID is invalid")
    text(event["authority_name"], "Policy authority name is invalid")
    text(event["title"], "Policy title is invalid")
    date_value(event["published_at"], "Policy publication date is invalid")
    date_value(event["effective_at"], "Policy effective date is invalid")
    text(event["source_document_id"], "Policy source document ID is invalid")
    official_url(event["source_url"], "Policy source URL is invalid")
    sha256_value(event["source_sha256"], "Policy source hash is invalid")
    details = object_value(event["details"], "Policy event details are invalid")
    kind = details.get("kind")
    if kind not in DETAIL_KINDS:
        raise ValueError("Policy event detail kind is invalid")
    if kind == "fomc_decision":
        validate_fomc(details)
    elif kind == "joint_data_standards":
        validate_joint_standards(details)
    else:
        validate_export_rule(details)
    return event


def compile_catalog(payload_bytes: bytes) -> dict[str, Any]:
    payload = json.loads(payload_bytes)
    source = object_value(payload, "Policy source payload is invalid")
    if source.get("schema_version") != SOURCE_SCHEMA_VERSION:
        raise ValueError("Policy source schema is unsupported")
    retrieved_at = text(source.get("retrieved_at"), "Policy retrieval time is missing")
    datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    raw_events = source.get("events")
    if not isinstance(raw_events, list) or len(raw_events) != 3:
        raise ValueError("Initial policy source must contain exactly three events")
    events = [validate_event(event) for event in raw_events]
    event_ids = [event["event_id"] for event in events]
    if len(set(event_ids)) != len(event_ids) or {event["details"]["kind"] for event in events} != DETAIL_KINDS:
        raise ValueError("Policy event identities or required kinds are invalid")
    source_record_hash = hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    observed_date = max(event["published_at"] for event in events)
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "release_id": "",
        "source_record_hash": source_record_hash,
        "observed_at": datetime.fromisoformat(observed_date).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        "retrieved_at": retrieved_at,
        "scope": "Three reviewed official U.S. policy actions: FOMC target-range decision, joint financial-data standards, and advanced-computing export-license review policy.",
        "methodology": "Publish only typed fields manually reviewed against the declared official records and validated by event-specific deterministic contracts; compose no market-direction claim.",
        "limitations": [
            "This release is not a comprehensive policy feed and may omit later amendments, court actions, guidance, or agency-specific implementation.",
            "Affected scope identifies subjects expressly named by an official record; it does not predict an asset-price reaction or establish investment impact.",
            "Scheduled meetings and future effective dates may change after the declared retrieval time and must be read with the release timestamp.",
        ],
        "events": sorted(events, key=lambda event: (event["published_at"], event["event_id"]), reverse=True),
    }
    canonical = json.dumps(catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    catalog["release_id"] = f"policy-events-{observed_date}-{digest[:12]}"
    catalog["manifest_hash"] = digest
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("web/src/data/policyEventCatalog.json"))
    args = parser.parse_args()
    catalog = compile_catalog(args.input_json.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({catalog['release_id']})")


if __name__ == "__main__":
    main()
