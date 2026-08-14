#!/usr/bin/env python3
"""Compile a frozen macro release from bounded official BLS API records.

The compiler publishes two deterministic CPI year-over-year calculations and
one exact unemployment-rate observation. Network acquisition is offline-only,
explicitly authorized, and never part of a browser or request path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "bls-macro-catalog.v1"
TERMS_URL = "https://www.bls.gov/developers/termsOfService.htm"
BLS_DISCLAIMER = "BLS.gov cannot vouch for the data or analyses derived from these data after the data have been retrieved from BLS.gov."
SERIES = {
    "headline_cpi_yoy": {
        "series_id": "CUUR0000SA0",
        "label": "Headline CPI",
        "seasonal_adjustment": "not_seasonally_adjusted",
        "derivation": "year_over_year_percent_change",
    },
    "core_cpi_yoy": {
        "series_id": "CUUR0000SA0L1E",
        "label": "Core CPI",
        "seasonal_adjustment": "not_seasonally_adjusted",
        "derivation": "year_over_year_percent_change",
    },
    "unemployment_rate": {
        "series_id": "LNS14000000",
        "label": "Unemployment rate",
        "seasonal_adjustment": "seasonally_adjusted",
        "derivation": "published_value",
    },
}


def decimal_value(value: object, field: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"BLS field {field} must be a string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"BLS field {field} is not numeric") from error
    if parsed < 0 or parsed > Decimal("1000"):
        raise ValueError(f"BLS field {field} is outside the permitted range")
    return parsed


def month_key(year: int, month: int) -> str:
    return f"{year:04d}-M{month:02d}"


def previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def series_records(payload: dict[str, Any]) -> dict[str, tuple[str, dict[str, Decimal]]]:
    source_series = payload.get("series")
    if not isinstance(source_series, list):
        raise ValueError("BLS source series are missing")
    parsed: dict[str, tuple[str, dict[str, Decimal]]] = {}
    for item in source_series:
        if not isinstance(item, dict):
            raise ValueError("BLS source series is invalid")
        series_id = item.get("series_id")
        source_url = item.get("source_url")
        if not isinstance(series_id, str) or not isinstance(source_url, str):
            raise ValueError("BLS series identity is incomplete")
        if source_url != f"https://api.bls.gov/publicAPI/v1/timeseries/data/{series_id}":
            raise ValueError("BLS source URL must be the official series endpoint")
        data = item.get("data")
        if not isinstance(data, list):
            raise ValueError("BLS series data is invalid")
        records: dict[str, Decimal] = {}
        for row in data:
            if not isinstance(row, dict):
                raise ValueError("BLS observation is invalid")
            year = row.get("year")
            period = row.get("period")
            if period == "M13":
                continue
            if not isinstance(year, str) or not isinstance(period, str) or not re.fullmatch(r"M(0[1-9]|1[0-2])", period):
                raise ValueError("BLS observation period is invalid")
            key = f"{year}-{period}"
            if key in records:
                raise ValueError("BLS observation periods must be unique")
            if row.get("value") == "-":
                continue
            records[key] = decimal_value(row.get("value"), f"{series_id} {key}")
        parsed[series_id] = (source_url, records)
    required = {config["series_id"] for config in SERIES.values()}
    if set(parsed) != required:
        raise ValueError("BLS source must contain exactly the declared series")
    return parsed


def rounded_tenth(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def compile_catalog(payload_bytes: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError as error:
        raise ValueError("BLS source payload is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("BLS source payload is invalid")
    retrieved_at = payload.get("retrieved_at")
    if not isinstance(retrieved_at, str):
        raise ValueError("BLS retrieval time is missing")
    retrieved = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    if retrieved.tzinfo is None:
        raise ValueError("BLS retrieval time must include a timezone")
    parsed = series_records(payload)
    latest_keys = []
    for config in SERIES.values():
        records = parsed[config["series_id"]][1]
        latest_keys.append(max(records))
    if len(set(latest_keys)) != 1:
        raise ValueError("BLS series do not share one latest observation period")
    latest_key = latest_keys[0]
    year, month = int(latest_key[:4]), int(latest_key[-2:])
    prior_year = year - 1
    previous_year, previous_month_number = previous_month(year, month)
    observed_at = datetime(year, month, monthrange(year, month)[1], tzinfo=timezone.utc)
    fresh_until = (observed_at + timedelta(days=45)).replace(hour=23, minute=59, second=59)
    observations = []
    for metric_id, config in SERIES.items():
        series_id = config["series_id"]
        source_url, records = parsed[series_id]
        current = records.get(month_key(year, month))
        previous = records.get(month_key(previous_year, previous_month_number))
        if current is None or previous is None:
            raise ValueError(f"BLS series {series_id} is missing the current or previous-month observation")
        inputs = [
            {"period": f"{year:04d}-{month:02d}", "value": float(current)},
            {"period": f"{previous_year:04d}-{previous_month_number:02d}", "value": float(previous)},
        ]
        if config["derivation"] == "year_over_year_percent_change":
            prior = records.get(month_key(prior_year, month))
            prior_previous = records.get(month_key(previous_year - 1, previous_month_number))
            if prior is None or prior_previous is None or prior == 0 or prior_previous == 0:
                raise ValueError(f"BLS series {series_id} is missing exact year-over-year inputs")
            current_value = rounded_tenth(((current / prior) - 1) * 100)
            previous_value = rounded_tenth(((previous / prior_previous) - 1) * 100)
            inputs.extend([
                {"period": f"{prior_year:04d}-{month:02d}", "value": float(prior)},
                {"period": f"{previous_year - 1:04d}-{previous_month_number:02d}", "value": float(prior_previous)},
            ])
        else:
            current_value = rounded_tenth(current)
            previous_value = rounded_tenth(previous)
        observations.append({
            "metric_id": metric_id,
            "label": config["label"],
            "series_id": series_id,
            "value_pct": float(current_value),
            "previous_value_pct": float(previous_value),
            "change_pp": float(rounded_tenth(current_value - previous_value)),
            "period": f"{year:04d}-{month:02d}",
            "previous_period": f"{previous_year:04d}-{previous_month_number:02d}",
            "seasonal_adjustment": config["seasonal_adjustment"],
            "derivation": config["derivation"],
            "source_url": source_url,
            "inputs": inputs,
        })
    canonical_source = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "release_id": "",
        "source_record_hash": hashlib.sha256(canonical_source).hexdigest(),
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "observed_period": f"{year:04d}-{month:02d}",
        "retrieved_at": retrieved_at,
        "fresh_until": fresh_until.isoformat().replace("+00:00", "Z"),
        "terms_url": TERMS_URL,
        "methodology": "Headline and core CPI are deterministic year-over-year percent changes from exact not-seasonally-adjusted BLS index observations, rounded to one decimal. Unemployment is the exact seasonally adjusted BLS published rate.",
        "disclaimer": BLS_DISCLAIMER,
        "limitations": [
            "This is a dated BLS observation release, not a live macroeconomic feed or forecast.",
            "CPI rates are Quantify calculations from the displayed BLS index inputs; unemployment is a published BLS value.",
            "Revisions after the declared retrieval time are outside this immutable release.",
        ],
        "observations": observations,
    }
    canonical = json.dumps(catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    catalog["release_id"] = f"bls-macro-{catalog['observed_period']}-{digest[:12]}"
    catalog["manifest_hash"] = digest
    return catalog


def acquire() -> bytes:
    source_series = []
    for config in SERIES.values():
        series_id = config["series_id"]
        url = f"https://api.bls.gov/publicAPI/v1/timeseries/data/{series_id}"
        request = urllib.request.Request(url, headers={"User-Agent": "QuantifyResearchReferee/1.0 public-data-compiler"})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = json.loads(response.read())
        if raw.get("status") != "REQUEST_SUCCEEDED" or len(raw.get("Results", {}).get("series", [])) != 1:
            raise ValueError(f"BLS request failed for {series_id}")
        source_series.append({"series_id": series_id, "source_url": url, "data": raw["Results"]["series"][0]["data"]})
    payload = {"retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), "series": source_series}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-json", type=Path)
    parser.add_argument("--output", type=Path, default=Path("web/src/data/blsMacroCatalog.json"))
    parser.add_argument("--authorize-acquisition", action="store_true")
    args = parser.parse_args()
    if args.input_json and args.authorize_acquisition:
        parser.error("choose --input-json or --authorize-acquisition, not both")
    if not args.input_json and not args.authorize_acquisition:
        parser.error("offline compilation requires --input-json; network acquisition requires --authorize-acquisition")
    payload = args.input_json.read_bytes() if args.input_json else acquire()
    catalog = compile_catalog(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({catalog['release_id']})")


if __name__ == "__main__":
    main()
