from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


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
