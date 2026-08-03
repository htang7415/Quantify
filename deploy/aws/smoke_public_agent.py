"""OAuth smoke caller for Quantify's public, agent-safe production edge."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_KEYCHAIN_SERVICE = "quantify.public-agent.oauth-client-secret"

def _environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"set {name}")
    return value


def _request(request: Request) -> tuple[int, bytes]:
    try:
        with urlopen(request, timeout=15) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def _access_token() -> str:
    client_id = _environment("COGNITO_MACHINE_CLIENT_ID")
    secret_file = os.environ.get("COGNITO_MACHINE_CLIENT_SECRET_FILE")
    if secret_file:
        client_secret = Path(secret_file).read_text().strip()
    else:
        keychain = subprocess.run(
            [
                "security", "find-generic-password", "-s",
                os.environ.get("PUBLIC_AGENT_KEYCHAIN_SERVICE", _KEYCHAIN_SERVICE),
                "-a", client_id, "-w",
            ],
            capture_output=True, check=False, text=True,
        )
        client_secret = keychain.stdout.strip()
    if not client_secret:
        raise RuntimeError("Cognito machine client secret is unavailable")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
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


def _verify(*, token: str | None) -> tuple[int, dict[str, object] | None]:
    body = json.dumps(
        {
            "cik": "0000789019",
            "analysis": "Microsoft revenue increased from fiscal 2023 to fiscal 2024.",
            "as_of_date": "2024-07-30",
        },
        separators=(",", ":"),
    ).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, payload = _request(
        Request(_environment("PUBLIC_AGENT_URL"), data=body, headers=headers, method="POST")
    )
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        decoded = None
    return status, decoded if isinstance(decoded, dict) else None


def main() -> None:
    unauthenticated_status, _ = _verify(token=None)
    if unauthenticated_status not in {401, 403}:
        raise RuntimeError(
            f"public agent accepted a request without an OAuth token ({unauthenticated_status})"
        )
    status, response = _verify(token=_access_token())
    if status != 200 or response is None:
        raise RuntimeError(f"public agent verification failed with HTTP {status}")
    expected_keys = {
        "verdicts",
        "requires_agent_resolution",
        "evidence_scope",
        "audit_manifest_hash",
        "limitation",
    }
    if set(response) != expected_keys:
        raise RuntimeError("public agent returned fields outside the safe contract")
    if "investment advice" not in str(response["limitation"]):
        raise RuntimeError("public agent limitation is missing")
    if response["evidence_scope"].get("source") != "SEC EDGAR":
        raise RuntimeError("public agent evidence scope is invalid")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Public Quantify agent smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
