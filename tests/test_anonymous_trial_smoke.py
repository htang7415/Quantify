from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "deploy" / "aws" / "smoke_anonymous_trial.py"


def _module():
    spec = importlib.util.spec_from_file_location("anonymous_trial_smoke", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_anonymous_trial_smoke_accepts_only_the_safe_contract(monkeypatch) -> None:
    module = _module()
    monkeypatch.setenv("WEB_PREVIEW_URL", "https://preview.example")
    payload = {
        "verdicts": [{"claim_id": "claim-1", "verdict": "verified"}],
        "requires_agent_resolution": False,
        "evidence_scope": {
            "source": "SEC EDGAR",
            "forms": ["10-K"],
            "snapshot_manifest_hash": "a" * 64,
        },
        "audit_manifest_hash": "b" * 64,
        "limitation": "This is not investment advice.",
    }

    monkeypatch.setattr(module, "_request", lambda request: (200, json.dumps(payload).encode()))

    module.main()


def test_anonymous_trial_smoke_rejects_non_https_preview(monkeypatch) -> None:
    module = _module()
    monkeypatch.setenv("WEB_PREVIEW_URL", "http://preview.example")

    try:
        module.main()
    except RuntimeError as error:
        assert "must use HTTPS" in str(error)
    else:
        raise AssertionError("expected non-HTTPS preview URL to be rejected")
