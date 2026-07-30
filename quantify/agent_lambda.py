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
import hmac
import json
import logging
import os
import re
from collections.abc import Mapping
from typing import Any
from urllib.request import Request, urlopen

from quantify.agent_tool import agent_safe_result
from quantify.anonymous_trial import (
    TrialLedgerUnavailableError,
    TrialLimitError,
    TrialUnavailableError,
    load_anonymous_trial_admission,
)
from quantify.tenant_admission import (
    TenantLedgerUnavailableError,
    TenantQuotaExceededError,
    load_tenant_admission,
)


_CIK_PATTERN = re.compile(r"^\d{1,10}$")
_PUBLIC_ROUTE = "/v1/agent/verify"
_TRIAL_ROUTE = "/v1/trial/verify"
_LOGGER = logging.getLogger(__name__)


def handler(event: dict[str, object], _context: object) -> dict[str, object]:
    """Support private direct invocation and the authenticated public route."""

    if "requestContext" in event:
        return _api_gateway_response(event)
    return verify(event)


def verify(event: Mapping[str, object]) -> dict[str, object]:
    """Run exactly one private core verification and expose only safe fields."""

    cik, analysis, as_of_date = _validated_request(event)
    return invoke_quantify_verify(cik=cik, analysis=analysis, as_of_date=as_of_date)


def _validated_request(event: Mapping[str, object]) -> tuple[str, str, str]:
    """Validate a request before it can consume any admission capacity."""

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
    return cik, analysis, as_of_date


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
        path = _application_path(event=event, request_context=request_context)
        if path not in {_PUBLIC_ROUTE, _TRIAL_ROUTE}:
            return _response(404, {"error": "not_found"})
        payload = _decode_json_body(event)
        cik, analysis, as_of_date = _validated_request(payload)
        if path == _TRIAL_ROUTE:
            _reserve_anonymous_trial(event=event, request_context=request_context)
        else:
            _reserve_authenticated_tenant(request_context=request_context)
        return _response(
            200,
            invoke_quantify_verify(
                cik=cik, analysis=analysis, as_of_date=as_of_date
            ),
        )
    except TrialLimitError:
        return _response(429, {"error": "trial_limit_reached"})
    except TrialUnavailableError:
        return _response(503, {"error": "trial_unavailable"})
    except TenantQuotaExceededError:
        return _response(429, {"error": "tenant_quota_exhausted"})
    except TenantLedgerUnavailableError:
        return _response(503, {"error": "tenant_admission_unavailable"})
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


def _reserve_anonymous_trial(*, event: Mapping[str, object], request_context: Mapping[str, object]) -> None:
    """Reserve trial capacity before report text reaches the private core."""

    try:
        import boto3
    except ImportError as error:  # pragma: no cover - Lambda base image provides boto3.
        raise TrialUnavailableError("anonymous trial is unavailable") from error
    admission = load_anonymous_trial_admission(
        environment=os.environ, client=boto3.client("dynamodb")
    )
    _LOGGER.info("anonymous trial admission configuration loaded")
    headers = event.get("headers")
    if not isinstance(headers, Mapping):
        raise TrialUnavailableError("anonymous trial is unavailable")
    normalized_headers = {
        key.lower(): value for key, value in headers.items() if isinstance(key, str) and isinstance(value, str)
    }
    origin_key = normalized_headers.get("x-quantify-trial-origin", "")
    if not hmac.compare_digest(origin_key, admission.origin_key):
        raise TrialUnavailableError("anonymous trial is unavailable")
    _LOGGER.info("anonymous trial origin verified")
    forwarded_for = normalized_headers.get("x-forwarded-for", "")
    source_ip = forwarded_for.split(",", 1)[0].strip()
    if not source_ip:
        http = request_context.get("http")
        source_ip = http.get("sourceIp") if isinstance(http, Mapping) else ""
    if not isinstance(source_ip, str):
        raise TrialUnavailableError("anonymous trial is unavailable")
    admission.reserve(source_ip=source_ip)


def _reserve_authenticated_tenant(*, request_context: Mapping[str, object]) -> None:
    """Reserve an authenticated tenant budget before forwarding report text."""

    authorizer = request_context.get("authorizer")
    jwt = authorizer.get("jwt") if isinstance(authorizer, Mapping) else None
    claims = jwt.get("claims") if isinstance(jwt, Mapping) else None
    tenant_id = claims.get("sub") if isinstance(claims, Mapping) else None
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise TenantLedgerUnavailableError("tenant identity is unavailable")
    try:
        import boto3
    except ImportError as error:  # pragma: no cover - Lambda base image provides boto3.
        raise TenantLedgerUnavailableError("tenant admission is unavailable") from error
    admission = load_tenant_admission(
        environment=os.environ, client=boto3.client("dynamodb")
    )
    admission.reserve(tenant_id=tenant_id)


def _application_path(*, event: Mapping[str, object], request_context: Mapping[str, object]) -> str:
    """Remove API Gateway's named stage before comparing the public allowlist."""

    route_key = event.get("routeKey")
    if isinstance(route_key, str):
        method, separator, route_path = route_key.partition(" ")
        if method == "POST" and separator and route_path.startswith("/"):
            return route_path
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
