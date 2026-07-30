"""SigV4-only smoke caller for Quantify's private API Gateway staging API."""

from __future__ import annotations

import datetime as dt
from hashlib import sha256
import hmac
import json
import os
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qsl, quote, urlsplit
from urllib.request import Request, urlopen


def _environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"set {name}")
    return value


def _assume_smoke_role() -> dict[str, str]:
    aws_bin = os.environ.get("AWS_BIN", "aws")
    completed = subprocess.run(
        [
            aws_bin,
            "sts",
            "assume-role",
            "--role-arn",
            _environment("SMOKE_ROLE_ARN"),
            "--role-session-name",
            "quantify-staging-smoke",
            "--query",
            "Credentials",
            "--output",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    credentials = json.loads(completed.stdout)
    return {
        "access_key": credentials["AccessKeyId"],
        "secret_key": credentials["SecretAccessKey"],
        "session_token": credentials["SessionToken"],
    }


def _signing_key(secret_key: str, date_stamp: str, region: str) -> bytes:
    key = ("AWS4" + secret_key).encode("utf-8")
    for part in (date_stamp, region, "execute-api", "aws4_request"):
        key = hmac.new(key, part.encode("utf-8"), sha256).digest()
    return key


def _signed_request(
    *, credentials: dict[str, str], method: str, url: str, body: bytes = b""
) -> tuple[int, bytes]:
    region = _environment("AWS_REGION")
    parsed = urlsplit(url)
    now = dt.datetime.now(dt.UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = sha256(body).hexdigest()
    canonical_query = "&".join(
        f"{quote(key, safe='-_.~')}={quote(value, safe='-_.~')}"
        for key, value in sorted(parse_qsl(parsed.query, keep_blank_values=True))
    )
    headers = {
        "content-type": "application/json",
        "host": parsed.netloc,
        "x-amz-date": amz_date,
        "x-amz-security-token": credentials["session_token"],
    }
    signed_header_names = ";".join(sorted(headers))
    canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in sorted(headers))
    canonical_request = "\n".join(
        [
            method,
            quote(parsed.path or "/", safe="/-_.~"),
            canonical_query,
            canonical_headers,
            signed_header_names,
            payload_hash,
        ]
    )
    credential_scope = f"{date_stamp}/{region}/execute-api/aws4_request"
    string_to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, credential_scope, sha256(canonical_request.encode()).hexdigest()]
    )
    signature = hmac.new(
        _signing_key(credentials["secret_key"], date_stamp, region),
        string_to_sign.encode(),
        sha256,
    ).hexdigest()
    headers["Authorization"] = (
        "AWS4-HMAC-SHA256 "
        f"Credential={credentials['access_key']}/{credential_scope}, "
        f"SignedHeaders={signed_header_names}, Signature={signature}"
    )
    request = Request(url, data=body or None, headers=headers, method=method)
    try:
        with urlopen(request, timeout=15) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def _expect_json(status: int, payload: bytes) -> dict[str, Any]:
    if status < 200 or status >= 300:
        raise RuntimeError(f"expected a successful response, received HTTP {status}")
    return json.loads(payload)


def main() -> None:
    base_url = _environment("STAGING_URL").rstrip("/")
    credentials = _assume_smoke_role()
    health = _expect_json(*_signed_request(credentials=credentials, method="GET", url=f"{base_url}/healthz"))
    if health != {"status": "ok"}:
        raise RuntimeError("health response does not match the private API contract")
    request_body = json.dumps(
        {
            "analysis": "Microsoft revenue increased from fiscal 2023 to fiscal 2024.",
            "as_of_date": "2024-07-30",
            "forms": ["10-K"],
        },
        separators=(",", ":"),
    ).encode()
    response = _expect_json(
        *_signed_request(
            credentials=credentials,
            method="POST",
            url=f"{base_url}/v1/companies/789019/verify",
            body=request_body,
        )
    )
    audit = response["audit_manifest"]
    if audit["deployment_image_digest"] != _environment("EXPECTED_IMAGE_DIGEST"):
        raise RuntimeError("audit image digest does not match the deployed digest")
    if audit["evidence_fixture_manifest_hash"] != _environment("EXPECTED_FIXTURE_MANIFEST_HASH"):
        raise RuntimeError("audit fixture manifest hash does not match")
    if not isinstance(response.get("claim_results"), list):
        raise RuntimeError("verification response has no claim-results list")
    if not isinstance(response.get("verification_cache_hit"), bool):
        raise RuntimeError("verification response has no cache-status flag")
    evidence_scope = response.get("evidence_scope")
    if not isinstance(evidence_scope, dict):
        raise RuntimeError("verification response has no evidence-scope object")
    if evidence_scope.get("source") != "SEC EDGAR" or evidence_scope.get("entity_level_only") is not True:
        raise RuntimeError("verification response violates the embedded-evidence contract")
    snapshot_manifest_hash = evidence_scope.get("snapshot_manifest_hash")
    if not isinstance(snapshot_manifest_hash, str) or len(snapshot_manifest_hash) != 64:
        raise RuntimeError("verification response has an invalid snapshot manifest hash")
    replay_manifest_hash = audit.get("manifest_hash")
    if not isinstance(replay_manifest_hash, str) or len(replay_manifest_hash) != 64:
        raise RuntimeError("verification response has an invalid replay manifest hash")
    for path in (
        "/v1/companies/789019/review",
        "/v1/companies/789019/resolve",
        "/v1/verify/batch",
    ):
        status, _ = _signed_request(
            credentials=credentials, method="POST", url=f"{base_url}{path}", body=b"{}"
        )
        if status != 404:
            raise RuntimeError(f"internal route {path} is unexpectedly available ({status})")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"AWS staging smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
