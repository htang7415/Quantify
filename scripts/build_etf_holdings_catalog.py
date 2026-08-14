#!/usr/bin/env python3
"""Compile a bounded ETF-holdings catalog from reviewed SEC N-PORT rows."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "etf-holdings-catalog.v1"
SOURCE_SCHEMA_VERSION = "etf-holdings-source.v1"
FLOW_SCHEMA_VERSION = "etf-flow-catalog.v2"
METADATA_SCHEMA_VERSION = "investor-security-metadata.v1"
ALLOWED_TICKERS = {"VGT", "QQQ", "SMH"}
ALLOWED_HOSTS = {"www.sec.gov", "data.sec.gov"}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("ETF holdings input must be a JSON object")
    return value


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def exact_decimal(value: Any, field: str) -> Decimal:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must preserve the exact filed decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{field} is not numeric") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be finite and non-negative")
    return parsed


def iso_date(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} is required")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date") from error
    return value


def official_url(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is required")
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"{field} must use an official SEC host")
    return value


def required_string(row: dict[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"ETF holdings {field} is required")
    return value


def compile_catalog(
    source: dict[str, Any],
    flow_catalog: dict[str, Any],
    security_metadata: dict[str, Any],
) -> dict[str, Any]:
    if source.get("schema_version") != SOURCE_SCHEMA_VERSION:
        raise ValueError("ETF holdings source schema is unsupported")
    if source.get("source_id") != "sec-form-n-port-datasets":
        raise ValueError("ETF holdings source is not approved")
    if source.get("selection_rule") != "top_10_by_filed_percentage_desc":
        raise ValueError("ETF holdings selection rule is unsupported")
    if flow_catalog.get("schema_version") != FLOW_SCHEMA_VERSION:
        raise ValueError("ETF holdings require the active ETF flow contract")
    if security_metadata.get("schema_version") != METADATA_SCHEMA_VERSION:
        raise ValueError("ETF holdings security metadata is unsupported")
    dataset_url = official_url(source.get("dataset_url"), "dataset_url")
    dataset_sha256 = required_string(source, "dataset_sha256")
    if len(dataset_sha256) != 64:
        raise ValueError("ETF holdings dataset hash is invalid")
    if source.get("dataset_period") != flow_catalog.get("dataset_period"):
        raise ValueError("ETF holdings dataset period does not match the ETF flow release")
    if dataset_url != flow_catalog.get("dataset_url") or dataset_sha256 != flow_catalog.get("dataset_sha256"):
        raise ValueError("ETF holdings dataset identity does not match the ETF flow release")
    funds = source.get("funds")
    if not isinstance(funds, list) or len(funds) != len(ALLOWED_TICKERS):
        raise ValueError("ETF holdings source must contain the complete initial universe")
    if {fund.get("ticker") for fund in funds if isinstance(fund, dict)} != ALLOWED_TICKERS:
        raise ValueError("ETF holdings source contains an unsupported or missing ticker")
    flow_funds = {fund["ticker"]: fund for fund in flow_catalog.get("funds", []) if isinstance(fund, dict)}
    metadata_rows = security_metadata.get("securities")
    if not isinstance(metadata_rows, dict):
        raise ValueError("ETF holdings security metadata rows are invalid")

    compiled_funds: list[dict[str, Any]] = []
    for fund in funds:
        if not isinstance(fund, dict):
            raise ValueError("ETF holdings fund row is invalid")
        ticker = required_string(fund, "ticker")
        flow_fund = flow_funds.get(ticker)
        if not flow_fund:
            raise ValueError("ETF holdings fund is not present in the ETF flow release")
        for field in ("fund_id", "name", "accession", "filed_date", "report_date"):
            required_string(fund, field)
        if any(fund[field] != flow_fund[field] for field in ("fund_id", "ticker", "name", "accession", "filed_date", "report_date")):
            raise ValueError("ETF holdings fund identity does not match the ETF flow release")
        net_assets = exact_decimal(fund.get("net_assets_usd"), "net_assets_usd")
        if net_assets != Decimal(str(flow_fund.get("net_assets_usd"))):
            raise ValueError("ETF holdings net assets do not match the ETF flow release")
        total_holding_rows = fund.get("total_holding_rows")
        if not isinstance(total_holding_rows, int) or total_holding_rows < 10:
            raise ValueError("ETF holdings total row count is invalid")
        holdings = fund.get("holdings")
        if not isinstance(holdings, list) or len(holdings) != 10:
            raise ValueError("ETF holdings release requires exactly ten selected rows per fund")

        compiled_holdings: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        filed_percentages: list[Decimal] = []
        for rank, holding in enumerate(holdings, start=1):
            if not isinstance(holding, dict):
                raise ValueError("ETF holding row is invalid")
            holding_id = required_string(holding, "holding_id")
            if holding_id in seen_ids:
                raise ValueError("ETF holding IDs must be unique within a fund")
            seen_ids.add(holding_id)
            for field in ("issuer_name", "issuer_title", "cusip", "unit", "currency_code", "investment_country"):
                required_string(holding, field)
            balance = exact_decimal(holding.get("balance"), "balance")
            currency_value = exact_decimal(holding.get("currency_value"), "currency_value")
            filed_percentage = exact_decimal(holding.get("filed_percentage"), "filed_percentage")
            filed_percentages.append(filed_percentage)
            metadata = metadata_rows.get(holding["cusip"])
            if metadata is not None and not isinstance(metadata, dict):
                raise ValueError("ETF holding security metadata row is invalid")
            ticker_mapping = metadata.get("ticker") if metadata else None
            theme_mapping = metadata.get("theme") if metadata else None
            if ticker_mapping is not None and (not isinstance(ticker_mapping, str) or not ticker_mapping):
                raise ValueError("ETF holding mapped ticker is invalid")
            if theme_mapping is not None and (not isinstance(theme_mapping, str) or not theme_mapping):
                raise ValueError("ETF holding mapped theme is invalid")
            compiled_holdings.append({
                "rank": rank,
                "holding_id": holding_id,
                "issuer_name": holding["issuer_name"],
                "issuer_title": holding["issuer_title"],
                "cusip": holding["cusip"],
                "ticker": ticker_mapping,
                "theme": theme_mapping,
                "balance": float(balance),
                "unit": holding["unit"],
                "currency_code": holding["currency_code"],
                "currency_value": float(currency_value),
                "filed_percentage": float(filed_percentage),
                "investment_country": holding["investment_country"],
            })
        if filed_percentages != sorted(filed_percentages, reverse=True):
            raise ValueError("ETF holdings must be ordered by filed percentage descending")
        compiled_funds.append({
            "fund_id": fund["fund_id"],
            "ticker": ticker,
            "slug": ticker.lower(),
            "name": fund["name"],
            "accession": fund["accession"],
            "filed_date": iso_date(fund["filed_date"], "filed_date"),
            "report_date": iso_date(fund["report_date"], "report_date"),
            "net_assets_usd": float(net_assets),
            "total_holding_rows": total_holding_rows,
            "published_holding_rows": len(compiled_holdings),
            "top_ten_concentration_pct": float(sum(filed_percentages, Decimal("0"))),
            "holdings": compiled_holdings,
            "source_url": flow_fund["source_url"],
        })
    compiled_funds.sort(key=lambda fund: fund["ticker"])
    metadata_hash = canonical_hash(security_metadata)
    source_record = {
        "dataset_period": source["dataset_period"],
        "dataset_sha256": dataset_sha256,
        "flow_release_id": flow_catalog["release_id"],
        "flow_manifest_hash": flow_catalog["manifest_hash"],
        "security_metadata_hash": metadata_hash,
        "funds": compiled_funds,
    }
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "release_id": "",
        "manifest_hash": "",
        "source_record_hash": canonical_hash(source_record),
        "flow_release_id": flow_catalog["release_id"],
        "flow_manifest_hash": flow_catalog["manifest_hash"],
        "security_metadata_hash": metadata_hash,
        "dataset_period": source["dataset_period"],
        "dataset_url": dataset_url,
        "dataset_sha256": dataset_sha256,
        "dataset_published_at": source["dataset_published_at"],
        "retrieved_at": source["retrieved_at"],
        "observed_at": flow_catalog["observed_at"],
        "fresh_until": flow_catalog["fresh_until"],
        "selection_rule": source["selection_rule"],
        "scope": "Top ten filed positions by reported percentage for VGT, QQQ, and SMH from the SEC 2026Q2 Form N-PORT dataset.",
        "methodology": "For each fund, Quantify publishes the ten reviewed FUND_REPORTED_HOLDING rows with the largest exact filed percentage, in descending order. Display tickers and themes are joined only by exact CUSIP from the versioned reviewed security map.",
        "limitations": [
            "This is a delayed top-ten filing snapshot, not a complete or live portfolio.",
            "Filed percentage and currency value are preserved from Form N-PORT and are not current market exposures.",
            "A mapped ticker connects only the exact reviewed security row; missing ticker mappings remain null.",
            "The release does not infer sector allocation, flow attribution, investor intent, market direction, or a recommendation.",
        ],
        "funds": compiled_funds,
    }
    digest = canonical_hash(catalog)
    catalog["release_id"] = f"etf-holdings-2026q2-{digest[:12]}"
    catalog["manifest_hash"] = digest
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--flow-catalog", type=Path, default=Path("web/src/data/etfFlowCatalog.json"))
    parser.add_argument("--metadata", type=Path, default=Path("scripts/investor_security_metadata.json"))
    parser.add_argument("--output", type=Path, default=Path("web/src/data/etfHoldingsCatalog.json"))
    args = parser.parse_args()
    catalog = compile_catalog(load_json(args.input), load_json(args.flow_catalog), load_json(args.metadata))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({catalog['release_id']})")


if __name__ == "__main__":
    main()
