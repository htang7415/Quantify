import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

import scripts.build_investor_catalog as investor_compiler
from scripts.build_public_release_candidate import build_candidate, canonical_bytes
from scripts.review_public_release_candidate import (
    CandidateReviewError,
    classify,
    replay_review_record,
    review_candidate,
    write_review_record,
)
from tests.test_public_release_candidate import RUN_AT, make_investor_source_bundle, paths


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "policies/public_candidate_gate_policy.v2.json"
REVIEWED_AT = "2026-08-14T06:00:00Z"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_pinned_candidate(tmp_path: Path) -> Path:
    candidate = tmp_path / "candidate"
    build_candidate(**paths(), target_directory=candidate, run_at=RUN_AT)
    return candidate


def review(candidate: Path, *, policy: Path = POLICY, active_index: Path | None = None) -> dict:
    return review_candidate(
        candidate_directory=candidate,
        active_release_index_path=active_index or ROOT / "web/src/data/publicReleaseIndex.json",
        active_catalog_directory=ROOT / "web/src/data",
        policy_path=policy,
        reviewed_at=REVIEWED_AT,
    )


def replay_candidate_manifest(path: Path) -> None:
    manifest = load(path)
    manifest["run_id"] = ""
    digest = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    manifest["run_id"] = f"public-refresh-{manifest['generated_at'][:10]}-{digest[:12]}"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def test_no_op_candidate_is_lane_a_but_never_authorized(tmp_path: Path) -> None:
    candidate = build_pinned_candidate(tmp_path)

    first = review(candidate)
    second = review(candidate)

    assert first == second
    assert first["lane"] == "lane_a"
    assert first["status"] == "requires_spot_review"
    assert first["promotion_authorized"] is False
    assert first["metrics"]["identity_change_count"] == 0
    assert first["reasons"] == ["routine_thresholds_passed", "no_release_identity_change"]
    assert {row["catalog"] for row in first["rollback_bindings"]} == {"etf_flows", "etf_holdings"}

    replay = deepcopy(first)
    stored_manifest_hash = replay["manifest_hash"]
    replay["manifest_hash"] = ""
    assert hashlib.sha256(canonical_bytes(replay)).hexdigest() == stored_manifest_hash
    identity = deepcopy(replay)
    identity["review_id"] = ""
    assert first["review_id"].endswith(hashlib.sha256(canonical_bytes(identity)).hexdigest()[:12])
    assert replay_review_record(first) == first
    tampered = deepcopy(first)
    tampered["promotion_authorized"] = True
    with pytest.raises(CandidateReviewError, match="boundary"):
        replay_review_record(tampered)


def test_review_record_write_is_new_only(tmp_path: Path) -> None:
    record = review(build_pinned_candidate(tmp_path))
    output = tmp_path / "review.json"
    write_review_record(record, output)
    assert load(output) == record
    with pytest.raises(CandidateReviewError, match="already exists"):
        write_review_record(record, output)


def test_candidate_artifact_tampering_and_extra_files_fail_closed(tmp_path: Path) -> None:
    candidate = build_pinned_candidate(tmp_path)
    flow = candidate / "catalogs/etfFlowCatalog.json"
    flow.write_bytes(flow.read_bytes() + b" ")
    with pytest.raises(CandidateReviewError, match="artifact hash does not match"):
        review(candidate)

    extra_candidate = build_pinned_candidate(tmp_path / "extra")
    (extra_candidate / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(CandidateReviewError, match="missing or extra"):
        review(extra_candidate)


def test_base_index_and_rollback_must_match_active_bytes(tmp_path: Path) -> None:
    candidate = build_pinned_candidate(tmp_path)
    changed_index = load(ROOT / "web/src/data/publicReleaseIndex.json")
    changed_index["generated_at"] = "2026-08-14T05:59:00Z"
    changed_index_path = tmp_path / "changed-index.json"
    changed_index_path.write_text(json.dumps(changed_index), encoding="utf-8")
    with pytest.raises(CandidateReviewError, match="base release index hash"):
        review(candidate, active_index=changed_index_path)

    manifest_path = candidate / "candidateManifest.json"
    manifest = load(manifest_path)
    manifest["previous_bindings"][0]["release_id"] = "tampered-release"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    replay_candidate_manifest(manifest_path)
    with pytest.raises(CandidateReviewError, match="rollback binding"):
        review(candidate)


def test_manifest_bound_investor_refresh_is_lane_b_and_crypto_bound(tmp_path: Path, monkeypatch) -> None:
    manager = investor_compiler.MANAGERS[0]
    monkeypatch.setattr(investor_compiler, "MANAGERS", (manager,))
    source_manifest = make_investor_source_bundle(tmp_path / "bundle", manager)
    candidate = tmp_path / "candidate"
    build_candidate(
        **{
            **paths(),
            "investor_catalog_path": None,
            "investor_source_manifest_path": source_manifest,
            "crypto_exposure_metadata_path": ROOT / "scripts/crypto_exposure_metadata.json",
        },
        target_directory=candidate,
        run_at=RUN_AT,
    )

    record = review(candidate)

    assert record["lane"] == "lane_b"
    assert record["status"] == "requires_full_review"
    assert record["promotion_authorized"] is False
    assert "investor_manager_scope_change" in record["reasons"]
    assert record["metrics"]["crypto_dependency"] == {
        "investor_changed": True,
        "crypto_exposure_changed": True,
        "rebuild_required": True,
        "binding_valid": True,
    }
    assert record["metrics"]["identity_change_count"] == 2


def test_investor_compilation_cannot_omit_crypto_dependency_artifact(tmp_path: Path, monkeypatch) -> None:
    manager = investor_compiler.MANAGERS[0]
    monkeypatch.setattr(investor_compiler, "MANAGERS", (manager,))
    source_manifest = make_investor_source_bundle(tmp_path / "bundle", manager)
    candidate = tmp_path / "candidate"
    build_candidate(
        **{
            **paths(),
            "investor_catalog_path": None,
            "investor_source_manifest_path": source_manifest,
            "crypto_exposure_metadata_path": ROOT / "scripts/crypto_exposure_metadata.json",
        },
        target_directory=candidate,
        run_at=RUN_AT,
    )
    manifest_path = candidate / "candidateManifest.json"
    manifest = load(manifest_path)
    manifest["outputs"] = [row for row in manifest["outputs"] if row["artifact"] != "catalogs/cryptoExposureCatalog.json"]
    (candidate / "catalogs/cryptoExposureCatalog.json").unlink()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    replay_candidate_manifest(manifest_path)

    with pytest.raises(CandidateReviewError, match="artifact set"):
        review(candidate)


def test_versioned_thresholds_deterministically_route_to_lane_b() -> None:
    policy = load(POLICY)
    changes = [{
        "catalog": "investors",
        "changed": True,
        "previous": {"status": "available", "observed_at": "2026-01-01T00:00:00Z", "freshness": "not_applicable"},
        "candidate": {"status": "available", "observed_at": "2026-04-01T00:00:00Z", "freshness": "not_applicable"},
    }]
    investors = {
        "added_manager_ciks": [], "removed_manager_ciks": [], "source_review_increase": 0,
        "previous_report_period": "2025-12-31", "candidate_report_period": "2026-03-31",
        "managers": [{
            "reporting_manager_cik": "0000000001", "previous_status": "available", "candidate_status": "available",
            "value_change_basis_points": 6001, "holdings_change_basis_points": 0,
        }],
    }
    flows = {"added_funds": [], "removed_funds": [], "funds": []}
    holdings = {"added_funds": [], "removed_funds": [], "funds": []}

    venture = {
        "added_firm_ids": [], "removed_firm_ids": [],
        "added_relationships": [], "removed_relationships": [],
    }
    lane, reasons = classify(policy=policy, changes=changes, investor=investors, flows=flows, holdings=holdings, venture=venture)

    assert lane == "lane_b"
    assert reasons == ["manager_value_change_threshold:0000000001"]


def test_policy_controls_cannot_be_disabled(tmp_path: Path) -> None:
    policy = load(POLICY)
    policy["require_investor_crypto_dependency_rebuild"] = False
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    candidate = build_pinned_candidate(tmp_path)

    with pytest.raises(CandidateReviewError, match="non-bypassable"):
        review(candidate, policy=policy_path)


def test_venture_candidate_is_lane_b_with_exact_scope_metrics(tmp_path: Path) -> None:
    candidate = tmp_path / "venture-candidate"
    source = ROOT / "tests/fixtures/public_data/vc_portfolio_sources_candidate_2026-08-14.json"
    build_candidate(**paths(), target_directory=candidate, run_at=RUN_AT, venture_source_path=source)

    record = review(candidate)

    assert record["lane"] == "lane_b"
    assert record["status"] == "requires_full_review"
    assert record["promotion_authorized"] is False
    assert record["reasons"] == ["venture_full_review_required"]
    assert record["metrics"]["venture"]["added_firm_ids"] == ["general-catalyst", "thrive-capital"]
    assert record["metrics"]["venture"]["removed_firm_ids"] == []
    assert record["metrics"]["venture"]["previous_firm_count"] == 4
    assert record["metrics"]["venture"]["candidate_firm_count"] == 6
    assert record["metrics"]["venture"]["previous_relationship_count"] == 24
    assert record["metrics"]["venture"]["candidate_relationship_count"] == 36
    assert {row["catalog"] for row in record["rollback_bindings"]} == {"venture", "etf_flows", "etf_holdings"}
