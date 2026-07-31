from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from quantify.indexed_release_archive import IndexedReleaseArchive
from quantify.policy_control import PolicyControlPointers, ReleaseGatePolicy, RuntimePolicyBundle
from quantify.release_operations import ReleaseLane, ReviewerApproval, SourceValidation, ReleaseEvaluation, gate_release


ROOT = Path(__file__).parents[1]


def _load(name: str):
    path = ROOT / "deploy" / "aws" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


compiler = _load("compile_research_task_release.py")
validator = _load("validate_research_task_bundle.py")


def _runtime() -> RuntimePolicyBundle:
    return RuntimePolicyBundle("1.0.0", "runtime-v1", "google", "gemini-3.1-flash-lite", "2026-07", "secret-v1", "a" * 64, 1, 4000, 500, ("verify_claims",), (), ("structured_fact",), ("arbitrary_url_fetch", "live_sec_retrieval", "private_document_access", "policy_mutation", "verdict_composition", "trade_execution"), "admission-v1", "cache-v1")


def _gate() -> ReleaseGatePolicy:
    return ReleaseGatePolicy("1.0.0", "gate-v1", 9900, 100, 25, 30, True, True)


def test_bundle_validator_accepts_one_fully_bound_approved_release() -> None:
    indexed = compiler.compile_release(fixtures_directory=ROOT / "fixtures" / "sec", declaration_path=ROOT / "fixtures" / "sec" / "release_v1.json", requests_path=ROOT / "fixtures" / "sec" / "release_v1_requests.json")
    runtime, policy = _runtime(), _gate()
    approval = gate_release(release=indexed.evidence_release, sources=(SourceValidation("sec", True, "b" * 64, 2),), evaluation=ReleaseEvaluation(9950, 50, 10), policy=policy, lane=ReleaseLane.A, reviewer=ReviewerApproval("reviewer", "c" * 64))
    result = validator.validate_bundle(
        archive=IndexedReleaseArchive.dump(indexed), runtime=runtime, gate_policy=policy,
        approval=approval, pointers=PolicyControlPointers(indexed.evidence_release.manifest_hash, runtime.content_hash, policy.content_hash),
    )
    assert result["evidence_release_manifest_hash"] == indexed.evidence_release.manifest_hash
    assert result["release_approval_manifest_hash"] == approval.manifest_hash


def test_bundle_validator_rejects_a_pointer_for_any_other_release() -> None:
    indexed = compiler.compile_release(fixtures_directory=ROOT / "fixtures" / "sec", declaration_path=ROOT / "fixtures" / "sec" / "release_v1.json", requests_path=ROOT / "fixtures" / "sec" / "release_v1_requests.json")
    runtime, policy = _runtime(), _gate()
    approval = gate_release(release=indexed.evidence_release, sources=(SourceValidation("sec", True, "b" * 64, 2),), evaluation=ReleaseEvaluation(9950, 50, 10), policy=policy, lane=ReleaseLane.A, reviewer=ReviewerApproval("reviewer", "c" * 64))
    with pytest.raises(ValueError, match="evidence-release pointer"):
        validator.validate_bundle(
            archive=IndexedReleaseArchive.dump(indexed), runtime=runtime, gate_policy=policy,
            approval=approval, pointers=PolicyControlPointers("d" * 64, runtime.content_hash, policy.content_hash),
        )


def test_compiler_can_emit_a_new_local_archive_for_bundle_validation(tmp_path: Path) -> None:
    archive = tmp_path / "release.archive.json"
    compiler.main([
        "--fixtures-directory", str(ROOT / "fixtures" / "sec"),
        "--release-declaration", str(ROOT / "fixtures" / "sec" / "release_v1.json"),
        "--requests", str(ROOT / "fixtures" / "sec" / "release_v1_requests.json"),
        "--archive-output", str(archive),
    ])
    assert archive.is_file()
    assert len(json.loads(archive.read_text())["indexed_release_manifest_hash"]) == 64
