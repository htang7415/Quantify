"""Smoke-check the bounded no-sign-up trial through its CloudFront edge."""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


_EXPECTED_KEYS = {
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


def _request(request: Request) -> tuple[int, bytes]:
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - configured HTTPS endpoint
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def _trial_url() -> str:
    base = _environment("WEB_PREVIEW_URL")
    if not base.startswith("https://"):
        raise RuntimeError("WEB_PREVIEW_URL must use HTTPS")
    return urljoin(f"{base.rstrip('/')}/", "v1/trial/verify")


def main() -> None:
    body = json.dumps(
        {
            "cik": "0000789019",
            "analysis": "Microsoft revenue increased from fiscal 2023 to fiscal 2024.",
            "as_of_date": "2024-07-30",
        },
        separators=(",", ":"),
    ).encode()
    status, payload = _request(
        Request(
            _trial_url(), data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
    )
    if status != 200:
        raise RuntimeError(f"anonymous trial verification failed with HTTP {status}")
    try:
        response = json.loads(payload)
    except json.JSONDecodeError as error:
        raise RuntimeError("anonymous trial returned invalid JSON") from error
    if not isinstance(response, dict) or set(response) != _EXPECTED_KEYS:
        raise RuntimeError("anonymous trial returned an unsafe response contract")
    evidence_scope = response.get("evidence_scope")
    if not isinstance(evidence_scope, dict) or evidence_scope.get("source") != "SEC EDGAR":
        raise RuntimeError("anonymous trial returned an invalid evidence scope")
    limitation = response.get("limitation")
    if not isinstance(limitation, str) or "investment advice" not in limitation.lower():
        raise RuntimeError("anonymous trial limitation is missing")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify anonymous-trial smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
