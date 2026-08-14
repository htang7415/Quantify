#!/usr/bin/env python3
"""Compile a frozen public investor catalog from SEC Form 13F XML filings.

The release path consumes a reviewed, hash-bound local source bundle with no
network fallback. Explicit network acquisition remains a separate CLI mode and
requires an SEC-compliant user agent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{name}"
SCHEMA_VERSION = "investor-catalog.v1"
SOURCE_BUNDLE_SCHEMA_VERSION = "investor-sec-source-bundle.v1"
COMPILATION_RECORD_SCHEMA_VERSION = "investor-compilation-record.v1"
APPROVED_SEC_HOSTS = {"data.sec.gov", "www.sec.gov"}


@dataclass(frozen=True)
class Manager:
    slug: str
    reporting_cik: str
    firm: str
    person: str | None
    category: str
    primary_theme: str


MANAGERS = (
    Manager("altimeter-capital", "0001541617", "Altimeter Capital", "Brad Gerstner", "Technology / Growth", "AI / Technology"),
    Manager("pershing-square", "0001336528", "Pershing Square", "Bill Ackman", "Concentrated / Quality", "Concentrated Quality"),
    Manager("berkshire-hathaway", "0001067983", "Berkshire Hathaway", None, "Concentrated / Quality", "Quality / Value"),
    Manager("coatue-management", "0001135730", "Coatue Management", "Philippe Laffont", "Technology / Growth", "Technology / Internet"),
    Manager("duquesne-family-office", "0001536411", "Duquesne Family Office", "Stanley Druckenmiller", "Macro / Opportunistic", "Macro / Opportunistic"),
    Manager("appaloosa", "0001656456", "Appaloosa", "David Tepper", "Macro / Opportunistic", "Opportunistic"),
    Manager("tiger-global", "0001167483", "Tiger Global", "Chase Coleman", "Technology / Growth", "Internet / Software"),
    Manager("viking-global", "0001103804", "Viking Global", "Andreas Halvorsen", "Technology / Growth", "Global Growth"),
)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(node: ET.Element, name: str, default: str = "") -> str:
    for child in node.iter():
        if local_name(child.tag).lower() == name.lower():
            return (child.text or default).strip()
    return default


def decimal_value(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", "").strip() or "0")
    except InvalidOperation as error:
        raise ValueError(f"invalid numeric 13F value: {value!r}") from error


class SecClient:
    def __init__(self, user_agent: str, cache_dir: Path) -> None:
        if "@" not in user_agent or len(user_agent) < 12:
            raise ValueError("--user-agent must identify the application and include a contact email")
        self.user_agent = user_agent
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_bytes(self, url: str) -> bytes:
        cache_name = hashlib.sha256(url.encode("utf-8")).hexdigest()
        cached = self.cache_dir / cache_name
        if cached.exists():
            return cached.read_bytes()
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
        cached.write_bytes(payload)
        time.sleep(0.12)
        return payload

    def get_json(self, url: str) -> dict[str, Any]:
        return json.loads(self.get_bytes(url))


class ManifestSecClient:
    """Read only exact SEC resources declared by one reviewed local manifest."""

    def __init__(self, manifest_path: Path) -> None:
        try:
            manifest_bytes = manifest_path.read_bytes()
            manifest = json.loads(manifest_bytes)
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("investor SEC source manifest is not readable JSON") from error
        if not isinstance(manifest, dict) or manifest.get("schema_version") != SOURCE_BUNDLE_SCHEMA_VERSION:
            raise ValueError("investor SEC source manifest schema is unsupported")
        if set(manifest) != {"schema_version", "source_id", "created_at", "quarters", "manager_ciks", "resources"}:
            raise ValueError("investor SEC source manifest fields are invalid")
        if manifest.get("source_id") != "sec-edgar-public-filings":
            raise ValueError("investor SEC source is not approved")
        created_at = manifest.get("created_at")
        if not isinstance(created_at, str):
            raise ValueError("investor SEC source creation time is required")
        try:
            parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("investor SEC source creation time is invalid") from error
        if parsed_created_at.tzinfo is None:
            raise ValueError("investor SEC source creation time must include a timezone")
        quarters = manifest.get("quarters")
        if not isinstance(quarters, int) or quarters < 2 or quarters > 8:
            raise ValueError("investor SEC source history depth must be between 2 and 8")
        manager_ciks = manifest.get("manager_ciks")
        expected_ciks = {manager.reporting_cik for manager in MANAGERS}
        if not isinstance(manager_ciks, list) or len(manager_ciks) != len(set(manager_ciks)) or set(manager_ciks) != expected_ciks:
            raise ValueError("investor SEC source manager scope does not match the compiler")
        resources = manifest.get("resources")
        if not isinstance(resources, list) or not resources:
            raise ValueError("investor SEC source resources are required")

        bundle_root = manifest_path.parent.resolve()
        payloads: dict[str, bytes] = {}
        media_types: dict[str, str] = {}
        resource_paths: set[Path] = set()
        for resource in resources:
            if not isinstance(resource, dict):
                raise ValueError("investor SEC source resource is invalid")
            if set(resource) != {"url", "path", "sha256", "media_type"}:
                raise ValueError("investor SEC source resource fields are invalid")
            url = resource.get("url")
            relative_path = resource.get("path")
            digest = resource.get("sha256")
            media_type = resource.get("media_type")
            parsed_url = urlparse(url) if isinstance(url, str) else None
            if parsed_url is None or parsed_url.scheme != "https" or parsed_url.hostname not in APPROVED_SEC_HOSTS:
                raise ValueError("investor SEC source resource must use an approved SEC URL")
            if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
                raise ValueError("investor SEC source resource path is invalid")
            declared_path = Path(relative_path)
            if declared_path.is_absolute() or ".." in declared_path.parts:
                raise ValueError("investor SEC source resource path must stay inside the bundle")
            resolved_path = (bundle_root / declared_path).resolve()
            if not resolved_path.is_relative_to(bundle_root):
                raise ValueError("investor SEC source resource path escapes the bundle")
            if not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise ValueError("investor SEC source resource hash is invalid")
            if media_type not in {"application/json", "application/xml"}:
                raise ValueError("investor SEC source resource media type is unsupported")
            if url in payloads or resolved_path in resource_paths:
                raise ValueError("investor SEC source resources must have unique URLs and paths")
            try:
                payload = resolved_path.read_bytes()
            except OSError as error:
                raise ValueError("investor SEC source resource is missing") from error
            if hashlib.sha256(payload).hexdigest() != digest:
                raise ValueError("investor SEC source resource hash does not match")
            payloads[url] = payload
            media_types[url] = media_type
            resource_paths.add(resolved_path)

        self.manifest = manifest
        self.manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        self.quarters = quarters
        self.created_at = created_at
        self._payloads = payloads
        self._media_types = media_types
        self._used_urls: set[str] = set()

    def get_bytes(self, url: str) -> bytes:
        payload = self._payloads.get(url)
        if payload is None:
            raise ValueError(f"investor SEC source bundle does not declare requested URL: {url}")
        self._used_urls.add(url)
        return payload

    def get_json(self, url: str) -> dict[str, Any]:
        if self._media_types.get(url) != "application/json":
            raise ValueError("investor SEC JSON request has the wrong declared media type")
        try:
            value = json.loads(self.get_bytes(url))
        except json.JSONDecodeError as error:
            raise ValueError("investor SEC JSON resource is invalid") from error
        if not isinstance(value, dict):
            raise ValueError("investor SEC JSON resource must be an object")
        return value

    def assert_media_type(self, url: str, expected: str) -> None:
        if self._media_types.get(url) != expected:
            raise ValueError(f"investor SEC resource has the wrong declared media type for {url}")

    def assert_complete(self) -> None:
        unused = set(self._payloads) - self._used_urls
        if unused:
            raise ValueError(f"investor SEC source bundle contains {len(unused)} unused resource(s)")

    @property
    def resource_count(self) -> int:
        return len(self._payloads)


def filing_rows(submissions: dict[str, Any], count: int) -> list[dict[str, str]]:
    recent = submissions["filings"]["recent"]
    rows: list[dict[str, str]] = []
    for index, form in enumerate(recent["form"]):
        if form not in {"13F-HR", "13F-HR/A"}:
            continue
        rows.append(
            {
                "form": form,
                "report_period": recent["reportDate"][index],
                "filed_date": recent["filingDate"][index],
                "accession": recent["accessionNumber"][index],
            }
        )
    # Prefer an amendment for the same period, otherwise the newest accepted filing.
    by_period: dict[str, dict[str, str]] = {}
    for row in rows:
        by_period.setdefault(row["report_period"], row)
    return sorted(by_period.values(), key=lambda row: row["report_period"], reverse=True)[:count]


def information_table_xml(client: SecClient | ManifestSecClient, cik: str, accession: str) -> tuple[bytes, str]:
    accession_path = accession.replace("-", "")
    index_url = SEC_ARCHIVES.format(cik=str(int(cik)), accession=accession_path, name="index.json")
    index = client.get_json(index_url)
    candidates = [item["name"] for item in index["directory"]["item"] if item["name"].lower().endswith(".xml")]
    for name in candidates:
        url = SEC_ARCHIVES.format(cik=str(int(cik)), accession=accession_path, name=name)
        if isinstance(client, ManifestSecClient):
            client.assert_media_type(url, "application/xml")
        payload = client.get_bytes(url)
        try:
            root = ET.fromstring(payload)
        except ET.ParseError:
            continue
        if local_name(root.tag).lower() == "informationtable":
            return payload, url
    raise ValueError(f"no 13F information table XML for {cik} {accession}")


def instrument_type(title: str, put_call: str) -> str:
    normalized = title.upper()
    if put_call:
        return "Option"
    if "WARRANT" in normalized or normalized.startswith("W ") or "W EXP" in normalized:
        return "Warrant"
    if "ETF" in normalized or "UNIT" in normalized or "FUND" in normalized:
        return "Fund / ETF"
    if "ADR" in normalized or "ADS" in normalized or "SPONSORED" in normalized:
        return "ADR"
    if "COM" in normalized or "CL " in normalized or "SHS" in normalized:
        return "Common equity"
    return "Other"


def parse_information_table(payload: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(payload)
    aggregate: dict[str, dict[str, Any]] = {}
    for row in root.iter():
        if local_name(row.tag).lower() != "infotable":
            continue
        issuer = child_text(row, "nameOfIssuer")
        title = child_text(row, "titleOfClass")
        cusip = child_text(row, "cusip").upper()
        put_call = child_text(row, "putCall").upper()
        value = decimal_value(child_text(row, "value"))
        shares = decimal_value(child_text(row, "sshPrnamt"))
        share_type = child_text(row, "sshPrnamtType").upper()
        if not issuer or not cusip or value < 0 or shares < 0:
            raise ValueError("13F row is missing a valid issuer, CUSIP, value, or share amount")
        key = "|".join((cusip, title.upper(), put_call, share_type))
        current = aggregate.setdefault(
            key,
            {
                "security_id": key,
                "issuer": issuer,
                "title": title,
                "cusip": cusip,
                "put_call": put_call or None,
                "share_type": share_type,
                "instrument_type": instrument_type(title, put_call),
                "value_usd": Decimal(0),
                "shares": Decimal(0),
            },
        )
        current["value_usd"] += value
        current["shares"] += shares
    if not aggregate:
        raise ValueError("13F information table contains no holdings")
    return list(aggregate.values())


def load_metadata(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "investor-security-metadata.v1":
        raise ValueError("investor security metadata has an unsupported schema")
    return value.get("securities", {})


def rounded(value: Decimal, places: int = 2) -> float:
    quantum = Decimal(1).scaleb(-places)
    return float(value.quantize(quantum))


def compile_snapshot(
    filing: dict[str, str],
    holdings: list[dict[str, Any]],
    source_url: str,
    metadata: dict[str, dict[str, str]],
) -> dict[str, Any]:
    total = sum((row["value_usd"] for row in holdings), Decimal(0))
    if total <= 0:
        raise ValueError("13F disclosed value must be positive")
    normalized = []
    for row in holdings:
        security_meta = metadata.get(row["cusip"], {})
        normalized.append(
            {
                **row,
                "ticker": security_meta.get("ticker") or None,
                "theme": security_meta.get("theme") or None,
                "weight_pct": row["value_usd"] / total * Decimal(100),
            }
        )
    normalized.sort(key=lambda row: (-row["value_usd"], row["issuer"], row["security_id"]))
    return {
        **filing,
        "source_url": source_url,
        "total_value_usd": int(total),
        "holdings_count": len(normalized),
        "holdings": normalized,
    }


def serialize_holding(row: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if previous is None:
        change = "new"
        share_delta_pct: float | None = None
        previous_weight = Decimal(0)
    else:
        previous_weight = previous["weight_pct"]
        prior_shares = previous["shares"]
        if prior_shares == 0:
            share_delta_pct = None
            change = "unchanged" if row["shares"] == 0 else "added"
        else:
            share_change = (row["shares"] - prior_shares) / prior_shares * Decimal(100)
            share_delta_pct = rounded(share_change)
            change = "added" if share_change > 0 else "reduced" if share_change < 0 else "unchanged"
    return {
        "security_id": row["security_id"],
        "issuer": row["issuer"],
        "ticker": row["ticker"],
        "cusip": row["cusip"],
        "title": row["title"],
        "instrument_type": row["instrument_type"],
        "put_call": row["put_call"],
        "value_usd": int(row["value_usd"]),
        "shares": float(row["shares"]),
        "weight_pct": rounded(row["weight_pct"]),
        "weight_delta_pp": rounded(row["weight_pct"] - previous_weight),
        "share_delta_pct": share_delta_pct,
        "change": change,
        "theme": row["theme"],
    }


def manager_release(manager: Manager, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    latest = snapshots[0]
    previous = snapshots[1] if len(snapshots) > 1 else None
    identity = {
        "slug": manager.slug,
        "firm": manager.firm,
        "person": manager.person,
        "reporting_manager_name": latest["reporting_manager_name"],
        "reporting_manager_cik": manager.reporting_cik,
        "category": manager.category,
        "primary_theme": manager.primary_theme,
        "latest_filing": {
            "form": latest["form"],
            "report_period": latest["report_period"],
            "filed_date": latest["filed_date"],
            "accession": latest["accession"],
            "source_url": latest["source_url"],
        },
    }
    # A holdings report with an aggregate value below the statutory reporting
    # threshold is a strong unit/data-integrity warning. Do not silently apply a
    # multiplier or publish derived dollar metrics.
    if latest["total_value_usd"] < 100_000_000:
        return {
            **identity,
            "status": "source_review",
            "status_reason": "The filed value scale is inconsistent with the expected Form 13F dollar-value contract; derived metrics are withheld pending source review.",
            "disclosed_portfolio_value_usd": None,
            "holdings_count": None,
            "top_five_concentration_pct": None,
            "classification_coverage_pct": 0,
            "holdings": [],
            "changes": [],
            "allocation": [],
            "history": [],
        }
    previous_by_id = {row["security_id"]: row for row in previous["holdings"]} if previous else {}
    current_by_id = {row["security_id"]: row for row in latest["holdings"]}
    holdings = [serialize_holding(row, previous_by_id.get(row["security_id"])) for row in latest["holdings"]]
    changes = [row for row in holdings if row["change"] != "unchanged"]
    if previous:
        for security_id, row in previous_by_id.items():
            if security_id in current_by_id:
                continue
            changes.append(
                {
                    "security_id": security_id,
                    "issuer": row["issuer"],
                    "ticker": row["ticker"],
                    "cusip": row["cusip"],
                    "title": row["title"],
                    "instrument_type": row["instrument_type"],
                    "put_call": row["put_call"],
                    "value_usd": 0,
                    "previous_value_usd": int(row["value_usd"]),
                    "shares": 0,
                    "weight_pct": 0,
                    "weight_delta_pp": rounded(-row["weight_pct"]),
                    "share_delta_pct": -100.0,
                    "change": "exited",
                    "theme": row["theme"],
                }
            )
    change_order = {"new": 0, "added": 1, "reduced": 2, "exited": 3}
    changes.sort(key=lambda row: (change_order[row["change"]], -max(row["value_usd"], row.get("previous_value_usd", 0))))

    allocation_totals: dict[str, Decimal] = {}
    classified_value = Decimal(0)
    for row in latest["holdings"]:
        theme = row["theme"] or "Other / unclassified"
        allocation_totals[theme] = allocation_totals.get(theme, Decimal(0)) + row["value_usd"]
        if row["theme"]:
            classified_value += row["value_usd"]
    allocation = [
        {"label": label, "weight_pct": rounded(value / Decimal(latest["total_value_usd"]) * Decimal(100))}
        for label, value in sorted(allocation_totals.items(), key=lambda item: -item[1])
    ]

    top_ids = [row["security_id"] for row in latest["holdings"][:5]]
    history = []
    for security_id in top_ids:
        current = current_by_id[security_id]
        points = []
        for snapshot in reversed(snapshots):
            row = next((item for item in snapshot["holdings"] if item["security_id"] == security_id), None)
            points.append({"period": snapshot["report_period"], "weight_pct": rounded(row["weight_pct"]) if row else 0})
        history.append({"security_id": security_id, "issuer": current["issuer"], "ticker": current["ticker"], "points": points})

    top_five = sum((row["weight_pct"] for row in latest["holdings"][:5]), Decimal(0))
    return {
        **identity,
        "status": "available",
        "status_reason": None,
        "disclosed_portfolio_value_usd": latest["total_value_usd"],
        "holdings_count": latest["holdings_count"],
        "top_five_concentration_pct": rounded(top_five),
        "classification_coverage_pct": rounded(classified_value / Decimal(latest["total_value_usd"]) * Decimal(100)),
        "holdings": holdings,
        "changes": changes,
        "allocation": allocation,
        "history": history,
    }


def compile_catalog(client: SecClient | ManifestSecClient, metadata: dict[str, dict[str, str]], quarters: int) -> dict[str, Any]:
    managers = []
    periods: set[str] = set()
    filed_dates: list[str] = []
    for manager in MANAGERS:
        submissions = client.get_json(SEC_SUBMISSIONS.format(cik=manager.reporting_cik))
        filings = filing_rows(submissions, quarters)
        if len(filings) < 2:
            raise ValueError(f"{manager.firm} does not have two compatible recent 13F filings")
        snapshots = []
        for filing in filings:
            payload, source_url = information_table_xml(client, manager.reporting_cik, filing["accession"])
            snapshot = compile_snapshot(filing, parse_information_table(payload), source_url, metadata)
            snapshot["reporting_manager_name"] = submissions["name"]
            snapshots.append(snapshot)
        periods.add(snapshots[0]["report_period"])
        filed_dates.append(snapshots[0]["filed_date"])
        managers.append(manager_release(manager, snapshots))
    if len(periods) != 1:
        raise ValueError(f"featured managers do not share a latest reporting period: {sorted(periods)}")
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "release_id": "",
        "source": "SEC EDGAR Form 13F information tables",
        "report_period": periods.pop(),
        "source_fresh_through": max(filed_dates),
        "limitations": [
            "Values and weights cover only securities disclosed in each reporting manager's Form 13F information table; they are not total assets under management.",
            "Form 13F omits many private investments, cash, shorts, derivatives, and non-reportable securities and may include confidential-treatment gaps.",
            "Reported positions belong to the filing manager and do not establish a named person's private holdings, intent, or investment recommendation.",
            "Change labels compare reported share amounts between compatible quarter-end filings; weight changes also reflect market prices.",
            "Share-count changes are not adjusted for corporate actions unless a reviewed adjustment is present in the release metadata.",
            "A manager is withheld when the filed value scale fails deterministic source-integrity checks; Quantify does not guess a correcting multiplier.",
        ],
        "managers": managers,
    }
    canonical = json.dumps(catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    catalog["release_id"] = f"13f-{catalog['report_period']}-{digest[:12]}"
    catalog["manifest_hash"] = digest
    return catalog


def compile_catalog_from_bundle(
    source_manifest_path: Path,
    metadata_path: Path,
    quarters: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    client = ManifestSecClient(source_manifest_path)
    selected_quarters = client.quarters if quarters is None else quarters
    if selected_quarters != client.quarters:
        raise ValueError("requested history depth does not match the investor SEC source manifest")
    try:
        metadata_bytes = metadata_path.read_bytes()
    except OSError as error:
        raise ValueError("investor security metadata is not readable") from error
    catalog = compile_catalog(client, load_metadata(metadata_path), selected_quarters)
    client.assert_complete()
    source_created_at = datetime.fromisoformat(client.created_at.replace("Z", "+00:00"))
    latest_filing_date = datetime.strptime(catalog["source_fresh_through"], "%Y-%m-%d").date()
    if source_created_at.date() < latest_filing_date:
        raise ValueError("investor SEC source creation date cannot precede the latest filing date")
    record = {
        "schema_version": COMPILATION_RECORD_SCHEMA_VERSION,
        "source_manifest_sha256": client.manifest_sha256,
        "source_created_at": client.created_at,
        "security_metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "compiler_contract": SCHEMA_VERSION,
        "quarters": selected_quarters,
        "resource_count": client.resource_count,
        "catalog_release_id": catalog["release_id"],
        "catalog_manifest_hash": catalog["manifest_hash"],
    }
    return catalog, record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-manifest", type=Path, required=True, help="Reviewed investor-sec-source-bundle.v1 manifest; never uses network")
    parser.add_argument("--metadata", type=Path, default=Path("scripts/investor_security_metadata.json"))
    parser.add_argument("--output", type=Path, default=Path("web/src/data/investorCatalog.json"))
    parser.add_argument("--compilation-record", type=Path)
    parser.add_argument("--quarters", type=int)
    args = parser.parse_args()
    if args.quarters is not None and (args.quarters < 2 or args.quarters > 8):
        parser.error("--quarters must be between 2 and 8")
    catalog, record = compile_catalog_from_bundle(args.source_manifest, args.metadata, args.quarters)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.compilation_record:
        args.compilation_record.parent.mkdir(parents=True, exist_ok=True)
        args.compilation_record.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({catalog['release_id']})")


if __name__ == "__main__":
    main()
