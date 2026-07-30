from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "agent_verify.py"
spec = importlib.util.spec_from_file_location("agent_verify", SCRIPT)
agent_verify = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(agent_verify)


def test_local_agent_cli_signs_one_private_verify_and_prints_safe_contract(tmp_path, monkeypatch, capsys) -> None:
    analysis = tmp_path / "analysis.txt"
    analysis.write_text("Microsoft revenue increased.")
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    monkeypatch.setenv("STAGING_URL", "https://example.execute-api.us-east-2.amazonaws.com/staging")
    monkeypatch.setattr(agent_verify, "_assume_role", lambda **_: {"access_key": "key", "secret_key": "secret", "session_token": "token"})
    captured = {}
    def signed_post(**kwargs):
        captured.update(kwargs)
        return 200, b'{"claim_results":[{"claim_id":"c1","verdict":"verified"}],"review_items":[],"evidence_scope":{"source":"SEC EDGAR","entity_level_only":true,"forms":["10-K"],"snapshot_manifest_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"audit_manifest":{"manifest_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}}'
    monkeypatch.setattr(agent_verify, "_signed_post", signed_post)
    agent_verify.main(["--cik", "0000789019", "--analysis-file", str(analysis), "--as-of-date", "2024-07-30", "--role-arn", "arn:aws:iam::123:role/caller"])
    assert captured["url"].endswith("/v1/companies/0000789019/verify")
    assert b"Microsoft revenue increased." in captured["body"]
    assert "investment advice" in capsys.readouterr().out
