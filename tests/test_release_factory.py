from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from quantify.release_factory import EvidenceReleaseError, build_evidence_release


def _fixtures(tmp_path):
    payload = b'{"cik":"0000789019"}'
    (tmp_path / "msft.json").write_bytes(payload)
    (tmp_path / "manifest.json").write_text(json.dumps({"fixtures": [{"cik": "0000789019", "path": "msft.json", "payload_sha256": sha256(payload).hexdigest()}]}))
    corpus = tmp_path / "evaluation.json"
    corpus.write_text('{"cases":["replayable"]}')
    return corpus


def test_release_factory_pins_fixture_provenance_policy_and_evaluation(tmp_path) -> None:
    corpus = _fixtures(tmp_path)
    release = build_evidence_release(fixtures_directory=tmp_path, release_id="sec-msft-v1", issuer_ciks=("0000789019",), evaluation_corpus=corpus)

    assert len(release.manifest_hash) == 64
    assert release.as_dict()["manifest_hash"] == release.manifest_hash
    assert release.fixture_payload_sha256s[0][0] == "0000789019"


def test_release_factory_rejects_missing_issuer_or_mutated_fixture(tmp_path) -> None:
    corpus = _fixtures(tmp_path)
    with pytest.raises(EvidenceReleaseError):
        build_evidence_release(fixtures_directory=tmp_path, release_id="missing", issuer_ciks=("0000320193",), evaluation_corpus=corpus)
    (tmp_path / "msft.json").write_text('{"cik":"0000789019","mutated":true}')
    with pytest.raises(EvidenceReleaseError):
        build_evidence_release(fixtures_directory=tmp_path, release_id="mutated", issuer_ciks=("0000789019",), evaluation_corpus=corpus)


def test_declared_v1_release_replays_the_checked_in_fixture_and_evaluation_inputs() -> None:
    fixtures = Path(__file__).parents[1] / "fixtures" / "sec"
    declaration = json.loads((fixtures / "release_v1.json").read_text())
    release = build_evidence_release(
        fixtures_directory=fixtures,
        release_id=declaration["release_id"],
        issuer_ciks=tuple(declaration["issuer_ciks"]),
        evaluation_corpus=fixtures / declaration["evaluation_corpus"],
        source_policy_version=declaration["source_policy_version"],
        eligibility_policy_version=declaration["eligibility_policy_version"],
        restatement_policy_version=declaration["restatement_policy_version"],
    )

    assert release.fixture_manifest_sha256 == declaration["fixture_manifest_sha256"]
    assert len(release.manifest_hash) == 64
