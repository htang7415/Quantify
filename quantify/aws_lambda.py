"""AWS Lambda boundary for Quantify's private, fixture-only production app.

The verifier remains cloud-provider independent.  This module is deliberately
small: it reads one pinned secret version at Lambda initialization and adapts
API Gateway HTTP API (payload v2) events to the existing ASGI application.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable, Mapping
from functools import lru_cache
import os
from typing import Any, Protocol
from urllib.parse import unquote

from fastapi import FastAPI

from quantify.production import ProductionConfigurationError, create_production_app


_SECRET_ARN_ENV = "QUANTIFY_GEMINI_SECRET_ARN"
_SECRET_VERSION_ENV = "QUANTIFY_GEMINI_SECRET_VERSION_ID"
_IMAGE_DIGEST_ENV = "QUANTIFY_IMAGE_DIGEST"


class SecretsManagerClient(Protocol):
    def get_secret_value(self, **kwargs: str) -> Mapping[str, object]: ...


def load_pinned_gemini_api_key(
    *,
    environment: Mapping[str, str] | None = None,
    secret_client: SecretsManagerClient | None = None,
) -> str:
    """Return the exact AWS Secrets Manager version selected for this image."""

    environment = environment if environment is not None else os.environ
    secret_arn = environment.get(_SECRET_ARN_ENV)
    version_id = environment.get(_SECRET_VERSION_ENV)
    if not secret_arn or not version_id:
        raise ProductionConfigurationError(
            "QUANTIFY_GEMINI_SECRET_ARN and QUANTIFY_GEMINI_SECRET_VERSION_ID are required"
        )
    if secret_client is None:
        try:
            import boto3
        except ImportError as error:  # pragma: no cover - Lambda base image provides boto3.
            raise ProductionConfigurationError("AWS Lambda runtime boto3 is unavailable") from error
        secret_client = boto3.client("secretsmanager")
    try:
        response = secret_client.get_secret_value(SecretId=secret_arn, VersionId=version_id)
    except Exception as error:  # AWS SDK exception types are intentionally not exposed.
        raise ProductionConfigurationError("pinned Gemini secret cannot be retrieved") from error
    secret = response.get("SecretString")
    if not isinstance(secret, str) or not secret:
        raise ProductionConfigurationError("pinned Gemini secret is empty or not a string")
    return secret


def create_aws_production_app(
    *,
    environment: Mapping[str, str] | None = None,
    secret_client: SecretsManagerClient | None = None,
) -> FastAPI:
    """Compose the existing production app with an AWS-pinned Gemini secret."""

    environment = environment if environment is not None else os.environ
    api_key = load_pinned_gemini_api_key(
        environment=environment, secret_client=secret_client
    )
    return create_production_app(
        api_key=api_key,
        image_digest=environment.get(_IMAGE_DIGEST_ENV),
        environment=environment,
    )


AsgiApp = Callable[
    [dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]],
    Awaitable[None],
]


def create_api_gateway_handler(app: AsgiApp) -> Callable[[dict[str, Any], object], dict[str, object]]:
    """Adapt API Gateway HTTP API payload v2 without a second web framework.

    API Gateway route configuration is a perimeter control, while FastAPI's
    production factory remains the authoritative in-process allowlist.
    """

    def handler(event: dict[str, Any], _context: object) -> dict[str, object]:
        return asyncio.run(_invoke_asgi(app, event))

    return handler


async def _invoke_asgi(app: AsgiApp, event: Mapping[str, Any]) -> dict[str, object]:
    request_context = event.get("requestContext")
    http_context = request_context.get("http") if isinstance(request_context, Mapping) else None
    if not isinstance(http_context, Mapping):
        raise ValueError("API Gateway HTTP API event lacks requestContext.http")
    method = http_context.get("method")
    if not isinstance(method, str) or not method:
        raise ValueError("API Gateway HTTP API event lacks an HTTP method")

    raw_path = event.get("rawPath") or http_context.get("path") or "/"
    if not isinstance(raw_path, str) or not raw_path.startswith("/"):
        raise ValueError("API Gateway HTTP API event has an invalid path")
    # HTTP API payload-v2 events for a named stage include the stage segment in
    # rawPath.  It is API Gateway routing metadata, not part of Quantify's
    # public route allowlist.  Preserve it as ASGI root_path and dispatch the
    # remaining application path to FastAPI.
    stage = request_context.get("stage") if isinstance(request_context, Mapping) else None
    root_path = ""
    if isinstance(stage, str) and stage:
        stage_prefix = f"/{stage}"
        if raw_path == stage_prefix:
            root_path = stage_prefix
            raw_path = "/"
        elif raw_path.startswith(f"{stage_prefix}/"):
            root_path = stage_prefix
            raw_path = raw_path[len(stage_prefix) :]
    headers = event.get("headers") or {}
    if not isinstance(headers, Mapping):
        raise ValueError("API Gateway HTTP API event has invalid headers")
    raw_body = event.get("body") or ""
    if not isinstance(raw_body, str):
        raise ValueError("API Gateway HTTP API event has an invalid body")
    try:
        body = (
            base64.b64decode(raw_body, validate=True)
            if event.get("isBase64Encoded")
            else raw_body.encode("utf-8")
        )
    except ValueError as error:
        raise ValueError("API Gateway HTTP API body is not valid base64") from error

    normalized_headers = [
        (str(name).lower().encode("latin-1"), str(value).encode("latin-1"))
        for name, value in headers.items()
    ]
    host = str(headers.get("host", "lambda"))
    source_ip = str(http_context.get("sourceIp", ""))
    raw_query_string = event.get("rawQueryString") or ""
    if not isinstance(raw_query_string, str):
        raise ValueError("API Gateway HTTP API event has an invalid query string")
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": str(headers.get("x-forwarded-proto", "https")),
        "path": unquote(raw_path),
        "raw_path": raw_path.encode("utf-8"),
        "query_string": raw_query_string.encode("utf-8"),
        "headers": normalized_headers,
        "server": (host, 443),
        "client": (source_ip, 0),
        "root_path": root_path,
    }
    received = False
    response_status: int | None = None
    response_headers: list[tuple[bytes, bytes]] = []
    response_body: list[bytes] = []

    async def receive() -> dict[str, Any]:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        nonlocal response_status, response_headers
        if message["type"] == "http.response.start":
            response_status = int(message["status"])
            response_headers = list(message.get("headers", ()))
        elif message["type"] == "http.response.body":
            response_body.append(message.get("body", b""))

    await app(scope, receive, send)
    if response_status is None:
        raise RuntimeError("ASGI application did not start an HTTP response")

    body_bytes = b"".join(response_body)
    response: dict[str, object] = {
        "statusCode": response_status,
        "headers": {},
        "isBase64Encoded": False,
    }
    header_values: dict[str, str] = {}
    cookies: list[str] = []
    for raw_name, raw_value in response_headers:
        name = raw_name.decode("latin-1")
        value = raw_value.decode("latin-1")
        if name.lower() == "set-cookie":
            cookies.append(value)
        else:
            header_values[name] = value
    response["headers"] = header_values
    if cookies:
        response["cookies"] = cookies
    try:
        response["body"] = body_bytes.decode("utf-8")
    except UnicodeDecodeError:
        response["body"] = base64.b64encode(body_bytes).decode("ascii")
        response["isBase64Encoded"] = True
    return response


@lru_cache(maxsize=1)
def _production_handler() -> Callable[[dict[str, Any], object], dict[str, object]]:
    return create_api_gateway_handler(create_aws_production_app())


def handler(event: dict[str, Any], context: object) -> dict[str, object]:
    """AWS Lambda handler configured by ``deploy/aws/template.yaml``."""

    return _production_handler()(event, context)
