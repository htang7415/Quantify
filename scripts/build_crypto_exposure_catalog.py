#!/usr/bin/env python3
"""Compile crypto-linked ETP exposure from an existing frozen investor catalog.

This compiler performs no network access. Security-to-asset identity is limited
to reviewed metadata backed by SEC filing URLs. Its output does not establish
direct token ownership, fund flows, market prices, or investment intent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "crypto-exposure-catalog.v1"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_metadata(path: Path) -> list[dict[str, Any]]:
    value = load_json(path)
    if value.get("schema_version") != "crypto-exposure-metadata.v1":
        raise ValueError("crypto exposure metadata has an unsupported schema")
    assets = value.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("crypto exposure metadata must declare assets")
    seen_assets: set[str] = set()
    seen_cusips: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict) or not all(asset.get(field) for field in ("asset_id", "slug", "name", "symbol", "network")):
            raise ValueError("crypto asset metadata is incomplete")
        if asset["asset_id"] in seen_assets:
            raise ValueError("crypto asset IDs must be unique")
        seen_assets.add(asset["asset_id"])
        funds = asset.get("funds")
        if not isinstance(funds, list):
            raise ValueError("crypto asset fund mappings must be a list")
        for fund in funds:
            if not isinstance(fund, dict) or not all(fund.get(field) for field in ("cusip", "ticker", "name", "exposure_type", "identity_source_url")):
                raise ValueError("crypto fund metadata is incomplete")
            if fund["exposure_type"] != "exchange_traded_product":
                raise ValueError("unsupported crypto exposure type")
            if fund["cusip"] in seen_cusips:
                raise ValueError("crypto fund CUSIPs must be unique")
            if not fund["identity_source_url"].startswith("https://www.sec.gov/"):
                raise ValueError("crypto fund identity must use an SEC source")
            seen_cusips.add(fund["cusip"])
    return assets


def compile_catalog(investor_catalog: dict[str, Any], assets: list[dict[str, Any]]) -> dict[str, Any]:
    if investor_catalog.get("schema_version") != "investor-catalog.v1":
        raise ValueError("investor catalog has an unsupported schema")
    if not investor_catalog.get("manifest_hash") or not investor_catalog.get("release_id"):
        raise ValueError("investor catalog release identity is required")

    holdings_by_cusip: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for manager in investor_catalog.get("managers", []):
        if manager.get("status") != "available":
            continue
        for holding in manager.get("holdings", []):
            holdings_by_cusip.setdefault(holding["cusip"], []).append((manager, holding))

    compiled_assets = []
    for asset in assets:
        positions = []
        for fund in asset["funds"]:
            for manager, holding in holdings_by_cusip.get(fund["cusip"], []):
                positions.append(
                    {
                        "manager_slug": manager["slug"],
                        "manager_firm": manager["firm"],
                        "reporting_manager_name": manager["reporting_manager_name"],
                        "reporting_manager_cik": manager["reporting_manager_cik"],
                        "fund_ticker": fund["ticker"],
                        "fund_name": fund["name"],
                        "cusip": fund["cusip"],
                        "value_usd": holding["value_usd"],
                        "shares": holding["shares"],
                        "portfolio_weight_pct": holding["weight_pct"],
                        "change": holding["change"],
                        "share_delta_pct": holding["share_delta_pct"],
                        "filing_accession": manager["latest_filing"]["accession"],
                        "filing_source_url": manager["latest_filing"]["source_url"],
                        "identity_source_url": fund["identity_source_url"],
                    }
                )
        positions.sort(key=lambda position: (-position["value_usd"], position["manager_slug"], position["fund_ticker"]))
        compiled_assets.append(
            {
                "asset_id": asset["asset_id"],
                "slug": asset["slug"],
                "name": asset["name"],
                "symbol": asset["symbol"],
                "network": asset["network"],
                "market_data_status": "unavailable",
                "reported_etp_value_usd": sum(position["value_usd"] for position in positions),
                "reporting_manager_count": len({position["manager_slug"] for position in positions}),
                "positions": positions,
            }
        )

    catalog = {
        "schema_version": SCHEMA_VERSION,
        "release_id": "",
        "investor_release_id": investor_catalog["release_id"],
        "investor_manifest_hash": investor_catalog["manifest_hash"],
        "report_period": investor_catalog["report_period"],
        "source": "SEC EDGAR Form 13F information tables and reviewed SEC-filed ETP identity",
        "limitations": [
            "Exposure values cover only crypto-linked exchange-traded products reported by managers in the declared Quantify 13F release.",
            "An ETP position is not direct bitcoin or ether ownership by the reporting manager and does not establish investment intent.",
            "Reported position changes are not ETF flows and are not observed trades.",
            "No crypto spot price, market capitalization, network metric, wallet attribution, or staking yield is included.",
        ],
        "assets": compiled_assets,
    }
    canonical = json.dumps(catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    catalog["release_id"] = f"crypto-exposure-{catalog['report_period']}-{digest[:12]}"
    catalog["manifest_hash"] = digest
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--investor-catalog", type=Path, default=Path("web/src/data/investorCatalog.json"))
    parser.add_argument("--metadata", type=Path, default=Path("scripts/crypto_exposure_metadata.json"))
    parser.add_argument("--output", type=Path, default=Path("web/src/data/cryptoExposureCatalog.json"))
    args = parser.parse_args()
    catalog = compile_catalog(load_json(args.investor_catalog), load_metadata(args.metadata))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({catalog['release_id']})")


if __name__ == "__main__":
    main()
