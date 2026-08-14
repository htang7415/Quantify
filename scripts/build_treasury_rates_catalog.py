#!/usr/bin/env python3
"""Compile a frozen U.S. Treasury par-yield release from the official XML feed.

Network acquisition is optional and offline-only. The compiler stores exact
published par yields and one deterministic spread; it does not estimate missing
maturities, forecast rates, or run in a browser/request path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "treasury-rates-catalog.v1"
SOURCE_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=2026"
MATURITIES = (
    ("1M", Decimal("0.0833333333"), "BC_1MONTH"),
    ("2M", Decimal("0.1666666667"), "BC_2MONTH"),
    ("3M", Decimal("0.25"), "BC_3MONTH"),
    ("4M", Decimal("0.3333333333"), "BC_4MONTH"),
    ("6M", Decimal("0.5"), "BC_6MONTH"),
    ("1Y", Decimal("1"), "BC_1YEAR"),
    ("2Y", Decimal("2"), "BC_2YEAR"),
    ("3Y", Decimal("3"), "BC_3YEAR"),
    ("5Y", Decimal("5"), "BC_5YEAR"),
    ("7Y", Decimal("7"), "BC_7YEAR"),
    ("10Y", Decimal("10"), "BC_10YEAR"),
    ("20Y", Decimal("20"), "BC_20YEAR"),
    ("30Y", Decimal("30"), "BC_30YEAR"),
)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def element_text(node: ET.Element, name: str) -> str:
    for child in node.iter():
        if local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def decimal_value(value: str, field: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"Treasury field {field} is not numeric") from error
    if parsed < Decimal("-5") or parsed > Decimal("25"):
        raise ValueError(f"Treasury field {field} is outside the permitted range")
    return parsed


def parse_latest(payload: bytes) -> tuple[str, str, str, dict[str, Decimal]]:
    root = ET.fromstring(payload)
    published_at = element_text(root, "updated")
    if not published_at:
        raise ValueError("Treasury feed publication time is missing")
    candidates: list[tuple[str, str, dict[str, Decimal]]] = []
    for entry in root.iter():
        if local_name(entry.tag) != "entry":
            continue
        observation = element_text(entry, "NEW_DATE")
        record_id = element_text(entry, "id")
        if not observation or not record_id:
            raise ValueError("Treasury entry identity is incomplete")
        values = {field: decimal_value(element_text(entry, field), field) for _, _, field in MATURITIES}
        candidates.append((observation, record_id, values))
    if not candidates:
        raise ValueError("Treasury feed contains no yield observations")
    observation, record_id, values = max(candidates, key=lambda row: row[0])
    return observation, published_at, record_id, values


def compile_catalog(payload: bytes, source_url: str = SOURCE_URL) -> dict[str, Any]:
    if not source_url.startswith("https://home.treasury.gov/"):
        raise ValueError("Treasury source URL must use the official host")
    observation, published_at, record_id, values = parse_latest(payload)
    observed = datetime.fromisoformat(observation).replace(tzinfo=timezone.utc)
    fresh_until = (observed + timedelta(days=3)).replace(hour=23, minute=59, second=59)
    curve = [
        {"maturity": maturity, "years": float(years), "yield_pct": float(values[field])}
        for maturity, years, field in MATURITIES
    ]
    by_maturity = {point["maturity"]: Decimal(str(point["yield_pct"])) for point in curve}
    record = {
        "source_record_id": record_id,
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "published_at": published_at,
        "curve": curve,
    }
    record_hash = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "release_id": "",
        "source_record_hash": record_hash,
        "observed_at": record["observed_at"],
        "published_at": published_at,
        "fresh_until": fresh_until.isoformat().replace("+00:00", "Z"),
        "source_url": source_url,
        "source_record_id": record_id,
        "methodology": "Exact U.S. Treasury daily par yield curve observations; 2s10s equals the published 10-year yield minus the published 2-year yield.",
        "limitations": [
            "Treasury par yields are official interpolated curve observations based on indicative bid-side quotations, not transaction prices.",
            "The release is a dated observation and becomes stale after its declared freshness window.",
            "The 2s10s spread is deterministic arithmetic and is not a forecast or trading signal.",
        ],
        "curve": curve,
        "spreads": [
            {
                "name": "2s10s",
                "value_pp": float(by_maturity["10Y"] - by_maturity["2Y"]),
                "derived_from": ["2Y", "10Y"],
            }
        ],
    }
    canonical = json.dumps(catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    catalog["release_id"] = f"treasury-rates-{record['observed_at'][:10]}-{digest[:12]}"
    catalog["manifest_hash"] = digest
    return catalog


def acquire(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "QuantifyResearchReferee/1.0 public-data-compiler"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-xml", type=Path)
    parser.add_argument("--source-url", default=SOURCE_URL)
    parser.add_argument("--output", type=Path, default=Path("web/src/data/treasuryRatesCatalog.json"))
    parser.add_argument("--authorize-acquisition", action="store_true")
    args = parser.parse_args()
    if args.input_xml and args.authorize_acquisition:
        parser.error("choose --input-xml or --authorize-acquisition, not both")
    if not args.input_xml and not args.authorize_acquisition:
        parser.error("offline compilation requires --input-xml; network acquisition requires --authorize-acquisition")
    payload = args.input_xml.read_bytes() if args.input_xml else acquire(args.source_url)
    catalog = compile_catalog(payload, args.source_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({catalog['release_id']})")


if __name__ == "__main__":
    main()
