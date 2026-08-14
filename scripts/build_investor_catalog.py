#!/usr/bin/env python3
"""Compile a frozen public investor catalog from SEC Form 13F XML filings.

This is an offline release-factory command. It is never called from a browser or
request path. Network acquisition requires an explicit SEC-compliant user agent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{name}"
SCHEMA_VERSION = "investor-catalog.v1"


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


def information_table_xml(client: SecClient, cik: str, accession: str) -> tuple[bytes, str]:
    accession_path = accession.replace("-", "")
    index_url = SEC_ARCHIVES.format(cik=str(int(cik)), accession=accession_path, name="index.json")
    index = client.get_json(index_url)
    candidates = [item["name"] for item in index["directory"]["item"] if item["name"].lower().endswith(".xml")]
    for name in candidates:
        url = SEC_ARCHIVES.format(cik=str(int(cik)), accession=accession_path, name=name)
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


def compile_catalog(client: SecClient, metadata: dict[str, dict[str, str]], quarters: int) -> dict[str, Any]:
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-agent", required=True, help="Application name and contact email for SEC requests")
    parser.add_argument("--metadata", type=Path, default=Path("scripts/investor_security_metadata.json"))
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/investor-sec"))
    parser.add_argument("--output", type=Path, default=Path("web/src/data/investorCatalog.json"))
    parser.add_argument("--quarters", type=int, default=5)
    args = parser.parse_args()
    if args.quarters < 2 or args.quarters > 8:
        parser.error("--quarters must be between 2 and 8")
    catalog = compile_catalog(SecClient(args.user_agent, args.cache_dir), load_metadata(args.metadata), args.quarters)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({catalog['release_id']})")


if __name__ == "__main__":
    main()
