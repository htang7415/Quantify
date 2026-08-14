#!/usr/bin/env python3
"""Compile a frozen ETF-flow catalog from reviewed SEC Form N-PORT rows.

This offline compiler accepts only exact filed Item B.6 inputs. It computes
monthly net flow as sales plus reinvestment minus redemptions and never derives
flow from a change in net assets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "etf-flow-catalog.v2"
SOURCE_SCHEMA_VERSION = "etf-flow-source.v2"
ALLOWED_TICKERS = {"SPY", "QQQ", "SMH", "IWM", "VGT"}
ALLOWED_HOSTS = {"www.sec.gov", "data.sec.gov"}
MONTH_FIELDS = ("sales_nav_usd", "reinvestment_nav_usd", "redemption_nav_usd")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("ETF flow source must be a JSON object")
    return value


def official_url(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is required")
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"{field} must use an official SEC host")
    return value


def decimal_value(value: Any, field: str) -> Decimal:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must preserve the exact filed decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{field} is not numeric") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be a finite non-negative value")
    return parsed


def iso_date(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} is required")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date") from error
    return value


def compile_catalog(source: dict[str, Any]) -> dict[str, Any]:
    if source.get("schema_version") != SOURCE_SCHEMA_VERSION:
        raise ValueError("ETF flow source schema is unsupported")
    if source.get("source_id") != "sec-form-n-port-datasets":
        raise ValueError("ETF flow source is not approved")
    dataset_url = official_url(source.get("dataset_url"), "dataset_url")
    if not isinstance(source.get("dataset_sha256"), str) or len(source["dataset_sha256"]) != 64:
        raise ValueError("dataset_sha256 is invalid")
    observed_through = iso_date(source.get("observed_through"), "observed_through")
    funds = source.get("funds")
    if not isinstance(funds, list) or len(funds) != len(ALLOWED_TICKERS):
        raise ValueError("ETF flow source must contain the complete initial universe")
    if {fund.get("ticker") for fund in funds if isinstance(fund, dict)} != ALLOWED_TICKERS:
        raise ValueError("ETF flow source contains an unsupported or missing ticker")

    compiled_funds: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for fund in funds:
        if not isinstance(fund, dict):
            raise ValueError("ETF flow fund row is invalid")
        required_strings = (
            "fund_id", "ticker", "name", "category", "registrant_cik", "registrant_name",
            "fund_lei", "accession", "filed_date", "report_date", "net_assets_usd",
            "identity_source_sha256",
        )
        if any(not isinstance(fund.get(field), str) or not fund[field] for field in required_strings):
            raise ValueError("ETF flow fund identity is incomplete")
        if fund["fund_id"] in seen_ids:
            raise ValueError("ETF flow fund IDs must be unique")
        seen_ids.add(fund["fund_id"])
        report_date = iso_date(fund["report_date"], "report_date")
        if report_date > observed_through:
            raise ValueError("ETF flow fund report date cannot exceed observed_through")
        months = fund.get("months")
        if not isinstance(months, list) or len(months) != 3 or len(set(months)) != 3:
            raise ValueError("ETF flow fund must declare three unique months")
        report_month = datetime.fromisoformat(report_date).replace(day=1)
        expected_months = []
        for offset in (2, 1, 0):
            zero_based = report_month.year * 12 + report_month.month - 1 - offset
            year, month_index = divmod(zero_based, 12)
            expected_months.append(f"{year:04d}-{month_index + 1:02d}")
        if months != expected_months:
            raise ValueError("ETF flow fund months must be the three report-date months in chronological order")
        if fund["series_id"] is not None and fund["fund_id"] != f"sec-series:{fund['series_id']}":
            raise ValueError("ETF flow series identity does not match its stable fund ID")
        if fund["series_id"] is not None and not fund.get("class_id"):
            raise ValueError("ETF flow series ticker identity requires a class ID")
        filing_url = official_url(fund.get("source_url"), "source_url")
        identity_url = official_url(fund.get("identity_source_url"), "identity_source_url")
        net_assets = decimal_value(fund["net_assets_usd"], "net_assets_usd")
        rows = fund.get("monthly_inputs")
        if not isinstance(rows, list) or [row.get("month") for row in rows if isinstance(row, dict)] != months:
            raise ValueError("ETF flow monthly inputs must match the declared month order")

        monthly_flows = []
        three_month_net = Decimal("0")
        for row in rows:
            values = {field: decimal_value(row.get(field), field) for field in MONTH_FIELDS}
            net_flow = values["sales_nav_usd"] + values["reinvestment_nav_usd"] - values["redemption_nav_usd"]
            three_month_net += net_flow
            monthly_flows.append({
                "month": row["month"],
                "sales_nav_usd": float(values["sales_nav_usd"]),
                "reinvestment_nav_usd": float(values["reinvestment_nav_usd"]),
                "redemption_nav_usd": float(values["redemption_nav_usd"]),
                "net_flow_usd": float(net_flow),
            })
        compiled_funds.append({
            "fund_id": fund["fund_id"],
            "ticker": fund["ticker"],
            "name": fund["name"],
            "category": fund["category"],
            "registrant_cik": fund["registrant_cik"],
            "registrant_name": fund["registrant_name"],
            "series_id": fund["series_id"],
            "class_id": fund["class_id"],
            "series_name": fund["series_name"],
            "fund_lei": fund["fund_lei"],
            "accession": fund["accession"],
            "filed_date": iso_date(fund["filed_date"], "filed_date"),
            "report_date": report_date,
            "months": months,
            "net_assets_usd": float(net_assets),
            "three_month_net_flow_usd": float(three_month_net),
            "monthly_flows": monthly_flows,
            "source_url": filing_url,
            "identity_source_url": identity_url,
            "identity_source_sha256": fund["identity_source_sha256"],
        })
    compiled_funds.sort(key=lambda fund: (-abs(fund["three_month_net_flow_usd"]), fund["ticker"]))
    published = datetime.fromisoformat(source["dataset_published_at"].replace("Z", "+00:00"))
    fresh_until = (published + timedelta(days=100)).astimezone(timezone.utc)
    source_record = {
        "dataset_period": source["dataset_period"],
        "dataset_url": dataset_url,
        "dataset_sha256": source["dataset_sha256"],
        "observed_through": observed_through,
        "funds": compiled_funds,
    }
    source_record_hash = hashlib.sha256(json.dumps(source_record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "release_id": "",
        "source_record_hash": source_record_hash,
        "dataset_period": source["dataset_period"],
        "dataset_url": dataset_url,
        "dataset_sha256": source["dataset_sha256"],
        "dataset_published_at": source["dataset_published_at"],
        "retrieved_at": source["retrieved_at"],
        "observed_at": f"{observed_through}T00:00:00Z",
        "fresh_until": fresh_until.isoformat().replace("+00:00", "Z"),
        "observed_through": observed_through,
        "scope": "Five U.S. exchange-traded funds with exact Form N-PORT Item B.6 fields from the SEC 2026Q2 dataset; each fund retains its own report date and three-month window.",
        "methodology": "For each filed month, net flow equals the reported net asset value of shares sold plus shares sold through reinvestment minus shares redeemed or repurchased. Three-month net flow is the sum of those three exact monthly results.",
        "limitations": [
            "This is a delayed Form N-PORT filing view, not a daily ETF creation and redemption feed.",
            "Filed sales and redemptions may include exchanges, mergers, acquisitions, liquidations, and non-ETF activity described by Form N-PORT Item B.6.",
            "Net flow is not calculated from a change in net assets and does not establish investor intent or purchases of underlying securities.",
            "Fund report dates are not synchronized: VGT reports through 2026-02-28 while SPY, QQQ, SMH, and IWM report through 2026-03-31.",
            "The initial universe is limited to SPY, QQQ, SMH, IWM, and VGT and is not a ranking of the broader ETF market.",
        ],
        "funds": compiled_funds,
    }
    canonical = json.dumps(catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    catalog["release_id"] = f"etf-flows-{observed_through}-{digest[:12]}"
    catalog["manifest_hash"] = digest
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("web/src/data/etfFlowCatalog.json"))
    args = parser.parse_args()
    catalog = compile_catalog(load_json(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({catalog['release_id']})")


if __name__ == "__main__":
    main()
