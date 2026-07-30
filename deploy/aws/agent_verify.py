"""Local AI-agent CLI for the private Quantify staging verification tool."""

from __future__ import annotations

import argparse
import datetime as dt
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from quantify.agent_tool import agent_safe_result


def _environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"set {name}")
    return value


def _assume_role(*, role_arn: str) -> dict[str, str]:
    completed = subprocess.run(
        [
            os.environ.get("AWS_BIN", "aws"), "sts", "assume-role", "--role-arn", role_arn,
            "--role-session-name", "quantify-local-agent", "--query", "Credentials", "--output", "json",
        ],
        check=True, capture_output=True, text=True,
    )
    credentials = json.loads(completed.stdout)
    return {"access_key": credentials["AccessKeyId"], "secret_key": credentials["SecretAccessKey"], "session_token": credentials["SessionToken"]}


def _signing_key(secret_key: str, date_stamp: str, region: str) -> bytes:
    key = ("AWS4" + secret_key).encode()
    for part in (date_stamp, region, "execute-api", "aws4_request"):
        key = hmac.new(key, part.encode(), sha256).digest()
    return key


def _signed_post(*, url: str, body: bytes, credentials: dict[str, str], region: str) -> tuple[int, bytes]:
    parsed = urlsplit(url)
    now = dt.datetime.now(dt.UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = sha256(body).hexdigest()
    headers = {"content-type": "application/json", "host": parsed.netloc, "x-amz-date": amz_date, "x-amz-security-token": credentials["session_token"]}
    signed_names = ";".join(sorted(headers))
    canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in sorted(headers))
    canonical = "\n".join(["POST", quote(parsed.path, safe="/-_.~"), "", canonical_headers, signed_names, payload_hash])
    scope = f"{date_stamp}/{region}/execute-api/aws4_request"
    string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, sha256(canonical.encode()).hexdigest()])
    headers["Authorization"] = f"AWS4-HMAC-SHA256 Credential={credentials['access_key']}/{scope}, SignedHeaders={signed_names}, Signature={hmac.new(_signing_key(credentials['secret_key'], date_stamp, region), string_to_sign.encode(), sha256).hexdigest()}"
    try:
        with urlopen(Request(url, data=body, headers=headers, method="POST"), timeout=15) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cik", required=True)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--analysis-file", type=Path)
    input_group.add_argument("--analysis-fixture", type=Path)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--role-arn", default=os.environ.get("CALLER_ROLE_ARN"))
    args = parser.parse_args(argv)
    if not args.role_arn:
        parser.error("set CALLER_ROLE_ARN or pass --role-arn")
    if args.analysis_fixture:
        analysis = json.loads(args.analysis_fixture.read_text(encoding="utf-8")).get("analysis", "")
    else:
        analysis = args.analysis_file.read_text(encoding="utf-8").strip()
    if not isinstance(analysis, str):
        parser.error("analysis fixture has no string analysis")
    if not analysis:
        parser.error("analysis file is empty")
    if len(analysis.split()) > 250:
        parser.error("analysis must contain at most 250 words")
    body = json.dumps({"analysis": analysis, "as_of_date": args.as_of_date}, separators=(",", ":")).encode()
    status, response_body = _signed_post(
        url=f"{_environment('STAGING_URL').rstrip('/')}/v1/companies/{args.cik}/verify",
        body=body, credentials=_assume_role(role_arn=args.role_arn), region=_environment("AWS_REGION"),
    )
    if status != 200:
        raise RuntimeError(f"Quantify verification failed with HTTP {status}")
    print(json.dumps(agent_safe_result(json.loads(response_body)), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify local agent tool failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
