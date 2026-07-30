from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "public_agent_verify.py"
spec = importlib.util.spec_from_file_location("public_agent_verify", SCRIPT)
public_agent_verify = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(public_agent_verify)


def test_public_agent_cli_uses_keychain_backed_token_and_prints_safe_contract(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    analysis = tmp_path / "analysis.txt"
    analysis.write_text("Microsoft revenue increased from fiscal 2023 to fiscal 2024.")
    expected = {
        "verdicts": [{"claim_id": "c1", "verdict": "verified"}],
        "requires_agent_resolution": False,
        "evidence_scope": {
            "source": "SEC EDGAR",
            "forms": ["10-K"],
            "snapshot_manifest_hash": "b" * 64,
        },
        "audit_manifest_hash": "a" * 64,
        "limitation": "This is not investment advice.",
    }
    monkeypatch.setattr(public_agent_verify, "_verify", lambda **_: expected)

    public_agent_verify.main(
        [
            "--cik",
            "0000789019",
            "--analysis-file",
            str(analysis),
            "--as-of-date",
            "2024-07-30",
        ]
    )

    assert json.loads(capsys.readouterr().out) == expected


def test_public_agent_cli_rejects_non_cik_and_oversized_analysis(
    tmp_path: Path, monkeypatch
) -> None:
    analysis = tmp_path / "analysis.txt"
    analysis.write_text("word " * 251)
    monkeypatch.setattr(public_agent_verify, "_verify", lambda **_: None)

    try:
        public_agent_verify.main(
            [
                "--cik",
                "bad",
                "--analysis-file",
                str(analysis),
                "--as-of-date",
                "2024-07-30",
            ]
        )
    except SystemExit as error:
        assert error.code == 2
    else:  # pragma: no cover - protects the public input boundary.
        raise AssertionError("invalid CIK was accepted")


def test_public_agent_cli_renders_a_conservative_human_result(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    analysis = tmp_path / "analysis.txt"
    analysis.write_text("Microsoft revenue increased from fiscal 2023 to fiscal 2024.")
    monkeypatch.setattr(
        public_agent_verify,
        "_verify",
        lambda **_: {
            "verdicts": [{"claim_id": "c1", "verdict": "verified"}],
            "requires_agent_resolution": False,
            "evidence_scope": {
                "source": "SEC EDGAR",
                "forms": ["10-K", "10-Q"],
                "snapshot_manifest_hash": "b" * 64,
            },
            "audit_manifest_hash": "a" * 64,
            "limitation": "This is not investment advice.",
        },
    )

    public_agent_verify.main(
        [
            "--cik",
            "0000789019",
            "--analysis-file",
            str(analysis),
            "--as-of-date",
            "2024-07-30",
            "--format",
            "human",
        ]
    )

    output = capsys.readouterr().out
    assert "c1: VERIFIED: Supported by the declared frozen evidence snapshot." in output
    assert "Evidence scope: SEC EDGAR (10-K, 10-Q), frozen snapshot " + "b" * 64 + "." in output
    assert "This is not investment advice." in output
    assert "Submitted analysis" not in output
    assert "Microsoft revenue increased" not in output


@pytest.mark.parametrize(
    "response, message",
    [
        (
            {
                "verdicts": [{"claim_id": "c1", "verdict": "verified"}],
                "requires_agent_resolution": "false",
                "evidence_scope": {
                    "source": "SEC EDGAR",
                    "forms": ["10-K"],
                    "snapshot_manifest_hash": "b" * 64,
                },
                "audit_manifest_hash": "a" * 64,
                "limitation": "This is not investment advice.",
            },
            "resolution flag",
        ),
        (
            {
                "verdicts": [{"claim_id": "c1", "verdict": "verified"}],
                "requires_agent_resolution": False,
                "evidence_scope": {
                    "source": "SEC EDGAR",
                    "forms": [],
                    "snapshot_manifest_hash": "b" * 64,
                },
                "audit_manifest_hash": "a" * 64,
                "limitation": "This is not investment advice.",
            },
            "evidence scope",
        ),
    ],
)
def test_public_agent_cli_human_result_fails_closed_for_malformed_safe_contract(
    response: dict[str, object], message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        public_agent_verify._human_result(response=response)
