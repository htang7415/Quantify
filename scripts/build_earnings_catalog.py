#!/usr/bin/env python3
"""Compile a bounded reported-earnings release from frozen SEC Company Facts.

Only exact comparable facts from one declared accession feed a company record.
The compiler does not retrieve live data, infer guidance, or compare estimates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "earnings-catalog.v1"
SEC_COMPANYFACTS_PREFIX = "https://data.sec.gov/api/xbrl/companyfacts/CIK"


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def decimal_value(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{field} must be numeric") from error
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def fact_rows(payload: dict[str, Any], concept: str, unit: str) -> list[dict[str, Any]]:
    try:
        rows = payload["facts"]["us-gaap"][concept]["units"][unit]
    except (KeyError, TypeError) as error:
        raise ValueError(f"SEC Company Facts is missing us-gaap:{concept} in {unit}") from error
    if not isinstance(rows, list):
        raise ValueError(f"SEC Company Facts rows for {concept} are invalid")
    eligible = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"SEC Company Facts row for {concept} is invalid")
        if row.get("form") != "10-Q" or not re.fullmatch(r"CY\d{4}Q[1-4]", str(row.get("frame", ""))):
            continue
        required = {"start", "end", "val", "accn", "fy", "fp", "filed", "frame"}
        if not required.issubset(row):
            raise ValueError(f"SEC Company Facts row for {concept} is incomplete")
        decimal_value(row["val"], f"{concept} value")
        eligible.append(row)
    if not eligible:
        raise ValueError(f"SEC Company Facts has no eligible quarterly rows for {concept}")
    return eligible


def comparable_pair(revenue_rows: list[dict[str, Any]], eps_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    def identity(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
        return row["accn"], row["start"], row["end"], row["filed"], row["frame"]

    revenue_by_identity = {identity(row): row for row in revenue_rows}
    eps_by_identity = {identity(row): row for row in eps_rows}
    shared = sorted(set(revenue_by_identity) & set(eps_by_identity), key=lambda item: (item[2], item[3], item[4]))
    if not shared:
        raise ValueError("Revenue and diluted EPS do not share an eligible filed quarter")
    current_key = shared[-1]
    current_revenue = revenue_by_identity[current_key]
    current_eps = eps_by_identity[current_key]
    frame_match = re.fullmatch(r"CY(\d{4})Q([1-4])", current_revenue["frame"])
    if not frame_match:
        raise ValueError("Current SEC frame is invalid")
    prior_frame = f"CY{int(frame_match.group(1)) - 1}Q{frame_match.group(2)}"

    def prior(rows: list[dict[str, Any]], current: dict[str, Any]) -> dict[str, Any]:
        matches = [row for row in rows if row["accn"] == current["accn"] and row["frame"] == prior_frame]
        if len(matches) != 1:
            raise ValueError(f"Accession {current['accn']} lacks one exact {prior_frame} comparative fact")
        return matches[0]

    prior_revenue = prior(revenue_rows, current_revenue)
    prior_eps = prior(eps_rows, current_eps)
    if (prior_revenue["start"], prior_revenue["end"], prior_revenue["filed"]) != (prior_eps["start"], prior_eps["end"], prior_eps["filed"]):
        raise ValueError("Prior revenue and diluted EPS periods are incompatible")
    return current_revenue, prior_revenue, current_eps, prior_eps


def percent_change(current: Decimal, prior: Decimal, field: str) -> float:
    if prior == 0:
        raise ValueError(f"{field} prior-year value cannot be zero")
    return float((((current / prior) - 1) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def filing_url(cik: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.html"


def compile_catalog(fixtures_dir: Path, metadata_path: Path) -> dict[str, Any]:
    manifest_path = fixtures_dir / "manifest.json"
    manifest = load_object(manifest_path)
    metadata = load_object(metadata_path)
    if metadata.get("schema_version") != "earnings-company-metadata.v1" or not isinstance(metadata.get("companies"), list):
        raise ValueError("Earnings company metadata is invalid")
    fixture_entries = manifest.get("fixtures")
    if not isinstance(fixture_entries, list):
        raise ValueError("SEC fixture manifest is invalid")
    entries = {entry.get("cik"): entry for entry in fixture_entries if isinstance(entry, dict)}
    companies = []
    source_records = []
    retrieved_values = []
    seen_tickers: set[str] = set()
    for config in metadata["companies"]:
        if not isinstance(config, dict):
            raise ValueError("Earnings company metadata row is invalid")
        ticker = config.get("ticker")
        cik = config.get("cik")
        if not isinstance(ticker, str) or not isinstance(cik, str) or not re.fullmatch(r"\d{10}", cik):
            raise ValueError("Earnings company identity is invalid")
        if ticker in seen_tickers:
            raise ValueError("Earnings tickers must be unique")
        seen_tickers.add(ticker)
        entry = entries.get(cik)
        if not entry:
            raise ValueError(f"SEC fixture manifest does not declare CIK {cik}")
        fixture_name = config.get("fixture")
        if entry.get("path") != fixture_name:
            raise ValueError(f"SEC fixture path does not match metadata for {ticker}")
        source_url = entry.get("source_url")
        expected_url = f"{SEC_COMPANYFACTS_PREFIX}{cik}.json"
        if source_url != expected_url:
            raise ValueError(f"SEC Company Facts source URL is invalid for {ticker}")
        fixture_path = fixtures_dir / str(fixture_name)
        payload_bytes = fixture_path.read_bytes()
        if sha256_bytes(payload_bytes) != entry.get("payload_sha256"):
            raise ValueError(f"SEC fixture hash mismatch for {ticker}")
        payload = json.loads(payload_bytes)
        if not isinstance(payload, dict) or str(payload.get("cik", "")).zfill(10) != cik:
            raise ValueError(f"SEC Company Facts CIK mismatch for {ticker}")
        revenue_concept = str(config.get("revenue_concept"))
        revenue_unit = str(config.get("revenue_unit"))
        eps_concept = str(config.get("eps_concept"))
        eps_unit = str(config.get("eps_unit"))
        current_revenue, prior_revenue, current_eps, prior_eps = comparable_pair(
            fact_rows(payload, revenue_concept, revenue_unit),
            fact_rows(payload, eps_concept, eps_unit),
        )
        if current_revenue["accn"] != current_eps["accn"] or current_revenue["fy"] != current_eps["fy"] or current_revenue["fp"] != current_eps["fp"]:
            raise ValueError(f"Current earnings facts are incompatible for {ticker}")
        revenue_value = decimal_value(current_revenue["val"], "revenue")
        prior_revenue_value = decimal_value(prior_revenue["val"], "prior revenue")
        eps_value = decimal_value(current_eps["val"], "diluted EPS")
        prior_eps_value = decimal_value(prior_eps["val"], "prior diluted EPS")
        accession = current_revenue["accn"]
        companies.append({
            "ticker": ticker,
            "slug": config.get("slug"),
            "cik": cik,
            "name": config.get("name"),
            "fiscal_year": int(current_revenue["fy"]),
            "fiscal_period": current_revenue["fp"],
            "period_start": current_revenue["start"],
            "period_end": current_revenue["end"],
            "prior_year_period_start": prior_revenue["start"],
            "prior_year_period_end": prior_revenue["end"],
            "filed_at": current_revenue["filed"],
            "accession": accession,
            "form": "10-Q",
            "filing_url": filing_url(cik, accession),
            "companyfacts_url": source_url,
            "revenue": {
                "concept": f"us-gaap:{revenue_concept}",
                "unit": revenue_unit,
                "value": float(revenue_value),
                "prior_year_value": float(prior_revenue_value),
                "yoy_change_pct": percent_change(revenue_value, prior_revenue_value, "revenue"),
            },
            "diluted_eps": {
                "concept": f"us-gaap:{eps_concept}",
                "unit": eps_unit,
                "value": float(eps_value),
                "prior_year_value": float(prior_eps_value),
                "yoy_change_pct": percent_change(eps_value, prior_eps_value, "diluted EPS"),
            },
        })
        retrieved_at = entry.get("retrieved_at")
        if not isinstance(retrieved_at, str):
            raise ValueError(f"SEC fixture retrieval time is missing for {ticker}")
        retrieved_values.append(retrieved_at)
        source_records.append({"ticker": ticker, "fixture_sha256": entry["payload_sha256"], "accession": accession})
    if not companies:
        raise ValueError("Earnings release cannot be empty")
    source_binding = {
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "metadata_sha256": sha256_bytes(metadata_path.read_bytes()),
        "records": source_records,
    }
    source_manifest_hash = sha256_bytes(json.dumps(source_binding, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    observed_date = max(company["filed_at"] for company in companies)
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "release_id": "",
        "source_manifest_hash": source_manifest_hash,
        "observed_at": datetime.fromisoformat(observed_date).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_retrieved_at": max(retrieved_values),
        "scope": "Latest exact comparable 10-Q revenue and diluted EPS facts for AAPL and MSFT in the declared frozen SEC Company Facts manifest.",
        "methodology": "For each company, select the latest 10-Q where revenue and diluted EPS share an accession and period. Compare only the same accession's exact prior-year calendar-quarter facts; round percentage changes to one decimal.",
        "limitations": [
            "Reported SEC facts only; no consensus estimates, surprise labels, guidance interpretation, future earnings dates, or price reactions.",
            "Coverage is limited to AAPL and MSFT and does not represent the full Quantify company directory.",
            "Facts and comparisons are frozen at the declared SEC fixture retrieval time; later amendments or filings are outside this release.",
        ],
        "companies": sorted(companies, key=lambda item: item["ticker"]),
    }
    canonical = json.dumps(catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = sha256_bytes(canonical)
    catalog["release_id"] = f"earnings-{observed_date}-{digest[:12]}"
    catalog["manifest_hash"] = digest
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-dir", type=Path, default=Path("fixtures/sec"))
    parser.add_argument("--metadata", type=Path, default=Path("scripts/earnings_company_metadata.json"))
    parser.add_argument("--output", type=Path, default=Path("web/src/data/earningsCatalog.json"))
    args = parser.parse_args()
    catalog = compile_catalog(args.fixtures_dir, args.metadata)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({catalog['release_id']})")


if __name__ == "__main__":
    main()
