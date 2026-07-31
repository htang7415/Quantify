from __future__ import annotations

import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys

import pytest

from quantify.release_factory import build_evidence_release
from quantify.release_operations import ReleaseApprovalRecord, ReleaseLane


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "deploy" / "aws" / "compile_research_task_release.py"
spec = importlib.util.spec_from_file_location("compile_research_task_release", SCRIPT)
compile_research_task_release = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = compile_research_task_release
spec.loader.exec_module(compile_research_task_release)


def test_frozen_v1_release_compiler_builds_and_replays_every_declared_request() -> None:
    release = compile_research_task_release.compile_release(
        fixtures_directory=ROOT / "fixtures" / "sec",
        declaration_path=ROOT / "fixtures" / "sec" / "release_v1.json",
        requests_path=ROOT / "fixtures" / "sec" / "release_v1_requests.json",
    )
    assert release.evidence_release.release_id == "sec-us-large-cap-v1"
    assert len(release.snapshots) == 3
    assert {snapshot.request.cik for snapshot in release.snapshots} == {"0000320193", "0000789019"}


def test_release_compiler_requires_the_complete_declared_issuer_set(tmp_path: Path) -> None:
    requests = {
        "schema_version": "1.0.0",
        "requests": [{"cik": "0000789019", "as_of_date": "2024-07-30", "forms": ["10-K"], "evidence_requests": []}],
    }
    path = tmp_path / "requests.json"
    path.write_text(json.dumps(requests))
    with pytest.raises(ValueError, match="exactly the declared issuers"):
        compile_research_task_release.compile_release(
            fixtures_directory=ROOT / "fixtures" / "sec",
            declaration_path=ROOT / "fixtures" / "sec" / "release_v1.json",
            requests_path=path,
        )


def test_release_compiler_validate_only_command_never_constructs_an_aws_client(capsys) -> None:
    compile_research_task_release.main([
        "--fixtures-directory", str(ROOT / "fixtures" / "sec"),
        "--release-declaration", str(ROOT / "fixtures" / "sec" / "release_v1.json"),
        "--requests", str(ROOT / "fixtures" / "sec" / "release_v1_requests.json"),
        "--validate-only",
    ])
    result = json.loads(capsys.readouterr().out)
    assert result["snapshot_count"] == 3
    assert len(result["evidence_release_manifest_hash"]) == 64


def test_release_compiler_requires_a_verified_approval_record_before_cloud_persistence() -> None:
    with pytest.raises(SystemExit, match="2"):
        compile_research_task_release.main([
            "--fixtures-directory", str(ROOT / "fixtures" / "sec"),
            "--release-declaration", str(ROOT / "fixtures" / "sec" / "release_v1.json"),
            "--requests", str(ROOT / "fixtures" / "sec" / "release_v1_requests.json"),
            "--policy-bucket", "private-bucket",
        ])


def test_release_compiler_rejects_a_non_boolean_approval_result(tmp_path: Path) -> None:
    release = build_evidence_release(
        fixtures_directory=ROOT / "fixtures" / "sec", release_id="sec-us-large-cap-v1",
        issuer_ciks=("0000320193", "0000789019"),
        evaluation_corpus=ROOT / "fixtures" / "sec" / "release_v1_requests.json",
    )
    record = ReleaseApprovalRecord(
        release_manifest_hash=release.manifest_hash, release_gate_policy_hash="a" * 64,
        release_gate_record_hash="b" * 64, source_validation_hashes=("c" * 64,),
        evaluation_hash="d" * 64, lane=ReleaseLane.A, reasons=(),
        reviewer_approval_record_hash="e" * 64, approved=True,
    ).as_dict()
    record["approved"] = "true"
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(record))

    with pytest.raises(ValueError, match="approval record is invalid"):
        compile_research_task_release._approved_record(path=path, release=release)


def test_release_compiler_persists_an_immutable_approval_record_before_archive() -> None:
    release = build_evidence_release(
        fixtures_directory=ROOT / "fixtures" / "sec", release_id="sec-us-large-cap-v1",
        issuer_ciks=("0000320193", "0000789019"),
        evaluation_corpus=ROOT / "fixtures" / "sec" / "release_v1_requests.json",
    )
    record = ReleaseApprovalRecord(
        release_manifest_hash=release.manifest_hash, release_gate_policy_hash="a" * 64,
        release_gate_record_hash="b" * 64, source_validation_hashes=("c" * 64,),
        evaluation_hash="d" * 64, lane=ReleaseLane.A, reasons=(),
        reviewer_approval_record_hash="e" * 64, approved=True,
    )
    class _S3:
        def __init__(self): self.objects = {}
        def put_object(self, **kwargs): self.objects[kwargs["Key"]] = kwargs["Body"]
        def get_object(self, **kwargs): return {"Body": BytesIO(self.objects[kwargs["Key"]])}

    client = _S3()
    key = compile_research_task_release.persist_approval_record(
        client=client, bucket_name="private", record=record
    )

    assert key.endswith(f"/{record.manifest_hash}.json")
    assert json.loads(client.objects[key]) == record.as_dict()
