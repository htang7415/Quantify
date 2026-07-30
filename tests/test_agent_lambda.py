from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from quantify import agent_lambda


def _event(
    *, body: object, path: str = "/v1/agent/verify", method: str = "POST", stage: str | None = None,
    source_ip: str = "203.0.113.9", headers: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "version": "2.0",
        "rawPath": path,
        "body": body,
        "isBase64Encoded": False,
        "requestContext": {"http": {"method": method, "sourceIp": source_ip}, **({"stage": stage} if stage else {})},
        **({"headers": headers} if headers is not None else {}),
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


def test_anonymous_trial_reserves_capacity_before_invoking_the_private_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reserved: list[str] = []

    monkeypatch.setattr(agent_lambda, "_reserve_anonymous_trial", lambda **_: reserved.append("yes"))
    monkeypatch.setattr(agent_lambda, "invoke_quantify_verify", lambda **_: _safe_result())

    response = agent_lambda.handler(
        _event(
            path="/v1/trial/verify",
            body=json.dumps({"cik": "0000789019", "analysis": "Microsoft revenue increased.", "as_of_date": "2024-07-30"}),
        ),
        object(),
    )

    assert response["statusCode"] == 200
    assert reserved == ["yes"]


def test_anonymous_trial_fails_closed_before_invoking_the_private_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent_lambda,
        "_reserve_anonymous_trial",
        lambda **_: (_ for _ in ()).throw(agent_lambda.TrialLimitError("limit")),
    )
    monkeypatch.setattr(agent_lambda, "invoke_quantify_verify", lambda **_: pytest.fail("core invoked"))

    response = agent_lambda.handler(
        _event(path="/v1/trial/verify", body=json.dumps({"cik": "0000789019", "analysis": "Microsoft revenue increased.", "as_of_date": "2024-07-30"})),
        object(),
    )

    assert response["statusCode"] == 429
    assert json.loads(response["body"]) == {"error": "trial_limit_reached"}


def test_anonymous_trial_accepts_only_the_cloudfront_origin_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reserved: list[str] = []
    admission = SimpleNamespace(
        origin_key="a" * 32,
        reserve=lambda *, source_ip: reserved.append(source_ip),
    )
    monkeypatch.setitem(__import__("sys").modules, "boto3", SimpleNamespace(client=lambda _: object()))
    monkeypatch.setattr(agent_lambda, "load_anonymous_trial_admission", lambda **_: admission)
    request_context = {"http": {"method": "POST", "sourceIp": "198.51.100.7"}}

    agent_lambda._reserve_anonymous_trial(
        event={"headers": {"X-Quantify-Trial-Origin": "a" * 32, "X-Forwarded-For": "203.0.113.9, 10.0.0.1"}},
        request_context=request_context,
    )

    assert reserved == ["203.0.113.9"]
    with pytest.raises(agent_lambda.TrialUnavailableError):
        agent_lambda._reserve_anonymous_trial(event={"headers": {}}, request_context=request_context)


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
