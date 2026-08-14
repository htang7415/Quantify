#!/usr/bin/env python3
"""Compile a frozen venture relationship catalog from reviewed official-source facts.

The compiler is cache-only: it performs no network acquisition, publication,
deployment, active-index mutation, or approval action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SOURCE_SCHEMA_VERSION = "vc-source-bundle.v1"
CATALOG_SCHEMA_VERSION = "vc-catalog.v1"
RECORD_SCHEMA_VERSION = "vc-compilation-record.v1"
COMPILER_CONTRACT = "build-vc-catalog.v1"
SOURCE_ID = "official-vc-portfolio-pages"
TAXONOMY_VERSION = "vc-sector-taxonomy.v1"
ALLOWED_HOSTS = {
    "sequoiacap.com", "a16z.com", "foundersfund.com", "khoslaventures.com",
    "jobs.thrivecap.com", "generalcatalyst.com",
}
CATEGORIES = {"core_technology_ai"}
SECTORS = {"ai", "autonomy", "climate_energy", "consumer", "defense", "enterprise_software", "fintech", "semiconductors", "space"}
STAGES = {"pre_seed_seed", "early", "growth", "undisclosed"}
ROLES = {"lead", "participant", "undisclosed"}
FOLLOW_ON_STATES = {"yes", "no", "undisclosed"}
SOURCE_FIELDS = {"schema_version", "source_id", "created_at", "scope", "taxonomy_version", "firms"}
FIRM_FIELDS = {"firm_id", "name", "category", "strategy_labels", "source_url", "source_sha256", "relationships"}
RELATIONSHIP_FIELDS = {"company_id", "company_name", "sector", "first_partnered_year", "stage", "participation_role", "follow_on_status", "source_url", "source_sha256"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def object_value(value: object, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(message)
    return value


def text(value: object, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(message)
    return value


def slug(value: object, message: str) -> str:
    parsed = text(value, message)
    if not re.fullmatch(r"[a-z0-9-]+", parsed):
        raise ValueError(message)
    return parsed


def sha256_value(value: object, message: str) -> str:
    parsed = text(value, message)
    if not re.fullmatch(r"[a-f0-9]{64}", parsed):
        raise ValueError(message)
    return parsed


def utc_timestamp(value: object, message: str) -> str:
    parsed = text(value, message)
    try:
        instant = datetime.strptime(parsed, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ValueError(message) from error
    return instant.strftime("%Y-%m-%dT%H:%M:%SZ")


def official_url(value: object, message: str, expected_host: str | None = None) -> str:
    parsed = text(value, message)
    url = urlparse(parsed)
    host = (url.hostname or "").removeprefix("www.")
    if url.scheme != "https" or host not in ALLOWED_HOSTS or (expected_host is not None and host != expected_host):
        raise ValueError(message)
    return parsed


def string_list(value: object, message: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(message)
    if len(set(value)) != len(value):
        raise ValueError(f"{message} Values must be unique")
    return value


def validate_relationship(value: object, expected_host: str, source_year: int) -> dict[str, Any]:
    relationship = object_value(value, "Venture relationship is invalid")
    if set(relationship) != RELATIONSHIP_FIELDS:
        raise ValueError("Venture relationship fields are invalid")
    slug(relationship.get("company_id"), "Venture company ID is invalid")
    text(relationship.get("company_name"), "Venture company name is invalid")
    if relationship.get("sector") not in SECTORS:
        raise ValueError("Venture sector is invalid")
    partnered = relationship.get("first_partnered_year")
    if partnered is not None and (isinstance(partnered, bool) or not isinstance(partnered, int) or not 1900 <= partnered <= source_year):
        raise ValueError("Venture first-partnered year is invalid")
    if relationship.get("stage") not in STAGES:
        raise ValueError("Venture stage is invalid")
    if relationship.get("participation_role") not in ROLES:
        raise ValueError("Venture participation role is invalid")
    if relationship.get("follow_on_status") not in FOLLOW_ON_STATES:
        raise ValueError("Venture follow-on status is invalid")
    official_url(relationship.get("source_url"), "Venture relationship source URL is invalid", expected_host)
    sha256_value(relationship.get("source_sha256"), "Venture relationship source hash is invalid")
    return relationship


def validate_firm(value: object, source_year: int) -> dict[str, Any]:
    firm = object_value(value, "Venture firm is invalid")
    if set(firm) != FIRM_FIELDS:
        raise ValueError("Venture firm fields are invalid")
    slug(firm.get("firm_id"), "Venture firm ID is invalid")
    text(firm.get("name"), "Venture firm name is invalid")
    if firm.get("category") not in CATEGORIES:
        raise ValueError("Venture firm category is invalid")
    string_list(firm.get("strategy_labels"), "Venture strategy labels are invalid")
    source_url = official_url(firm.get("source_url"), "Venture firm source URL is invalid")
    expected_host = (urlparse(source_url).hostname or "").removeprefix("www.")
    sha256_value(firm.get("source_sha256"), "Venture firm source hash is invalid")
    relationships = firm.get("relationships")
    if not isinstance(relationships, list):
        raise ValueError("Venture firm relationships are invalid")
    validated = [validate_relationship(item, expected_host, source_year) for item in relationships]
    company_ids = [item["company_id"] for item in validated]
    if len(company_ids) != len(set(company_ids)):
        raise ValueError("Venture firm contains a duplicate company relationship")
    return firm


def compile_catalog(payload_bytes: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError as error:
        raise ValueError("Venture source payload is not valid JSON") from error
    source = object_value(payload, "Venture source payload is invalid")
    if set(source) != SOURCE_FIELDS:
        raise ValueError("Venture source fields are invalid")
    if source.get("schema_version") != SOURCE_SCHEMA_VERSION or source.get("source_id") != SOURCE_ID:
        raise ValueError("Venture source schema or source ID is unsupported")
    if source.get("taxonomy_version") != TAXONOMY_VERSION:
        raise ValueError("Venture taxonomy is unsupported")
    created_at = utc_timestamp(source.get("created_at"), "Venture source creation time is invalid")
    text(source.get("scope"), "Venture source scope is missing")
    raw_firms = source.get("firms")
    if not isinstance(raw_firms, list) or not raw_firms:
        raise ValueError("Venture source firms are invalid")
    source_year = int(created_at[:4])
    firms = [validate_firm(value, source_year) for value in raw_firms]
    firm_ids = [firm["firm_id"] for firm in firms]
    firm_names = [firm["name"] for firm in firms]
    if len(firm_ids) != len(set(firm_ids)) or len(firm_names) != len(set(firm_names)):
        raise ValueError("Venture firm identities must be unique")

    company_identity: dict[str, tuple[str, str]] = {}
    compiled_firms: list[dict[str, Any]] = []
    for firm in firms:
        relationships = sorted(firm["relationships"], key=lambda row: (row["company_name"].casefold(), row["company_id"]))
        for relationship in relationships:
            identity = (relationship["company_name"], relationship["sector"])
            previous = company_identity.setdefault(relationship["company_id"], identity)
            if previous != identity:
                raise ValueError("Venture company identity or sector conflicts across firms")
        sector_counts = Counter(relationship["sector"] for relationship in relationships)
        compiled_firms.append({
            "firm_id": firm["firm_id"],
            "name": firm["name"],
            "category": firm["category"],
            "strategy_labels": list(firm["strategy_labels"]),
            "source_url": firm["source_url"],
            "source_sha256": firm["source_sha256"],
            "tracked_relationship_count": len(relationships),
            "sector_counts": [
                {"sector": sector, "company_count": count}
                for sector, count in sorted(sector_counts.items(), key=lambda row: (-row[1], row[0]))
            ],
            "relationships": relationships,
        })

    source_manifest_hash = sha256_bytes(payload_bytes)
    observed_date = created_at[:10]
    firm_count_label = {4: "four", 6: "six"}.get(len(compiled_firms), str(len(compiled_firms)))
    catalog: dict[str, Any] = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "release_id": "",
        "source_manifest_hash": source_manifest_hash,
        "observed_at": created_at,
        "source_fresh_through": observed_date,
        "scope": source["scope"],
        "methodology": "Publish only manually reviewed firm-to-company relationships from declared official firm pages. Count broad reviewed sector classifications by tracked company; do not infer ownership, value, stage, role, follow-on activity, or completeness.",
        "limitations": [
            f"This is a bounded sample of relationships publicly presented by {firm_count_label} venture firms, not a complete or current fund portfolio.",
            "Company count and sector count describe only tracked released relationships and are not weighted by invested capital, ownership, valuation, or return.",
            "Undisclosed timing, stage, participation role, follow-on status, ownership, and position value are not estimated.",
        ],
        "firms": sorted(compiled_firms, key=lambda firm: (firm["name"].casefold(), firm["firm_id"])),
    }
    digest = sha256_bytes(canonical_bytes(catalog))
    catalog["release_id"] = f"vc-{observed_date}-{digest[:12]}"
    catalog["manifest_hash"] = digest
    record = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "source_manifest_sha256": source_manifest_hash,
        "source_created_at": created_at,
        "compiler_contract": COMPILER_CONTRACT,
        "catalog_release_id": catalog["release_id"],
        "catalog_manifest_hash": catalog["manifest_hash"],
        "firm_count": len(compiled_firms),
        "relationship_count": sum(firm["tracked_relationship_count"] for firm in compiled_firms),
        "publication_authorized": False,
    }
    return catalog, record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("web/src/data/vcCatalog.json"))
    parser.add_argument("--record-output", type=Path, default=Path("web/src/data/vcCompilationRecord.json"))
    args = parser.parse_args()
    catalog, record = compile_catalog(args.source.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.record_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.record_output.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({catalog['release_id']}; publication not authorized by compiler)")


if __name__ == "__main__":
    main()
