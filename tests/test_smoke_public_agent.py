from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "smoke_public_agent.py"
spec = importlib.util.spec_from_file_location("smoke_public_agent", SCRIPT)
smoke_public_agent = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(smoke_public_agent)


def _oauth_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COGNITO_MACHINE_CLIENT_ID", "client-id")
    monkeypatch.setenv("OAUTH_VERIFY_SCOPE", "https://example.test/verify")
    monkeypatch.setenv("OAUTH_TOKEN_ENDPOINT", "https://example.test/token")


def test_smoke_reads_an_explicit_secret_file_when_provided(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret_file = tmp_path / "secret"
    secret_file.write_text("file-secret\n")
    _oauth_environment(monkeypatch)
    monkeypatch.setenv("COGNITO_MACHINE_CLIENT_SECRET_FILE", str(secret_file))
    monkeypatch.setattr(smoke_public_agent, "_request", lambda request: (200, b'{"access_token":"token"}'))

    assert smoke_public_agent._access_token() == "token"


def test_smoke_uses_keychain_when_no_secret_file_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Completed:
        returncode = 0
        stdout = "keychain-secret\n"

    _oauth_environment(monkeypatch)
    monkeypatch.delenv("COGNITO_MACHINE_CLIENT_SECRET_FILE", raising=False)
    monkeypatch.setattr(smoke_public_agent.subprocess, "run", lambda *args, **kwargs: _Completed())
    monkeypatch.setattr(smoke_public_agent, "_request", lambda request: (200, b'{"access_token":"token"}'))

    assert smoke_public_agent._access_token() == "token"


def test_smoke_refuses_an_unavailable_keychain_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Completed:
        returncode = 44
        stdout = ""

    _oauth_environment(monkeypatch)
    monkeypatch.delenv("COGNITO_MACHINE_CLIENT_SECRET_FILE", raising=False)
    monkeypatch.setattr(smoke_public_agent.subprocess, "run", lambda *args, **kwargs: _Completed())

    with pytest.raises(RuntimeError, match="secret is unavailable"):
        smoke_public_agent._access_token()
