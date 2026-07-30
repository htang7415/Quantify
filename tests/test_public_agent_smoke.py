from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "smoke_public_agent.py"
spec = importlib.util.spec_from_file_location("smoke_public_agent", SCRIPT)
smoke_public_agent = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(smoke_public_agent)


def test_public_agent_smoke_requires_oauth_then_checks_safe_contract(monkeypatch) -> None:
    response = {
        "verdicts": [{"claim_id": "c1", "verdict": "verified"}],
        "requires_agent_resolution": False,
        "evidence_scope": {"source": "SEC EDGAR", "entity_level_only": True},
        "audit_manifest_hash": "a" * 64,
        "limitation": "This is not investment advice.",
    }
    calls: list[str | None] = []

    def verify(*, token: str | None):
        calls.append(token)
        return (401, None) if token is None else (200, response)

    monkeypatch.setattr(smoke_public_agent, "_verify", verify)
    monkeypatch.setattr(smoke_public_agent, "_access_token", lambda: "access-token")

    smoke_public_agent.main()

    assert calls == [None, "access-token"]


def test_public_agent_smoke_rejects_extra_public_fields(monkeypatch) -> None:
    monkeypatch.setattr(smoke_public_agent, "_access_token", lambda: "access-token")
    monkeypatch.setattr(
        smoke_public_agent,
        "_verify",
        lambda *, token: (401, None)
        if token is None
        else (200, {"verdicts": [], "raw_report": "must not be public"}),
    )

    try:
        smoke_public_agent.main()
    except RuntimeError as error:
        assert "outside the safe contract" in str(error)
    else:  # pragma: no cover - protects the smoke contract itself.
        raise AssertionError("unsafe public response was accepted")
