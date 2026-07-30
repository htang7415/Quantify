"""Local external-agent adapter for Quantify's scoped public verification API."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
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
    if not isinstance(response, dict) or set(response) != _EXPECTED_RESPONSE_KEYS:
        raise RuntimeError("public Quantify verification returned an unsafe response contract")
    if "investment advice" not in str(response["limitation"]):
        raise RuntimeError("public Quantify verification is missing its limitation")
    return response


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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cik", required=True, type=_valid_cik)
    parser.add_argument("--analysis-file", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True, type=_valid_date)
    args = parser.parse_args(argv)
    analysis = args.analysis_file.read_text(encoding="utf-8").strip()
    if not analysis:
        parser.error("analysis file is empty")
    if len(analysis.split()) > 250:
        parser.error("analysis must contain at most 250 words")
    print(
        json.dumps(
            _verify(cik=args.cik, analysis=analysis, as_of_date=args.as_of_date),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Public Quantify agent verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
