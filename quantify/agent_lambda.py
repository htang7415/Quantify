"""Narrow AWS Lambda boundary for the deterministic Quantify agent tool.

Direct Lambda invocation remains useful for private staging.  When placed behind
the production public API, the same handler accepts only API Gateway HTTP API
payload-v2 events and returns the deliberately restricted agent-safe result.
Authentication and OAuth scope verification happen at API Gateway, before this
function is invoked.
"""
from __future__ import annotations

import base64
from datetime import date
import json
import os
import re
from collections.abc import Mapping
from typing import Any
from urllib.request import Request, urlopen

from quantify.agent_tool import agent_safe_result


_CIK_PATTERN = re.compile(r"^\d{1,10}$")
_PUBLIC_ROUTE = "/v1/agent/verify"


def handler(event: dict[str, object], _context: object) -> dict[str, object]:
    """Support private direct invocation and the authenticated public route."""

    if "requestContext" in event:
        return _api_gateway_response(event)
    return verify(event)


def verify(event: Mapping[str, object]) -> dict[str, object]:
    """Run exactly one private core verification and expose only safe fields."""

    try:
        cik = event["cik"]
        analysis = event["analysis"]
        as_of_date = event["as_of_date"]
    except KeyError as error:
        raise ValueError(f"missing {error.args[0]}") from error
    if not isinstance(cik, str) or not isinstance(analysis, str) or not isinstance(as_of_date, str):
        raise ValueError("cik, analysis, and as_of_date must be strings")
    if not _CIK_PATTERN.fullmatch(cik):
        raise ValueError("cik must contain one through ten digits")
    if not analysis.strip() or len(analysis.split()) > 250:
        raise ValueError("analysis must contain one through 250 words")
    try:
        date.fromisoformat(as_of_date)
    except ValueError as error:
        raise ValueError("as_of_date must be an ISO calendar date") from error

    return invoke_quantify_verify(cik=cik, analysis=analysis, as_of_date=as_of_date)


def invoke_quantify_verify(*, cik: str, analysis: str, as_of_date: str) -> dict[str, object]:
    """Sign one request to the private core API using this Lambda's role."""

    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    from botocore.session import get_session

    core_url = os.environ.get("QUANTIFY_CORE_URL") or os.environ["QUANTIFY_STAGING_URL"]
    url = f"{core_url.rstrip('/')}/v1/companies/{cik}/verify"
    body = json.dumps({"analysis": analysis, "as_of_date": as_of_date}, separators=(",", ":")).encode()
    request = AWSRequest(method="POST", url=url, data=body, headers={"content-type": "application/json"})
    session = get_session()
    SigV4Auth(session.get_credentials().get_frozen_credentials(), "execute-api", os.environ["AWS_REGION"]).add_auth(request)
    with urlopen(Request(url, data=body, headers=dict(request.headers.items()), method="POST"), timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(f"Quantify verification failed with HTTP {response.status}")
        return agent_safe_result(json.loads(response.read()))


def _api_gateway_response(event: Mapping[str, object]) -> dict[str, object]:
    """Adapt a public HTTP API event without leaking request or error details."""

    try:
        request_context = event.get("requestContext")
        if not isinstance(request_context, Mapping):
            raise ValueError("request context is invalid")
        http = request_context.get("http")
        if not isinstance(http, Mapping) or http.get("method") != "POST":
            return _response(404, {"error": "not_found"})
        if _application_path(event=event, request_context=request_context) != _PUBLIC_ROUTE:
            return _response(404, {"error": "not_found"})
        payload = _decode_json_body(event)
        return _response(200, verify(payload))
    except ValueError:
        return _response(400, {"error": "invalid_request"})
    except Exception:
        # Core failures are already fail-closed.  The public boundary must not
        # disclose report text, provider details, credentials, or IAM context.
        return _response(502, {"error": "verification_unavailable"})


def _decode_json_body(event: Mapping[str, object]) -> Mapping[str, object]:
    body = event.get("body")
    if not isinstance(body, str):
        raise ValueError("body is required")
    try:
        raw = base64.b64decode(body, validate=True) if event.get("isBase64Encoded") else body.encode()
        payload: Any = json.loads(raw)
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("body must be JSON") from error
    if not isinstance(payload, Mapping):
        raise ValueError("body must be a JSON object")
    return payload


def _application_path(*, event: Mapping[str, object], request_context: Mapping[str, object]) -> str:
    """Remove API Gateway's named stage before comparing the public allowlist."""

    raw_path = event.get("rawPath")
    if not isinstance(raw_path, str):
        return ""
    stage = request_context.get("stage")
    prefix = f"/{stage}" if isinstance(stage, str) and stage else ""
    if prefix and (raw_path == prefix or raw_path.startswith(f"{prefix}/")):
        return raw_path[len(prefix):] or "/"
    return raw_path


def _response(status_code: int, payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": json.dumps(payload, sort_keys=True, separators=(",", ":")),
    }
