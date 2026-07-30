from __future__ import annotations

import json

import pytest

from quantify import agent_lambda


def _event(
    *, body: object, path: str = "/v1/agent/verify", method: str = "POST", stage: str | None = None
) -> dict[str, object]:
    return {
        "version": "2.0",
        "rawPath": path,
        "body": body,
        "isBase64Encoded": False,
        "requestContext": {"http": {"method": method}, **({"stage": stage} if stage else {})},
    }


def _safe_result() -> dict[str, object]:
    return {
        "verdicts": [{"claim_id": "claim-1", "verdict": "verified"}],
        "requires_agent_resolution": False,
        "evidence_scope": {
            "source": "SEC EDGAR",
            "entity_level_only": True,
            "forms": ["10-K"],
            "snapshot_manifest_hash": "a" * 64,
        },
        "audit_manifest_hash": "b" * 64,
        "limitation": "not investment advice",
    }


def test_public_agent_route_returns_only_safe_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def invoke(**kwargs: str) -> dict[str, object]:
        captured.update(kwargs)
        return _safe_result()

    monkeypatch.setattr(agent_lambda, "invoke_quantify_verify", invoke)
    response = agent_lambda.handler(
        _event(body=json.dumps({"cik": "0000789019", "analysis": "Microsoft revenue increased.", "as_of_date": "2024-07-30"})),
        object(),
    )

    assert response["statusCode"] == 200
    assert response["headers"] == {"content-type": "application/json; charset=utf-8"}
    assert json.loads(response["body"]) == _safe_result()
    assert captured == {
        "cik": "0000789019",
        "analysis": "Microsoft revenue increased.",
        "as_of_date": "2024-07-30",
    }


def test_public_agent_route_accepts_api_gateway_named_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_lambda, "invoke_quantify_verify", lambda **_: _safe_result())

    response = agent_lambda.handler(
        _event(
            path="/production/v1/agent/verify",
            stage="production",
            body=json.dumps({"cik": "0000789019", "analysis": "Microsoft revenue increased.", "as_of_date": "2024-07-30"}),
        ),
        object(),
    )

    assert response["statusCode"] == 200


@pytest.mark.parametrize(
    "event",
    [
        _event(body="not json"),
        _event(body=json.dumps({"cik": "not-a-cik", "analysis": "Microsoft revenue increased.", "as_of_date": "2024-07-30"})),
        _event(body=json.dumps({"cik": "0000789019", "analysis": "Microsoft revenue increased.", "as_of_date": "30-07-2024"})),
    ],
)
def test_public_agent_route_rejects_bad_input_without_invoking_core(
    event: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent_lambda, "invoke_quantify_verify", lambda **_: pytest.fail("core invoked"))

    response = agent_lambda.handler(event, object())

    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {"error": "invalid_request"}


def test_public_agent_route_hides_core_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_lambda, "invoke_quantify_verify", lambda **_: (_ for _ in ()).throw(RuntimeError("api key=secret")))

    response = agent_lambda.handler(
        _event(body=json.dumps({"cik": "0000789019", "analysis": "Microsoft revenue increased.", "as_of_date": "2024-07-30"})),
        object(),
    )

    assert response["statusCode"] == 502
    assert json.loads(response["body"]) == {"error": "verification_unavailable"}
    assert "secret" not in response["body"]


def test_public_agent_route_is_narrow_and_direct_invocation_keeps_working(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_lambda, "invoke_quantify_verify", lambda **_: _safe_result())

    method_response = agent_lambda.handler(_event(body="{}", method="GET"), object())
    path_response = agent_lambda.handler(_event(body="{}", path="/healthz"), object())
    direct_response = agent_lambda.handler(
        {"cik": "0000789019", "analysis": "Microsoft revenue increased.", "as_of_date": "2024-07-30"},
        object(),
    )

    assert method_response["statusCode"] == path_response["statusCode"] == 404
    assert direct_response == _safe_result()
