#!/usr/bin/env python3
"""Build a deterministic public-catalog candidate from reviewed local inputs.

This coordinator has no acquisition, publication, deployment, or active-index
mutation path. It writes a complete candidate directory atomically and fails
closed before a candidate becomes visible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.build_crypto_exposure_catalog import compile_catalog as compile_crypto_exposure
    from scripts.build_crypto_exposure_catalog import load_metadata as load_crypto_exposure_metadata
    from scripts.build_etf_flow_catalog import compile_catalog as compile_etf_flows
    from scripts.build_etf_holdings_catalog import compile_catalog as compile_etf_holdings
    from scripts.build_investor_catalog import compile_catalog_from_bundle
except ModuleNotFoundError:  # Direct `python scripts/...` invocation.
    from build_crypto_exposure_catalog import compile_catalog as compile_crypto_exposure
    from build_crypto_exposure_catalog import load_metadata as load_crypto_exposure_metadata
    from build_etf_flow_catalog import compile_catalog as compile_etf_flows
    from build_etf_holdings_catalog import compile_catalog as compile_etf_holdings
    from build_investor_catalog import compile_catalog_from_bundle


CANDIDATE_SCHEMA_VERSION = "public-refresh-candidate.v1"
INDEX_SCHEMA_VERSION = "public-release-index.v2"
INVESTOR_SCHEMA_VERSION = "investor-catalog.v1"
EXPECTED_CATALOGS = {
    "investors", "markets", "macro", "rates", "etf_flows", "etf_holdings",
    "crypto", "crypto_exposure", "earnings", "policy", "events",
}
HEX_64 = set("0123456789abcdef")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not readable JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def valid_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX_64


def parse_run_at(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise ValueError("run_at must be an exact UTC timestamp ending in Z") from error
    return parsed


def validate_investor_catalog(catalog: dict[str, Any]) -> None:
    if catalog.get("schema_version") != INVESTOR_SCHEMA_VERSION:
        raise ValueError("investor catalog schema is unsupported")
    if not isinstance(catalog.get("report_period"), str) or not isinstance(catalog.get("managers"), list):
        raise ValueError("investor catalog scope is incomplete")
    stored_hash = catalog.get("manifest_hash")
    stored_release = catalog.get("release_id")
    if not valid_hash(stored_hash) or not isinstance(stored_release, str):
        raise ValueError("investor catalog replay identity is invalid")
    unsigned = deepcopy(catalog)
    unsigned.pop("manifest_hash", None)
    unsigned["release_id"] = ""
    digest = sha256_bytes(canonical_bytes(unsigned))
    expected_release = f"13f-{catalog['report_period']}-{digest[:12]}"
    if digest != stored_hash or stored_release != expected_release:
        raise ValueError("investor catalog manifest hash does not replay")


def validate_release_index(index: dict[str, Any], investor_catalog: dict[str, Any] | None = None) -> None:
    if index.get("schema_version") != INDEX_SCHEMA_VERSION or not isinstance(index.get("releases"), list):
        raise ValueError("active public release index is unsupported")
    rows = index["releases"]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("active public release index contains an invalid entry")
    by_catalog = {row.get("catalog"): row for row in rows}
    if len(by_catalog) != len(rows) or set(by_catalog) != EXPECTED_CATALOGS:
        raise ValueError("active public release index catalog set is invalid")
    for row in rows:
        if row.get("status") not in {"available", "unavailable", "source_review", "revoked"}:
            raise ValueError("active public release status is invalid")
        if row.get("freshness") not in {"current", "stale", "not_applicable", "unknown"}:
            raise ValueError("active public release freshness is invalid")
        if not isinstance(row.get("limitations"), list) or not row["limitations"]:
            raise ValueError("active public release limitations are required")
        if row["status"] == "available" and (
            not isinstance(row.get("release_id"), str)
            or not valid_hash(row.get("manifest_hash"))
            or not isinstance(row.get("observed_at"), str)
        ):
            raise ValueError("available public release identity is incomplete")
    if investor_catalog is not None:
        investor_binding = by_catalog["investors"]
        if (
            investor_binding.get("status") != "available"
            or investor_binding.get("release_id") != investor_catalog["release_id"]
            or investor_binding.get("manifest_hash") != investor_catalog["manifest_hash"]
        ):
            raise ValueError("investor catalog does not match the active public binding")


def freshness_at(catalog: dict[str, Any], run_at: datetime) -> str:
    fresh_until = catalog.get("fresh_until")
    if not isinstance(fresh_until, str):
        raise ValueError("compiled catalog freshness deadline is missing")
    try:
        deadline = datetime.fromisoformat(fresh_until.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("compiled catalog freshness deadline is invalid") from error
    if deadline.tzinfo is None:
        raise ValueError("compiled catalog freshness deadline must include a timezone")
    return "current" if run_at <= deadline.astimezone(timezone.utc) else "stale"


def parsed_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_temporal_order(
    run_at: datetime,
    active_index: dict[str, Any],
    catalogs: tuple[dict[str, Any], ...],
) -> None:
    if run_at < parsed_timestamp(active_index.get("generated_at"), "active index generation time"):
        raise ValueError("run_at cannot precede the active index generation time")
    for catalog in catalogs:
        if run_at < parsed_timestamp(catalog.get("observed_at"), "compiled catalog observation time"):
            raise ValueError("run_at cannot precede a compiled catalog observation time")
        if run_at < parsed_timestamp(catalog.get("retrieved_at"), "compiled catalog retrieval time"):
            raise ValueError("run_at cannot precede a compiled catalog retrieval time")


def candidate_index(
    active_index: dict[str, Any],
    investor_catalog: dict[str, Any],
    flow_catalog: dict[str, Any],
    holdings_catalog: dict[str, Any],
    run_at: str,
    crypto_exposure_catalog: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result = deepcopy(active_index)
    result["generated_at"] = run_at
    replacements: dict[str, tuple[dict[str, Any], str, str]] = {
        "etf_flows": (flow_catalog, flow_catalog["observed_at"], freshness_at(flow_catalog, parse_run_at(run_at))),
        "etf_holdings": (holdings_catalog, holdings_catalog["observed_at"], freshness_at(holdings_catalog, parse_run_at(run_at))),
    }
    if crypto_exposure_catalog is not None:
        if (
            crypto_exposure_catalog.get("investor_release_id") != investor_catalog.get("release_id")
            or crypto_exposure_catalog.get("investor_manifest_hash") != investor_catalog.get("manifest_hash")
        ):
            raise ValueError("crypto exposure candidate does not bind the investor catalog")
        investor_observed_at = f"{investor_catalog['source_fresh_through']}T00:00:00Z"
        replacements["investors"] = (investor_catalog, investor_observed_at, "not_applicable")
        replacements["crypto_exposure"] = (crypto_exposure_catalog, investor_observed_at, "not_applicable")
    previous: list[dict[str, Any]] = []
    for row in result["releases"]:
        replacement = replacements.get(row["catalog"])
        if replacement is None:
            continue
        compiled, observed_at, freshness = replacement
        previous.append({
            "catalog": row["catalog"],
            "status": row["status"],
            "release_id": row["release_id"],
            "manifest_hash": row["manifest_hash"],
            "observed_at": row["observed_at"],
            "freshness": row["freshness"],
        })
        row.update({
            "status": "available",
            "release_id": compiled["release_id"],
            "manifest_hash": compiled["manifest_hash"],
            "observed_at": observed_at,
            "freshness": freshness,
            "limitations": (
                row["limitations"]
                if row.get("release_id") == compiled["release_id"] and row.get("manifest_hash") == compiled["manifest_hash"]
                else list(compiled["limitations"])
            ),
        })
    return result, previous


def output_record(artifact: str, payload: bytes, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "artifact": artifact,
        "sha256": sha256_bytes(payload),
        "release_id": catalog.get("release_id") if catalog else None,
        "manifest_hash": catalog.get("manifest_hash") if catalog else None,
    }


def build_candidate(
    *,
    investor_catalog_path: Path | None,
    etf_flow_input_path: Path,
    etf_holdings_input_path: Path,
    security_metadata_path: Path,
    active_release_index_path: Path,
    target_directory: Path,
    run_at: str,
    investor_source_manifest_path: Path | None = None,
    crypto_exposure_metadata_path: Path | None = None,
) -> dict[str, Any]:
    parse_run_at(run_at)
    if target_directory.exists():
        raise ValueError("candidate target directory already exists")
    if investor_source_manifest_path is not None and investor_catalog_path is not None:
        raise ValueError("provide either an investor catalog or an investor source manifest, not both")
    if investor_source_manifest_path is None and investor_catalog_path is None:
        raise ValueError("an investor catalog or investor source manifest is required")
    if investor_source_manifest_path is not None and crypto_exposure_metadata_path is None:
        raise ValueError("crypto exposure metadata is required when compiling an investor source bundle")

    inputs = {
        "etf_flow_source": etf_flow_input_path,
        "etf_holdings_source": etf_holdings_input_path,
        "security_metadata": security_metadata_path,
        "active_release_index": active_release_index_path,
    }
    if investor_source_manifest_path is not None:
        inputs["investor_source_manifest"] = investor_source_manifest_path
        assert crypto_exposure_metadata_path is not None
        inputs["crypto_exposure_metadata"] = crypto_exposure_metadata_path
    else:
        assert investor_catalog_path is not None
        inputs["investor_catalog"] = investor_catalog_path
    input_payloads: dict[str, bytes] = {}
    for name, path in inputs.items():
        try:
            input_payloads[name] = path.read_bytes()
        except OSError as error:
            raise ValueError(f"{name} is not readable") from error

    flow_source = load_object(etf_flow_input_path, "ETF flow source")
    holdings_source = load_object(etf_holdings_input_path, "ETF holdings source")
    security_metadata = load_object(security_metadata_path, "security metadata")
    active_index = load_object(active_release_index_path, "active public release index")
    validate_release_index(active_index)
    investor_compilation = None
    crypto_catalog = None
    if investor_source_manifest_path is not None:
        investor_catalog, investor_compilation = compile_catalog_from_bundle(
            investor_source_manifest_path,
            security_metadata_path,
        )
        assert crypto_exposure_metadata_path is not None
        crypto_catalog = compile_crypto_exposure(
            investor_catalog,
            load_crypto_exposure_metadata(crypto_exposure_metadata_path),
        )
        if parse_run_at(run_at) < parsed_timestamp(investor_compilation["source_created_at"], "investor source creation time"):
            raise ValueError("run_at cannot precede the investor source creation time")
    else:
        assert investor_catalog_path is not None
        investor_catalog = load_object(investor_catalog_path, "investor catalog")
    validate_investor_catalog(investor_catalog)
    if investor_source_manifest_path is None:
        validate_release_index(active_index, investor_catalog)

    flow_catalog = compile_etf_flows(flow_source)
    holdings_catalog = compile_etf_holdings(holdings_source, flow_catalog, security_metadata)
    validate_temporal_order(parse_run_at(run_at), active_index, (flow_catalog, holdings_catalog))
    next_index, previous_bindings = candidate_index(
        active_index,
        investor_catalog,
        flow_catalog,
        holdings_catalog,
        run_at,
        crypto_catalog,
    )

    artifacts = {
        "catalogs/investorCatalog.json": pretty_bytes(investor_catalog),
        "catalogs/etfFlowCatalog.json": pretty_bytes(flow_catalog),
        "catalogs/etfHoldingsCatalog.json": pretty_bytes(holdings_catalog),
        "publicReleaseIndex.json": pretty_bytes(next_index),
    }
    output_catalogs = {
        "catalogs/investorCatalog.json": investor_catalog,
        "catalogs/etfFlowCatalog.json": flow_catalog,
        "catalogs/etfHoldingsCatalog.json": holdings_catalog,
    }
    if crypto_catalog is not None:
        artifacts["catalogs/cryptoExposureCatalog.json"] = pretty_bytes(crypto_catalog)
        output_catalogs["catalogs/cryptoExposureCatalog.json"] = crypto_catalog
    if investor_compilation is not None:
        artifacts["catalogs/investorCompilationRecord.json"] = pretty_bytes(investor_compilation)
    output_records = [
        output_record(name, payload, output_catalogs.get(name))
        for name, payload in sorted(artifacts.items())
    ]
    manifest_base = {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "run_id": "",
        "generated_at": run_at,
        "status": "ready_for_review",
        "publication_authorized": False,
        "investor_compilation": investor_compilation,
        "base_release_index_sha256": sha256_bytes(input_payloads["active_release_index"]),
        "inputs": [
            {"input": name, "sha256": sha256_bytes(payload)}
            for name, payload in sorted(input_payloads.items())
        ],
        "outputs": output_records,
        "previous_bindings": previous_bindings,
        "limitations": [
            "This directory is a review candidate and is not an active or approved public release.",
            "The investor catalog is either a hash-validated compiled input or is compiled only from the declared cache-only SEC source bundle.",
            "Promotion and deployment require separate review and explicit authorization.",
        ],
    }
    run_digest = sha256_bytes(canonical_bytes(manifest_base))
    manifest_base["run_id"] = f"public-refresh-{run_at[:10]}-{run_digest[:12]}"
    artifacts["candidateManifest.json"] = pretty_bytes(manifest_base)

    target_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target_directory.name}.", dir=target_directory.parent))
    try:
        for name, payload in artifacts.items():
            destination = temporary / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        if target_directory.exists():
            raise ValueError("candidate target directory already exists")
        os.replace(temporary, target_directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest_base


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    investor_source = parser.add_mutually_exclusive_group(required=True)
    investor_source.add_argument("--investor-catalog", type=Path)
    investor_source.add_argument("--investor-source-manifest", type=Path)
    parser.add_argument("--etf-flow-input", type=Path, required=True)
    parser.add_argument("--etf-holdings-input", type=Path, required=True)
    parser.add_argument("--security-metadata", type=Path, required=True)
    parser.add_argument("--crypto-exposure-metadata", type=Path, default=Path("scripts/crypto_exposure_metadata.json"))
    parser.add_argument("--active-release-index", type=Path, required=True)
    parser.add_argument("--target-directory", type=Path, required=True)
    parser.add_argument("--run-at", required=True, help="Exact UTC timestamp, for example 2026-08-14T02:00:00Z")
    args = parser.parse_args()
    manifest = build_candidate(
        investor_catalog_path=args.investor_catalog,
        etf_flow_input_path=args.etf_flow_input,
        etf_holdings_input_path=args.etf_holdings_input,
        security_metadata_path=args.security_metadata,
        active_release_index_path=args.active_release_index,
        target_directory=args.target_directory,
        run_at=args.run_at,
        investor_source_manifest_path=args.investor_source_manifest,
        crypto_exposure_metadata_path=args.crypto_exposure_metadata if args.investor_source_manifest else None,
    )
    print(f"wrote {args.target_directory} ({manifest['run_id']}; review required)")


if __name__ == "__main__":
    main()
