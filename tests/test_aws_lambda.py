from __future__ import annotations

import json

from fastapi import FastAPI
import pytest

from quantify.aws_lambda import (
    create_api_gateway_handler,
    create_aws_production_app,
    load_pinned_gemini_api_key,
)
from quantify.api import create_app
from quantify.production import ProductionConfigurationError


def _event(*, method: str, path: str, body: str = "", stage: str | None = None) -> dict:
    return {
        "version": "2.0",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {
            "host": "example.execute-api.us-east-2.amazonaws.com",
            "content-type": "application/json",
        },
        "requestContext": {
            "http": {"method": method, "path": path, "sourceIp": "127.0.0.1"},
            **({"stage": stage} if stage else {}),
        },
        "body": body,
        "isBase64Encoded": False,
    }


def test_api_gateway_adapter_returns_fastapi_health_response() -> None:
    app = FastAPI()

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    response = create_api_gateway_handler(app)(_event(method="GET", path="/healthz"), object())

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"status": "ok"}
    assert response["isBase64Encoded"] is False


def test_api_gateway_adapter_strips_the_named_stage_from_the_application_path() -> None:
    app = FastAPI()

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    response = create_api_gateway_handler(app)(
        _event(method="GET", path="/staging/healthz", stage="staging"), object()
    )

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"status": "ok"}


def test_api_gateway_adapter_passes_a_json_request_body() -> None:
    app = FastAPI()

    @app.post("/echo")
    def echo(payload: dict[str, str]) -> dict[str, str]:
        return payload

    response = create_api_gateway_handler(app)(
        _event(method="POST", path="/echo", body='{"claim":"grounded"}'), object()
    )

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"claim": "grounded"}


def test_api_gateway_adapter_preserves_production_route_allowlist() -> None:
    class _Service:
        def verify(self, *, cik: str, request: object) -> dict[str, str]:
            return {"cik": cik}

    app = create_app(_Service(), include_internal_routes=False, include_documentation=False)
    response = create_api_gateway_handler(app)(
        _event(method="POST", path="/v1/companies/789019/review", body="{}"), object()
    )

    assert response["statusCode"] == 404


class _SecretClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, str]] = []

    def get_secret_value(self, **kwargs: str) -> dict[str, object]:
        self.calls.append(kwargs)
        return self.response


def test_secret_loader_reads_only_the_pinned_secret_version() -> None:
    client = _SecretClient({"SecretString": "test-key"})
    environment = {
        "QUANTIFY_GEMINI_SECRET_ARN": "arn:aws:secretsmanager:us-east-2:123:secret:key",
        "QUANTIFY_GEMINI_SECRET_VERSION_ID": "a" * 32,
    }

    assert load_pinned_gemini_api_key(environment=environment, secret_client=client) == "test-key"
    assert client.calls == [
        {"SecretId": environment["QUANTIFY_GEMINI_SECRET_ARN"], "VersionId": "a" * 32}
    ]


def test_secret_loader_fails_closed_when_a_pinned_secret_cannot_be_read() -> None:
    with pytest.raises(ProductionConfigurationError, match="required"):
        load_pinned_gemini_api_key(environment={})

    client = _SecretClient({"SecretString": ""})
    with pytest.raises(ProductionConfigurationError, match="empty"):
        load_pinned_gemini_api_key(
            environment={
                "QUANTIFY_GEMINI_SECRET_ARN": "arn:aws:secretsmanager:us-east-2:123:secret:key",
                "QUANTIFY_GEMINI_SECRET_VERSION_ID": "a" * 32,
            },
            secret_client=client,
        )


def test_aws_composition_never_accepts_a_plaintext_gemini_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _SecretClient({"SecretString": "secret-from-manager"})
    environment = {
        "GEMINI_API_KEY": "plaintext-key-must-not-be-used",
        "QUANTIFY_GEMINI_SECRET_ARN": "arn:aws:secretsmanager:us-east-2:123:secret:key",
        "QUANTIFY_GEMINI_SECRET_VERSION_ID": "a" * 32,
        "QUANTIFY_IMAGE_DIGEST": "sha256:" + "1" * 64,
    }
    captured: dict[str, object] = {}

    def fake_create_production_app(**kwargs: object) -> FastAPI:
        captured.update(kwargs)
        return FastAPI()

    monkeypatch.setattr("quantify.aws_lambda.create_production_app", fake_create_production_app)

    create_aws_production_app(environment=environment, secret_client=client)

    assert captured["api_key"] == "secret-from-manager"
    assert captured["image_digest"] == environment["QUANTIFY_IMAGE_DIGEST"]
