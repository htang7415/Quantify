from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

from fastapi import FastAPI
import pytest

from quantify.aws_lambda import (
    DynamoMonthlyCostGuard,
    S3AuditManifestStore,
    create_api_gateway_handler,
    create_aws_production_app,
    load_audit_manifest_store,
    load_monthly_cost_guard,
    load_pinned_gemini_api_key,
)
from quantify.harness.audit import AuditManifest
from quantify.api import create_app
from quantify.production import ProductionConfigurationError
from quantify.runtime import MonthlyCostLimitError


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


class _S3Client:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def put_object(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {}


class _DynamoClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def update_item(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {}


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


def test_audit_manifest_store_writes_only_the_canonical_encrypted_record() -> None:
    client = _S3Client()
    store = S3AuditManifestStore(bucket_name="private-audits", client=client)
    manifest = AuditManifest(
        manifest_version="test",
        analysis_as_of_date=date(2024, 7, 30),
        snapshot_id="snapshot",
        snapshot_manifest_hash="a" * 64,
        source_url="https://data.sec.gov/example",
        source_payload_sha256="b" * 64,
        source_retrieved_at="2024-07-30T00:00:00Z",
        cache_hit=True,
        requested_forms=("10-K",),
        resolved_filing_accessions=("0000000000-00-000001",),
        filing_accessions=("0000000000-00-000001",),
        superseded_filing_accessions=(),
        restatement_policy="as_filed",
        selected_evidence_ids=("evidence-1",),
        superseded_evidence_ids=(),
        selection_rationale="test",
        request_timestamp="2024-07-30T00:00:00Z",
    )
    payload = asdict(manifest)
    payload["analysis_as_of_date"] = manifest.analysis_as_of_date.isoformat()
    payload["manifest_hash"] = manifest.manifest_hash

    store.persist(payload)

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["Bucket"] == "private-audits"
    assert call["Key"] == f"audit-manifests/v1/{manifest.manifest_hash}.json"
    assert call["ContentType"] == "application/json"
    assert call["ServerSideEncryption"] == "aws:kms"
    assert call["BucketKeyEnabled"] is True
    assert call["IfNoneMatch"] == "*"
    persisted = json.loads(call["Body"])
    assert persisted["manifest_hash"] == manifest.manifest_hash
    assert persisted["audit_storage_schema_version"] == "1.0.0"
    assert "cache_hit" not in persisted["manifest"]
    assert "analysis" not in persisted["manifest"]


def test_audit_store_configuration_is_required() -> None:
    with pytest.raises(ProductionConfigurationError, match="QUANTIFY_AUDIT_BUCKET_NAME"):
        load_audit_manifest_store(environment={})


def test_monthly_cost_guard_reserves_before_a_model_call() -> None:
    client = _DynamoClient()
    guard = DynamoMonthlyCostGuard(
        table_name="ledger", monthly_limit_micro_usd=10_000_000, client=client
    )
    guard.reserve()
    assert client.calls[0]["TableName"] == "ledger"
    assert client.calls[0]["ConditionExpression"].startswith("attribute_not_exists")


def test_monthly_cost_guard_requires_its_configuration() -> None:
    with pytest.raises(ProductionConfigurationError, match="COST_LEDGER"):
        load_monthly_cost_guard(environment={})


def test_monthly_cost_guard_fails_closed_at_the_cap() -> None:
    class _AtCapClient:
        def update_item(self, **kwargs: object) -> dict[str, object]:
            error = RuntimeError("conditional")
            error.response = {"Error": {"Code": "ConditionalCheckFailedException"}}  # type: ignore[attr-defined]
            raise error

    guard = DynamoMonthlyCostGuard(
        table_name="ledger", monthly_limit_micro_usd=10_000_000, client=_AtCapClient()
    )
    with pytest.raises(MonthlyCostLimitError):
        guard.reserve()


def test_aws_composition_never_accepts_a_plaintext_gemini_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _SecretClient({"SecretString": "secret-from-manager"})
    environment = {
        "GEMINI_API_KEY": "plaintext-key-must-not-be-used",
        "QUANTIFY_GEMINI_SECRET_ARN": "arn:aws:secretsmanager:us-east-2:123:secret:key",
        "QUANTIFY_GEMINI_SECRET_VERSION_ID": "a" * 32,
        "QUANTIFY_IMAGE_DIGEST": "sha256:" + "1" * 64,
        "QUANTIFY_AUDIT_BUCKET_NAME": "private-audits",
        "QUANTIFY_COST_LEDGER_TABLE_NAME": "private-ledger",
        "QUANTIFY_MONTHLY_COST_LIMIT_MICRO_USD": "10000000",
    }
    captured: dict[str, object] = {}

    def fake_create_production_app(**kwargs: object) -> FastAPI:
        captured.update(kwargs)
        return FastAPI()

    monkeypatch.setattr("quantify.aws_lambda.create_production_app", fake_create_production_app)

    create_aws_production_app(
        environment=environment,
        secret_client=client,
        audit_client=_S3Client(),
        cost_ledger_client=_DynamoClient(),
    )

    assert captured["api_key"] == "secret-from-manager"
    assert captured["image_digest"] == environment["QUANTIFY_IMAGE_DIGEST"]
    assert callable(captured["audit_manifest_sink"])
