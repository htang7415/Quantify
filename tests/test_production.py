from __future__ import annotations

from decimal import Decimal
import json

import pytest
from fastapi.testclient import TestClient

from quantify.engine import MetricThresholdClaim, Relation, ReportSpan, StatementClassification
from quantify.harness import ExtractedStatement, ExtractionResult, validate_extraction
from quantify.harness.observability import RequestMetrics
from quantify.harness.sec.client import SecCompanyFactsClient
from quantify.production import (
    DEFAULT_FIXTURES_DIRECTORY,
    ProductionConfigurationError,
    create_production_app,
    emit_request_metrics,
)
from tests.conftest import load_snapshot


class _Transport:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.calls = 0
        self.unavailable = unavailable

    def post_json(self, *, url, headers, body, timeout_seconds):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.unavailable:
            raise RuntimeError("pinned model is unavailable")
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "statements": [
                                            {
                                                "classification": "non_factual",
                                                "report_span_id": "report-s1",
                                            }
                                        ]
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }


def _app(*, transport: _Transport, audit_manifest_sink=None) -> TestClient:
    return TestClient(
        create_production_app(
            api_key="test-key",
            image_digest="sha256:test-image",
            transport=transport,
            audit_manifest_sink=audit_manifest_sink,
        )
    )


def _request() -> dict[str, object]:
    return {
        "analysis": "Microsoft reports financial results.",
        "as_of_date": "2024-07-30",
        "forms": ["10-K"],
    }


def test_production_factory_enforces_the_private_route_allowlist() -> None:
    api = _app(transport=_Transport())

    assert {route.path for route in api.app.routes} == {
        "/healthz",
        "/v1/companies/{cik}/verify",
    }
    assert api.get("/healthz").json() == {"status": "ok"}
    assert api.post("/v1/companies/789019/review", json=_request()).status_code == 404
    assert api.post("/v1/verify/batch", json={"items": []}).status_code == 404


def test_production_factory_requires_key_and_image_digest() -> None:
    with pytest.raises(ProductionConfigurationError, match="GEMINI_API_KEY"):
        create_production_app(image_digest="sha256:test-image")
    with pytest.raises(ProductionConfigurationError, match="IMAGE_DIGEST"):
        create_production_app(api_key="test-key")


def test_embedded_fixture_hash_failure_blocks_factory(tmp_path) -> None:
    (tmp_path / "aapl_companyfacts.json").write_text("{}")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "fixtures": [
                    {
                        "path": "aapl_companyfacts.json",
                        "cik": "0000320193",
                        "source_url": "https://data.sec.gov/example",
                        "retrieved_at": "2026-07-28T21:54:18Z",
                        "payload_sha256": "0" * 64,
                    }
                ]
            }
        )
    )

    with pytest.raises(ProductionConfigurationError, match="hash mismatch"):
        create_production_app(
            fixtures_directory=tmp_path,
            api_key="test-key",
            image_digest="sha256:test-image",
        )


def test_production_request_uses_one_model_call_and_embedded_evidence_only(monkeypatch) -> None:
    transport = _Transport()
    api = _app(transport=transport)

    def _unexpected_live_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("production must not fetch live SEC data")

    monkeypatch.setattr(SecCompanyFactsClient, "fetch_company_facts", _unexpected_live_fetch)
    first = api.post("/v1/companies/789019/verify", json=_request())
    second = api.post("/v1/companies/789019/verify", json=_request())

    assert first.status_code == second.status_code == 200
    assert transport.calls == 1
    assert first.json()["audit_manifest"]["deployment_image_digest"] == "sha256:test-image"
    assert first.json()["audit_manifest"]["evidence_fixture_manifest_hash"] == (
        __import__("hashlib").sha256(
            (DEFAULT_FIXTURES_DIRECTORY / "manifest.json").read_bytes()
        ).hexdigest()
    )
    audit = first.json()["audit_manifest"]
    assert audit["evidence_release_manifest_hash"] == audit[
        "evidence_fixture_manifest_hash"
    ]
    assert len(audit["runtime_policy_bundle_hash"]) == 64
    assert len(audit["release_gate_policy_hash"]) == 64


def test_production_persists_the_canonical_manifest_before_returning_a_verdict() -> None:
    stored: list[dict[str, object]] = []

    response = _app(transport=_Transport(), audit_manifest_sink=stored.append).post(
        "/v1/companies/789019/verify", json=_request()
    )

    assert response.status_code == 200
    assert len(stored) == 1
    assert stored[0]["manifest_hash"] == response.json()["audit_manifest"]["manifest_hash"]
    assert _request()["analysis"] not in json.dumps(stored[0])


def test_audit_persistence_failure_returns_typed_503_without_logging_report_text(caplog) -> None:
    request = _request()

    def unavailable_store(_manifest: object) -> None:
        raise RuntimeError("storage unavailable")

    with caplog.at_level("WARNING", logger="quantify.request_failure"):
        response = _app(
            transport=_Transport(), audit_manifest_sink=unavailable_store
        ).post("/v1/companies/789019/verify", json=request)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "audit_manifest_unavailable"
    message = caplog.messages[-1]
    assert request["analysis"] not in message
    assert json.loads(message.removeprefix("quantify_request_failure=")) == {
        "code": "audit_manifest_unavailable",
        "event": "audit_manifest_unavailable",
        "status_code": 503,
    }


def test_production_metrics_log_contains_aggregate_fields_but_not_report_text(caplog) -> None:
    report_text = "Confidential analysis text must never enter request metrics."

    with caplog.at_level("INFO", logger="quantify.request_metrics"):
        emit_request_metrics(
            RequestMetrics(
                cache_hit=True,
                sec_network_calls=0,
                filings_selected=1,
                evidence_count=3,
                eligible_evidence_count=3,
                rejected_evidence_count=0,
                verified_count=1,
                unsupported_count=0,
                defeated_count=0,
                qualified_count=0,
                agent_resolution_count=0,
                empty_result=False,
                total_cost=0.0,
                company_cik="0000789019",
            )
        )

    message = caplog.messages[-1]
    assert message.startswith("quantify_request_metrics={")
    assert report_text not in message
    payload = json.loads(message.removeprefix("quantify_request_metrics="))
    assert payload["observability_schema_version"] == "1.0.0"
    assert payload["company_cik"] == "0000789019"


def test_unavailable_pinned_model_returns_typed_503_without_logging_report_text(caplog) -> None:
    request = _request()
    with caplog.at_level("WARNING", logger="quantify.request_failure"):
        response = _app(transport=_Transport(unavailable=True)).post(
            "/v1/companies/789019/verify", json=request
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "pinned_model_unavailable"
    message = caplog.messages[-1]
    assert message.startswith("quantify_request_failure={")
    assert request["analysis"] not in message
    assert json.loads(message.removeprefix("quantify_request_failure=")) == {
        "code": "pinned_model_unavailable",
        "event": "pinned_model_unavailable",
        "status_code": 503,
    }


def test_production_rejects_oversized_reports_before_model_extraction() -> None:
    transport = _Transport()
    response = _app(transport=transport).post(
        "/v1/companies/789019/verify",
        json={**_request(), "analysis": "word " * 251},
    )

    assert response.status_code == 422
    assert transport.calls == 0


def _statement(*, statement_id: str, span_id: str, claim_id: str, threshold: str) -> ExtractedStatement:
    report = "Microsoft revenue exceeded the stated threshold."
    return ExtractedStatement(
        statement_id=statement_id,
        classification=StatementClassification.CLASSIFIED,
        report_span=ReportSpan(
            span_id=span_id,
            sentence_text=report,
            sentence_start=0,
            sentence_end=len(report),
            claim_fragment="Microsoft revenue exceeded the stated threshold",
            fragment_start=0,
            fragment_end=len("Microsoft revenue exceeded the stated threshold"),
        ),
        claims=(
            MetricThresholdClaim(
                claim_id=claim_id,
                cited_evidence_id="msft-revenue-fy2024",
                relation=Relation.GREATER_THAN,
                threshold=Decimal(threshold),
            ),
        ),
    )


def test_semantic_duplicates_collapse_and_retain_all_source_spans() -> None:
    report = "Microsoft revenue exceeded the stated threshold."
    validated = validate_extraction(
        report_text=report,
        snapshot=load_snapshot("msft_revenue_regression.json"),
        extraction=ExtractionResult(
            extractor_version="fixture",
            statements=(
                _statement(statement_id="s-a", span_id="span-a", claim_id="claim-a", threshold="1.0"),
                _statement(statement_id="s-b", span_id="span-b", claim_id="claim-b", threshold="1.00"),
            ),
        ),
    )

    assert [claim.claim_id for claim in validated.claims] == ["claim-a"]
    assert validated.canonical_claim_source_spans == (("claim-a", ("span-a", "span-b")),)


def test_more_than_six_distinct_claims_fails_closed() -> None:
    report = "Microsoft revenue exceeded the stated threshold."
    validated = validate_extraction(
        report_text=report,
        snapshot=load_snapshot("msft_revenue_regression.json"),
        extraction=ExtractionResult(
            extractor_version="fixture",
            statements=tuple(
                _statement(
                    statement_id=f"s-{index}",
                    span_id=f"span-{index}",
                    claim_id=f"claim-{index}",
                    threshold=str(index),
                )
                for index in range(7)
            ),
        ),
    )

    assert validated.claims == ()
    assert [item.statement_id for item in validated.review_items] == [
        "extraction-claim-limit"
    ]
