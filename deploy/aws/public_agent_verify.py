"""Local external-agent adapter for Quantify's scoped public verification API."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_KEYCHAIN_SERVICE = "quantify.public-agent.oauth-client-secret"
_EXPECTED_RESPONSE_KEYS = {
    "verdicts",
    "requires_agent_resolution",
    "evidence_scope",
    "audit_manifest_hash",
    "limitation",
}
_HASH = re.compile(r"^[0-9a-f]{64}$")
_VERDICT_MEANINGS = {
    "verified": "Supported by the declared frozen evidence snapshot.",
    "unsupported": "The declared evidence does not warrant the extracted claim.",
    "defeated": "Compatible counterevidence in the declared snapshot defeats the extracted claim.",
    "qualified": "Supported only with an important qualification from the declared snapshot.",
    "requires_agent_resolution": "Cannot be published until an agent resolves the ambiguity.",
}


def _environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"set {name}")
    return value


def _client_secret() -> str:
    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-s",
            os.environ.get("PUBLIC_AGENT_KEYCHAIN_SERVICE", _KEYCHAIN_SERVICE),
            "-a",
            _environment("COGNITO_MACHINE_CLIENT_ID"),
            "-w",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    secret = result.stdout.strip()
    if result.returncode != 0 or not secret:
        raise RuntimeError("public-agent OAuth client secret is unavailable in macOS Keychain")
    return secret


def _request(request: Request) -> tuple[int, bytes]:
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed configured HTTPS endpoint
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def _access_token() -> str:
    basic = base64.b64encode(
        f"{_environment('COGNITO_MACHINE_CLIENT_ID')}:{_client_secret()}".encode()
    ).decode()
    body = urlencode(
        {"grant_type": "client_credentials", "scope": _environment("OAUTH_VERIFY_SCOPE")}
    ).encode()
    status, payload = _request(
        Request(
            _environment("OAUTH_TOKEN_ENDPOINT"),
            data=body,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
    )
    if status != 200:
        raise RuntimeError(f"OAuth token request failed with HTTP {status}")
    token = json.loads(payload).get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("OAuth token response has no access token")
    return token


def _safe_response(response: object) -> dict[str, object]:
    """Validate the complete narrow public contract before exposing it locally."""

    if not isinstance(response, dict) or set(response) != _EXPECTED_RESPONSE_KEYS:
        raise RuntimeError("public Quantify verification returned an unsafe response contract")
    verdicts = response["verdicts"]
    if not isinstance(verdicts, list):
        raise RuntimeError("public Quantify verification has invalid verdicts")
    validated_verdicts: list[dict[str, str]] = []
    for item in verdicts:
        if (
            not isinstance(item, dict)
            or set(item) != {"claim_id", "verdict"}
            or not isinstance(item["claim_id"], str)
            or not item["claim_id"]
            or not isinstance(item["verdict"], str)
            or item["verdict"] not in _VERDICT_MEANINGS
        ):
            raise RuntimeError("public Quantify verification has an invalid verdict")
        validated_verdicts.append({"claim_id": item["claim_id"], "verdict": item["verdict"]})
    requires_resolution = response["requires_agent_resolution"]
    if not isinstance(requires_resolution, bool):
        raise RuntimeError("public Quantify verification has an invalid resolution flag")
    evidence_scope = response["evidence_scope"]
    if (
        not isinstance(evidence_scope, dict)
        or set(evidence_scope) != {"source", "forms", "snapshot_manifest_hash"}
        or evidence_scope["source"] != "SEC EDGAR"
        or not isinstance(evidence_scope["forms"], list)
        or not evidence_scope["forms"]
        or not all(isinstance(form, str) and form for form in evidence_scope["forms"])
        or not isinstance(evidence_scope["snapshot_manifest_hash"], str)
        or not _HASH.fullmatch(evidence_scope["snapshot_manifest_hash"])
    ):
        raise RuntimeError("public Quantify verification has an invalid evidence scope")
    audit_manifest_hash = response["audit_manifest_hash"]
    if not isinstance(audit_manifest_hash, str) or not _HASH.fullmatch(audit_manifest_hash):
        raise RuntimeError("public Quantify verification has an invalid audit reference")
    limitation = response["limitation"]
    if not isinstance(limitation, str) or "investment advice" not in limitation.lower():
        raise RuntimeError("public Quantify verification is missing its limitation")
    return {
        "verdicts": validated_verdicts,
        "requires_agent_resolution": requires_resolution,
        "evidence_scope": {
            "source": evidence_scope["source"],
            "forms": list(evidence_scope["forms"]),
            "snapshot_manifest_hash": evidence_scope["snapshot_manifest_hash"],
        },
        "audit_manifest_hash": audit_manifest_hash,
        "limitation": limitation,
    }


def _verify(*, cik: str, analysis: str, as_of_date: str) -> dict[str, object]:
    body = json.dumps(
        {"cik": cik, "analysis": analysis, "as_of_date": as_of_date},
        separators=(",", ":"),
    ).encode()
    status, payload = _request(
        Request(
            _environment("PUBLIC_AGENT_URL"),
            data=body,
            headers={
                "Authorization": f"Bearer {_access_token()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
    )
    if status != 200:
        raise RuntimeError(f"public Quantify verification failed with HTTP {status}")
    try:
        response = json.loads(payload)
    except json.JSONDecodeError as error:
        raise RuntimeError("public Quantify verification returned invalid JSON") from error
    return _safe_response(response)


def _valid_cik(value: str) -> str:
    if not value.isdigit() or not 1 <= len(value) <= 10:
        raise argparse.ArgumentTypeError("CIK must contain 1 through 10 digits")
    return value


def _valid_date(value: str) -> str:
    try:
        dt.date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("as-of date must be ISO-8601") from error
    return value


def _human_result(*, response: dict[str, object]) -> str:
    """Render every safe-contract field without echoing submitted analysis."""

    safe_response = _safe_response(response)
    verdicts = safe_response["verdicts"]
    evidence_scope = safe_response["evidence_scope"]
    assert isinstance(verdicts, list)  # Narrowed by _safe_response.
    assert isinstance(evidence_scope, dict)  # Narrowed by _safe_response.
    forms = evidence_scope["forms"]
    assert isinstance(forms, list)  # Narrowed by _safe_response.
    form_text = ", ".join(forms)
    lines = [
        "Quantify Research Referee",
        "",
        "Verification outcome for extracted factual claims:",
    ]
    if verdicts:
        for item in verdicts:
            assert isinstance(item, dict)  # Narrowed by _safe_response.
            claim_id, verdict = item["claim_id"], item["verdict"]
            assert isinstance(claim_id, str) and isinstance(verdict, str)
            lines.append(f"  {claim_id}: {verdict.upper()}: {_VERDICT_MEANINGS[verdict]}")
    else:
        lines.append("  No factual claims were extracted.")
    if safe_response["requires_agent_resolution"]:
        lines.append("  REVIEW REQUIRED: Do not publish automatically; an agent must resolve the ambiguity.")
    lines.extend(
        (
            "",
            f"Evidence scope: {evidence_scope['source']} ({form_text}), frozen snapshot {evidence_scope['snapshot_manifest_hash']}.",
            f"Audit reference: {safe_response['audit_manifest_hash']}",
            f"Limitation: {safe_response['limitation']}",
        )
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cik", required=True, type=_valid_cik)
    parser.add_argument("--analysis-file", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True, type=_valid_date)
    parser.add_argument("--format", choices=("json", "human"), default="json")
    args = parser.parse_args(argv)
    analysis = args.analysis_file.read_text(encoding="utf-8").strip()
    if not analysis:
        parser.error("analysis file is empty")
    if len(analysis.split()) > 250:
        parser.error("analysis must contain at most 250 words")
    response = _verify(cik=args.cik, analysis=analysis, as_of_date=args.as_of_date)
    if args.format == "human":
        print(_human_result(response=response))
    else:
        print(json.dumps(response, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Public Quantify agent verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
