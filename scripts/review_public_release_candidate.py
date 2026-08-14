#!/usr/bin/env python3
"""Replay, diff, and classify a public release candidate for human review.

The command is read-only except for a new review-record output. It cannot
approve, promote, publish, deploy, or mutate an active release index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

try:
    from scripts.build_public_release_candidate import canonical_bytes, validate_investor_catalog, validate_release_index
except ModuleNotFoundError:  # Direct `python scripts/...` invocation.
    from build_public_release_candidate import canonical_bytes, validate_investor_catalog, validate_release_index


POLICY_SCHEMA = "public-candidate-gate-policy.v1"
REVIEW_SCHEMA = "public-candidate-review.v1"
CATALOG_ARTIFACTS = {
    "investors": "catalogs/investorCatalog.json",
    "etf_flows": "catalogs/etfFlowCatalog.json",
    "etf_holdings": "catalogs/etfHoldingsCatalog.json",
    "crypto_exposure": "catalogs/cryptoExposureCatalog.json",
}
CATALOG_SCHEMAS = {
    "investors": "investor-catalog.v1",
    "etf_flows": "etf-flow-catalog.v2",
    "etf_holdings": "etf-holdings-catalog.v1",
    "crypto_exposure": "crypto-exposure-catalog.v1",
}
ACTIVE_CATALOG_FILES = {
    "investors": "investorCatalog.json",
    "etf_flows": "etfFlowCatalog.json",
    "etf_holdings": "etfHoldingsCatalog.json",
    "crypto_exposure": "cryptoExposureCatalog.json",
}
POLICY_FIELDS = {
    "schema_version", "policy_id", "allowed_changed_catalogs",
    "maximum_manager_scope_change", "maximum_source_review_increase",
    "maximum_manager_value_change_basis_points", "maximum_manager_holdings_change_basis_points",
    "maximum_etf_net_assets_change_basis_points", "require_no_status_regression",
    "require_no_observation_regression", "require_investor_crypto_dependency_rebuild",
    "lane_a_spot_review_required", "lane_b_full_review_required",
}
BINDING_FIELDS = ("catalog", "status", "release_id", "manifest_hash", "observed_at", "freshness")
CATALOG_NAMES = {"investors", "markets", "macro", "rates", "etf_flows", "etf_holdings", "crypto", "crypto_exposure", "earnings", "policy", "events"}
REVIEW_FIELDS = {
    "schema_version", "review_id", "reviewed_at", "candidate_run_id", "candidate_manifest_sha256",
    "base_release_index_sha256", "policy_id", "policy_sha256", "status", "lane",
    "promotion_authorized", "reasons", "catalog_changes", "metrics", "rollback_bindings",
    "artifact_hashes", "manifest_hash",
}


class CandidateReviewError(ValueError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def valid_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def load_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, json.JSONDecodeError) as error:
        raise CandidateReviewError(f"{label} is not readable JSON") from error
    if not isinstance(value, dict):
        raise CandidateReviewError(f"{label} must be a JSON object")
    return value, payload


def utc_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as error:
        raise CandidateReviewError(f"{label} must be an exact UTC timestamp ending in Z") from error
    return parsed


def load_policy(path: Path) -> tuple[dict[str, Any], str]:
    policy, _ = load_object(path, "public candidate gate policy")
    if set(policy) != POLICY_FIELDS or policy.get("schema_version") != POLICY_SCHEMA:
        raise CandidateReviewError("public candidate gate policy contract is invalid")
    if not isinstance(policy.get("policy_id"), str) or not policy["policy_id"]:
        raise CandidateReviewError("public candidate gate policy ID is invalid")
    catalogs = policy.get("allowed_changed_catalogs")
    if not isinstance(catalogs, list) or not catalogs or len(catalogs) != len(set(catalogs)):
        raise CandidateReviewError("public candidate changed-catalog allowlist is invalid")
    if any(catalog not in {"investors", "markets", "macro", "rates", "etf_flows", "etf_holdings", "crypto", "crypto_exposure", "earnings", "policy", "events"} for catalog in catalogs):
        raise CandidateReviewError("public candidate changed-catalog allowlist is invalid")
    integer_fields = (
        "maximum_manager_scope_change", "maximum_source_review_increase",
        "maximum_manager_value_change_basis_points", "maximum_manager_holdings_change_basis_points",
        "maximum_etf_net_assets_change_basis_points",
    )
    if any(type(policy.get(field)) is not int or policy[field] < 0 for field in integer_fields):
        raise CandidateReviewError("public candidate gate thresholds are invalid")
    boolean_fields = (
        "require_no_status_regression", "require_no_observation_regression",
        "require_investor_crypto_dependency_rebuild", "lane_a_spot_review_required",
        "lane_b_full_review_required",
    )
    if any(policy.get(field) is not True for field in boolean_fields):
        raise CandidateReviewError("public candidate non-bypassable policy controls are invalid")
    return policy, sha256_bytes(canonical_bytes(policy))


def binding(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in BINDING_FIELDS}


def valid_binding(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != set(BINDING_FIELDS):
        return False
    if value.get("catalog") not in CATALOG_NAMES or value.get("status") not in {"available", "unavailable", "source_review", "revoked"}:
        return False
    if value.get("freshness") not in {"current", "stale", "not_applicable", "unknown"}:
        return False
    if value.get("release_id") is not None and not isinstance(value["release_id"], str):
        return False
    if value.get("manifest_hash") is not None and not valid_hash(value["manifest_hash"]):
        return False
    if value.get("observed_at") is not None and not isinstance(value["observed_at"], str):
        return False
    if value["status"] == "available" and (not value.get("release_id") or not value.get("manifest_hash") or not value.get("observed_at")):
        return False
    return True


def index_rows(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    try:
        validate_release_index(index)
    except ValueError as error:
        raise CandidateReviewError(str(error)) from error
    return {row["catalog"]: row for row in index["releases"]}


def replay_catalog(catalog_name: str, catalog: dict[str, Any]) -> None:
    if catalog.get("schema_version") != CATALOG_SCHEMAS[catalog_name]:
        raise CandidateReviewError(f"{catalog_name} catalog schema is unsupported")
    if catalog_name == "investors":
        try:
            validate_investor_catalog(catalog)
        except ValueError as error:
            raise CandidateReviewError(str(error)) from error
        return
    stored_hash = catalog.get("manifest_hash")
    stored_release = catalog.get("release_id")
    if not isinstance(stored_hash, str) or len(stored_hash) != 64 or not isinstance(stored_release, str):
        raise CandidateReviewError(f"{catalog_name} catalog replay identity is invalid")
    unsigned = deepcopy(catalog)
    if catalog_name == "etf_holdings":
        unsigned["release_id"] = ""
        unsigned["manifest_hash"] = ""
        expected_release = f"etf-holdings-{catalog.get('dataset_period', '').lower()}-{stored_hash[:12]}"
    else:
        unsigned.pop("manifest_hash", None)
        unsigned["release_id"] = ""
        expected_release = (
            f"etf-flows-{catalog.get('observed_through', '')}-{stored_hash[:12]}"
            if catalog_name == "etf_flows"
            else f"crypto-exposure-{catalog.get('report_period', '')}-{stored_hash[:12]}"
        )
    digest = sha256_bytes(canonical_bytes(unsigned))
    if digest != stored_hash or stored_release != expected_release:
        raise CandidateReviewError(f"{catalog_name} catalog manifest does not replay")


def replay_candidate_manifest(manifest: dict[str, Any]) -> None:
    expected_fields = {
        "schema_version", "run_id", "generated_at", "status", "publication_authorized",
        "investor_compilation", "base_release_index_sha256", "inputs", "outputs",
        "previous_bindings", "limitations",
    }
    if set(manifest) != expected_fields or manifest.get("schema_version") != "public-refresh-candidate.v1":
        raise CandidateReviewError("candidate manifest contract is invalid")
    if manifest.get("status") != "ready_for_review" or manifest.get("publication_authorized") is not False:
        raise CandidateReviewError("candidate manifest review boundary is invalid")
    utc_timestamp(manifest.get("generated_at"), "candidate generation time")
    inputs = manifest.get("inputs")
    if (
        not isinstance(inputs, list) or not inputs
        or any(not isinstance(row, dict) or set(row) != {"input", "sha256"} or not isinstance(row["input"], str) or not row["input"] or not valid_hash(row["sha256"]) for row in inputs)
        or len({row["input"] for row in inputs}) != len(inputs)
    ):
        raise CandidateReviewError("candidate input records are invalid")
    limitations = manifest.get("limitations")
    if not isinstance(limitations, list) or not limitations or any(not isinstance(row, str) or not row for row in limitations):
        raise CandidateReviewError("candidate limitations are invalid")
    replay = deepcopy(manifest)
    replay["run_id"] = ""
    digest = sha256_bytes(canonical_bytes(replay))
    expected_id = f"public-refresh-{manifest['generated_at'][:10]}-{digest[:12]}"
    if manifest.get("run_id") != expected_id:
        raise CandidateReviewError("candidate run ID does not replay")


def verify_candidate_artifacts(candidate_directory: Path, manifest: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise CandidateReviewError("candidate outputs are invalid")
    declared: dict[str, dict[str, Any]] = {}
    artifact_hashes = []
    for record in outputs:
        if not isinstance(record, dict) or set(record) != {"artifact", "sha256", "release_id", "manifest_hash"}:
            raise CandidateReviewError("candidate output record is invalid")
        name = record.get("artifact")
        if not isinstance(name, str) or not name or name in declared or name.startswith("/") or ".." in Path(name).parts:
            raise CandidateReviewError("candidate artifact path is invalid")
        path = (candidate_directory / name).resolve()
        if not path.is_relative_to(candidate_directory.resolve()):
            raise CandidateReviewError("candidate artifact escapes its directory")
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise CandidateReviewError(f"candidate artifact is missing: {name}") from error
        digest = sha256_bytes(payload)
        if digest != record.get("sha256"):
            raise CandidateReviewError(f"candidate artifact hash does not match: {name}")
        declared[name] = record
        artifact_hashes.append({"artifact": name, "sha256": digest})
    actual = {
        str(path.relative_to(candidate_directory))
        for path in candidate_directory.rglob("*")
        if path.is_file() and path.name != "candidateManifest.json"
    }
    if actual != set(declared):
        raise CandidateReviewError("candidate directory contains missing or extra artifacts")
    return declared, sorted(artifact_hashes, key=lambda row: row["artifact"])


def load_and_verify_catalog(path: Path, catalog_name: str, record: dict[str, Any]) -> dict[str, Any]:
    catalog, _ = load_object(path, f"{catalog_name} candidate catalog")
    replay_catalog(catalog_name, catalog)
    if record.get("release_id") != catalog.get("release_id") or record.get("manifest_hash") != catalog.get("manifest_hash"):
        raise CandidateReviewError(f"{catalog_name} output record does not bind its catalog")
    return catalog


def percentage_change_basis_points(previous: Any, candidate: Any) -> int | None:
    if previous is None or candidate is None:
        return None
    old = Decimal(str(previous))
    new = Decimal(str(candidate))
    if old == 0:
        return 0 if new == 0 else None
    return int(((new - old) / abs(old) * Decimal(10_000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def investor_metrics(active: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    previous = {row["reporting_manager_cik"]: row for row in active["managers"]}
    current = {row["reporting_manager_cik"]: row for row in candidate["managers"]}
    shared = sorted(set(previous) & set(current))
    managers = []
    for cik in shared:
        old, new = previous[cik], current[cik]
        managers.append({
            "reporting_manager_cik": cik,
            "firm": new["firm"],
            "previous_status": old["status"],
            "candidate_status": new["status"],
            "value_change_basis_points": percentage_change_basis_points(old["disclosed_portfolio_value_usd"], new["disclosed_portfolio_value_usd"]),
            "holdings_change_basis_points": percentage_change_basis_points(old["holdings_count"], new["holdings_count"]),
        })
    previous_review = sum(row["status"] == "source_review" for row in previous.values())
    candidate_review = sum(row["status"] == "source_review" for row in current.values())
    return {
        "previous_report_period": active["report_period"],
        "candidate_report_period": candidate["report_period"],
        "previous_manager_count": len(previous),
        "candidate_manager_count": len(current),
        "added_manager_ciks": sorted(set(current) - set(previous)),
        "removed_manager_ciks": sorted(set(previous) - set(current)),
        "previous_source_review_count": previous_review,
        "candidate_source_review_count": candidate_review,
        "source_review_increase": candidate_review - previous_review,
        "previous_total_holdings": sum(row["holdings_count"] or 0 for row in previous.values()),
        "candidate_total_holdings": sum(row["holdings_count"] or 0 for row in current.values()),
        "managers": managers,
    }


def etf_flow_metrics(active: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    previous = {row["ticker"]: row for row in active["funds"]}
    current = {row["ticker"]: row for row in candidate["funds"]}
    return {
        "added_funds": sorted(set(current) - set(previous)),
        "removed_funds": sorted(set(previous) - set(current)),
        "funds": [{
            "ticker": ticker,
            "net_assets_change_basis_points": percentage_change_basis_points(previous[ticker]["net_assets_usd"], current[ticker]["net_assets_usd"]),
        } for ticker in sorted(set(previous) & set(current))],
    }


def etf_holdings_metrics(active: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    previous = {row["ticker"]: row for row in active["funds"]}
    current = {row["ticker"]: row for row in candidate["funds"]}
    return {
        "added_funds": sorted(set(current) - set(previous)),
        "removed_funds": sorted(set(previous) - set(current)),
        "funds": [{
            "ticker": ticker,
            "previous_published_rows": previous[ticker]["published_holding_rows"],
            "candidate_published_rows": current[ticker]["published_holding_rows"],
        } for ticker in sorted(set(previous) & set(current))],
    }


def classify(
    *,
    policy: dict[str, Any],
    changes: list[dict[str, Any]],
    investor: dict[str, Any],
    flows: dict[str, Any],
    holdings: dict[str, Any],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    changed_catalogs = [row["catalog"] for row in changes if row["changed"]]
    for catalog in changed_catalogs:
        if catalog not in policy["allowed_changed_catalogs"]:
            reasons.append(f"catalog_not_routine:{catalog}")
    scope_change = len(investor["added_manager_ciks"]) + len(investor["removed_manager_ciks"])
    if scope_change > policy["maximum_manager_scope_change"]:
        reasons.append("investor_manager_scope_change")
    if investor["source_review_increase"] > policy["maximum_source_review_increase"]:
        reasons.append("investor_source_review_increase")
    if investor["candidate_report_period"] < investor["previous_report_period"]:
        reasons.append("investor_report_period_regression")
    for manager in investor["managers"]:
        cik = manager["reporting_manager_cik"]
        if manager["previous_status"] == "available" and manager["candidate_status"] != "available":
            reasons.append(f"investor_status_regression:{cik}")
        if manager["previous_status"] != "available" or manager["candidate_status"] != "available":
            continue
        value_change = manager["value_change_basis_points"]
        if value_change is None or abs(value_change) > policy["maximum_manager_value_change_basis_points"]:
            reasons.append(f"manager_value_change_threshold:{cik}")
        holdings_change = manager["holdings_change_basis_points"]
        if holdings_change is None or abs(holdings_change) > policy["maximum_manager_holdings_change_basis_points"]:
            reasons.append(f"manager_holdings_change_threshold:{cik}")
    if flows["added_funds"] or flows["removed_funds"]:
        reasons.append("etf_flow_fund_scope_change")
    for fund in flows["funds"]:
        change = fund["net_assets_change_basis_points"]
        if change is None or abs(change) > policy["maximum_etf_net_assets_change_basis_points"]:
            reasons.append(f"etf_net_assets_change_threshold:{fund['ticker']}")
    if holdings["added_funds"] or holdings["removed_funds"]:
        reasons.append("etf_holdings_fund_scope_change")
    if any(row["previous_published_rows"] != row["candidate_published_rows"] for row in holdings["funds"]):
        reasons.append("etf_published_row_count_change")
    for change in changes:
        previous, candidate = change["previous"], change["candidate"]
        if previous["status"] == "available" and candidate["status"] != "available":
            reasons.append(f"catalog_status_regression:{change['catalog']}")
        if previous["observed_at"] and candidate["observed_at"] and candidate["observed_at"] < previous["observed_at"]:
            reasons.append(f"catalog_observation_regression:{change['catalog']}")
        if candidate["freshness"] == "stale":
            reasons.append(f"catalog_stale:{change['catalog']}")
    if not reasons:
        reasons.append("routine_thresholds_passed")
    if not changed_catalogs:
        reasons.append("no_release_identity_change")
    lane = "lane_b" if any(reason not in {"routine_thresholds_passed", "no_release_identity_change"} for reason in reasons) else "lane_a"
    return lane, reasons


def replay_review_record(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != REVIEW_FIELDS or value.get("schema_version") != REVIEW_SCHEMA:
        raise CandidateReviewError("public candidate review record contract is invalid")
    if value.get("promotion_authorized") is not False or value.get("lane") not in {"lane_a", "lane_b"}:
        raise CandidateReviewError("public candidate review boundary is invalid")
    expected_status = "requires_spot_review" if value["lane"] == "lane_a" else "requires_full_review"
    if value.get("status") != expected_status:
        raise CandidateReviewError("public candidate review status is invalid")
    utc_timestamp(value.get("reviewed_at"), "review time")
    reasons = value.get("reasons")
    if not isinstance(reasons, list) or not reasons or len(reasons) != len(set(reasons)) or any(not isinstance(reason, str) or not reason for reason in reasons):
        raise CandidateReviewError("public candidate review reasons are invalid")
    changes = value.get("catalog_changes")
    if not isinstance(changes, list) or len(changes) != len(CATALOG_NAMES):
        raise CandidateReviewError("public candidate catalog changes are invalid")
    change_catalogs: set[str] = set()
    for change in changes:
        if (
            not isinstance(change, dict) or set(change) != {"catalog", "changed", "previous", "candidate"}
            or change.get("catalog") not in CATALOG_NAMES or change["catalog"] in change_catalogs
            or type(change.get("changed")) is not bool
            or not valid_binding(change.get("previous")) or not valid_binding(change.get("candidate"))
            or change["previous"]["catalog"] != change["catalog"] or change["candidate"]["catalog"] != change["catalog"]
            or change["changed"] != (change["previous"] != change["candidate"])
        ):
            raise CandidateReviewError("public candidate catalog changes are invalid")
        change_catalogs.add(change["catalog"])
    metrics = value.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != {"identity_change_count", "investors", "etf_flows", "etf_holdings", "crypto_dependency"}:
        raise CandidateReviewError("public candidate review metrics are invalid")
    if type(metrics.get("identity_change_count")) is not int or metrics["identity_change_count"] != sum(change["changed"] for change in changes):
        raise CandidateReviewError("public candidate identity-change count is invalid")
    crypto = metrics.get("crypto_dependency")
    if (
        not isinstance(crypto, dict)
        or set(crypto) != {"investor_changed", "crypto_exposure_changed", "rebuild_required", "binding_valid"}
        or any(type(crypto.get(field)) is not bool for field in crypto)
        or crypto["binding_valid"] is not True
        or crypto["rebuild_required"] != crypto["investor_changed"]
    ):
        raise CandidateReviewError("public candidate crypto dependency metrics are invalid")
    rollback = value.get("rollback_bindings")
    if not isinstance(rollback, list) or any(not valid_binding(row) for row in rollback) or len({row["catalog"] for row in rollback}) != len(rollback):
        raise CandidateReviewError("public candidate rollback bindings are invalid")
    artifacts = value.get("artifact_hashes")
    if (
        not isinstance(artifacts, list) or not artifacts
        or any(not isinstance(row, dict) or set(row) != {"artifact", "sha256"} or not isinstance(row["artifact"], str) or not row["artifact"] or not valid_hash(row["sha256"]) for row in artifacts)
        or len({row["artifact"] for row in artifacts}) != len(artifacts)
    ):
        raise CandidateReviewError("public candidate artifact hashes are invalid")
    stored_hash = value.get("manifest_hash")
    replay = deepcopy(value)
    replay["manifest_hash"] = ""
    if not isinstance(stored_hash, str) or sha256_bytes(canonical_bytes(replay)) != stored_hash:
        raise CandidateReviewError("public candidate review manifest does not replay")
    identity = deepcopy(replay)
    identity["review_id"] = ""
    identity_digest = sha256_bytes(canonical_bytes(identity))
    expected_id = f"public-candidate-review-{value['reviewed_at'][:10]}-{identity_digest[:12]}"
    if value.get("review_id") != expected_id:
        raise CandidateReviewError("public candidate review ID does not replay")
    return value


def review_candidate(
    *,
    candidate_directory: Path,
    active_release_index_path: Path,
    active_catalog_directory: Path,
    policy_path: Path,
    reviewed_at: str,
) -> dict[str, Any]:
    utc_timestamp(reviewed_at, "review time")
    policy, policy_hash = load_policy(policy_path)
    manifest, manifest_payload = load_object(candidate_directory / "candidateManifest.json", "candidate manifest")
    replay_candidate_manifest(manifest)
    if utc_timestamp(reviewed_at, "review time") < utc_timestamp(manifest["generated_at"], "candidate generation time"):
        raise CandidateReviewError("review time cannot precede candidate generation time")
    declared, artifact_hashes = verify_candidate_artifacts(candidate_directory, manifest)
    input_hashes = {row["input"]: row["sha256"] for row in manifest["inputs"]}
    expected_inputs = {"active_release_index", "etf_flow_source", "etf_holdings_source", "security_metadata"}
    if manifest.get("investor_compilation") is None:
        expected_inputs.add("investor_catalog")
    else:
        expected_inputs.update({"investor_source_manifest", "crypto_exposure_metadata"})
    if set(input_hashes) != expected_inputs:
        raise CandidateReviewError("candidate input set is invalid")
    expected_artifacts = {
        "catalogs/investorCatalog.json", "catalogs/etfFlowCatalog.json",
        "catalogs/etfHoldingsCatalog.json", "publicReleaseIndex.json",
    }
    if manifest.get("investor_compilation") is not None:
        expected_artifacts.update({"catalogs/cryptoExposureCatalog.json", "catalogs/investorCompilationRecord.json"})
    if set(declared) != expected_artifacts:
        raise CandidateReviewError("candidate artifact set is invalid")
    active_index, active_index_payload = load_object(active_release_index_path, "active public release index")
    active_rows = index_rows(active_index)
    if (
        sha256_bytes(active_index_payload) != manifest.get("base_release_index_sha256")
        or input_hashes["active_release_index"] != manifest.get("base_release_index_sha256")
    ):
        raise CandidateReviewError("candidate base release index hash does not match")
    candidate_index_record = declared.get("publicReleaseIndex.json")
    if candidate_index_record is None:
        raise CandidateReviewError("candidate public release index is missing")
    if candidate_index_record.get("release_id") is not None or candidate_index_record.get("manifest_hash") is not None:
        raise CandidateReviewError("candidate public release index output identity is invalid")
    candidate_index, _ = load_object(candidate_directory / "publicReleaseIndex.json", "candidate public release index")
    candidate_rows = index_rows(candidate_index)
    if candidate_index.get("generated_at") != manifest.get("generated_at"):
        raise CandidateReviewError("candidate index generation time does not match its manifest")

    candidate_catalogs: dict[str, dict[str, Any]] = {}
    active_catalogs: dict[str, dict[str, Any]] = {}
    for catalog, artifact in CATALOG_ARTIFACTS.items():
        record = declared.get(artifact)
        if record is not None:
            candidate_catalogs[catalog] = load_and_verify_catalog(candidate_directory / artifact, catalog, record)
        active_path = active_catalog_directory / ACTIVE_CATALOG_FILES[catalog]
        active_catalog, _ = load_object(active_path, f"active {catalog} catalog")
        replay_catalog(catalog, active_catalog)
        active_catalogs[catalog] = active_catalog
        active_binding = active_rows[catalog]
        if active_binding["release_id"] != active_catalog["release_id"] or active_binding["manifest_hash"] != active_catalog["manifest_hash"]:
            raise CandidateReviewError(f"active {catalog} catalog does not match the active index")

    previous_bindings = manifest.get("previous_bindings")
    if not isinstance(previous_bindings, list) or any(not isinstance(row, dict) or set(row) != set(BINDING_FIELDS) for row in previous_bindings):
        raise CandidateReviewError("candidate rollback bindings are invalid")
    previous_by_catalog = {row["catalog"]: row for row in previous_bindings}
    if len(previous_by_catalog) != len(previous_bindings):
        raise CandidateReviewError("candidate rollback catalogs must be unique")
    expected_rollback_catalogs = {"etf_flows", "etf_holdings"}
    if manifest.get("investor_compilation") is not None:
        expected_rollback_catalogs.update({"investors", "crypto_exposure"})
    if set(previous_by_catalog) != expected_rollback_catalogs:
        raise CandidateReviewError("candidate rollback catalog set is invalid")
    for catalog, row in active_rows.items():
        if catalog in previous_by_catalog:
            if previous_by_catalog[catalog] != binding(row):
                raise CandidateReviewError(f"candidate rollback binding does not match active {catalog}")
        elif candidate_rows[catalog] != row:
            raise CandidateReviewError(f"candidate changed {catalog} without a rollback binding")

    for catalog, candidate_catalog in candidate_catalogs.items():
        row = candidate_rows[catalog]
        if row["release_id"] != candidate_catalog["release_id"] or row["manifest_hash"] != candidate_catalog["manifest_hash"]:
            raise CandidateReviewError(f"candidate {catalog} catalog does not match the candidate index")
        identity_changed = (
            candidate_catalog["release_id"] != active_rows[catalog]["release_id"]
            or candidate_catalog["manifest_hash"] != active_rows[catalog]["manifest_hash"]
        )
        if identity_changed:
            if row["limitations"] != candidate_catalog["limitations"]:
                raise CandidateReviewError(f"candidate {catalog} limitations do not match its catalog")
        elif row != active_rows[catalog]:
            raise CandidateReviewError(f"candidate changed {catalog} index metadata without a new release identity")

    compilation = manifest.get("investor_compilation")
    if compilation is not None:
        compilation_fields = {
            "schema_version", "source_manifest_sha256", "source_created_at", "security_metadata_sha256",
            "compiler_contract", "quarters", "resource_count", "catalog_release_id", "catalog_manifest_hash",
        }
        if (
            not isinstance(compilation, dict) or set(compilation) != compilation_fields
            or compilation.get("schema_version") != "investor-compilation-record.v1"
            or compilation.get("compiler_contract") != "investor-catalog.v1"
            or not valid_hash(compilation.get("source_manifest_sha256"))
            or not valid_hash(compilation.get("security_metadata_sha256"))
            or type(compilation.get("quarters")) is not int or not 2 <= compilation["quarters"] <= 8
            or type(compilation.get("resource_count")) is not int or compilation["resource_count"] < 1
            or compilation.get("catalog_release_id") != candidate_catalogs["investors"]["release_id"]
            or compilation.get("catalog_manifest_hash") != candidate_catalogs["investors"]["manifest_hash"]
        ):
            raise CandidateReviewError("candidate investor compilation record does not bind the investor catalog")
        if compilation["source_manifest_sha256"] != input_hashes["investor_source_manifest"] or compilation["security_metadata_sha256"] != input_hashes["security_metadata"]:
            raise CandidateReviewError("candidate investor compilation inputs do not match the candidate manifest")
        compilation_output = declared["catalogs/investorCompilationRecord.json"]
        if compilation_output.get("release_id") is not None or compilation_output.get("manifest_hash") is not None:
            raise CandidateReviewError("candidate investor compilation output identity is invalid")
        compilation_artifact, _ = load_object(candidate_directory / "catalogs/investorCompilationRecord.json", "investor compilation record")
        if compilation_artifact != compilation:
            raise CandidateReviewError("candidate investor compilation record does not replay")
    else:
        try:
            active_investor_payload = (active_catalog_directory / ACTIVE_CATALOG_FILES["investors"]).read_bytes()
        except OSError as error:
            raise CandidateReviewError("active investor catalog is not readable") from error
        if input_hashes["investor_catalog"] != sha256_bytes(active_investor_payload):
            raise CandidateReviewError("candidate pinned investor input does not match the active catalog")

    selected_crypto = candidate_catalogs.get("crypto_exposure", active_catalogs["crypto_exposure"])
    selected_investor = candidate_catalogs["investors"]
    investor_changed = binding(active_rows["investors"]) != binding(candidate_rows["investors"])
    crypto_changed = binding(active_rows["crypto_exposure"]) != binding(candidate_rows["crypto_exposure"])
    crypto_dependency_valid = (
        selected_crypto.get("investor_release_id") == selected_investor.get("release_id")
        and selected_crypto.get("investor_manifest_hash") == selected_investor.get("manifest_hash")
    )
    if not crypto_dependency_valid or (investor_changed and not crypto_changed):
        raise CandidateReviewError("candidate investor-to-crypto dependency is invalid")

    catalog_changes = [{
        "catalog": catalog,
        "changed": binding(active_rows[catalog]) != binding(candidate_rows[catalog]),
        "previous": binding(active_rows[catalog]),
        "candidate": binding(candidate_rows[catalog]),
    } for catalog in sorted(active_rows)]
    investor_diff = investor_metrics(active_catalogs["investors"], selected_investor)
    flow_diff = etf_flow_metrics(active_catalogs["etf_flows"], candidate_catalogs["etf_flows"])
    holdings_diff = etf_holdings_metrics(active_catalogs["etf_holdings"], candidate_catalogs["etf_holdings"])
    crypto_dependency = {
        "investor_changed": investor_changed,
        "crypto_exposure_changed": crypto_changed,
        "rebuild_required": investor_changed,
        "binding_valid": crypto_dependency_valid,
    }
    lane, reasons = classify(
        policy=policy,
        changes=catalog_changes,
        investor=investor_diff,
        flows=flow_diff,
        holdings=holdings_diff,
    )
    record = {
        "schema_version": REVIEW_SCHEMA,
        "review_id": "",
        "reviewed_at": reviewed_at,
        "candidate_run_id": manifest["run_id"],
        "candidate_manifest_sha256": sha256_bytes(manifest_payload),
        "base_release_index_sha256": sha256_bytes(active_index_payload),
        "policy_id": policy["policy_id"],
        "policy_sha256": policy_hash,
        "status": "requires_spot_review" if lane == "lane_a" else "requires_full_review",
        "lane": lane,
        "promotion_authorized": False,
        "reasons": reasons,
        "catalog_changes": catalog_changes,
        "metrics": {
            "identity_change_count": sum(row["changed"] for row in catalog_changes),
            "investors": investor_diff,
            "etf_flows": flow_diff,
            "etf_holdings": holdings_diff,
            "crypto_dependency": crypto_dependency,
        },
        "rollback_bindings": previous_bindings,
        "artifact_hashes": artifact_hashes,
        "manifest_hash": "",
    }
    identity_digest = sha256_bytes(canonical_bytes(record))
    record["review_id"] = f"public-candidate-review-{reviewed_at[:10]}-{identity_digest[:12]}"
    record["manifest_hash"] = sha256_bytes(canonical_bytes(record))
    return replay_review_record(record)


def write_review_record(record: dict[str, Any], output_path: Path) -> None:
    if output_path.exists():
        raise CandidateReviewError("review output already exists")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output_path.name}.", dir=output_path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
        if output_path.exists():
            raise CandidateReviewError("review output already exists")
        os.replace(temporary_name, output_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-directory", type=Path, required=True)
    parser.add_argument("--active-release-index", type=Path, required=True)
    parser.add_argument("--active-catalog-directory", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=Path("policies/public_candidate_gate_policy.v1.json"))
    parser.add_argument("--reviewed-at", required=True, help="Exact UTC review timestamp ending in Z")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = review_candidate(
        candidate_directory=args.candidate_directory,
        active_release_index_path=args.active_release_index,
        active_catalog_directory=args.active_catalog_directory,
        policy_path=args.policy,
        reviewed_at=args.reviewed_at,
    )
    write_review_record(record, args.output)
    print(f"wrote {args.output} ({record['lane']}; {record['status']}; promotion not authorized)")


if __name__ == "__main__":
    main()
