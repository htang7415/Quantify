from __future__ import annotations

import pytest

from quantify.agent_tool import QuantifyAgentTool, agent_safe_result


def _response() -> dict[str, object]:
    return {
        "claim_results": [
            {"claim_id": "claim-supported", "verdict": "verified"},
            {"claim_id": "claim-defeated", "verdict": "defeated"},
        ],
        "review_items": [],
        "evidence_scope": {
            "source": "SEC EDGAR", "entity_level_only": True,
            "forms": ["10-K"], "snapshot_manifest_hash": "a" * 64,
        },
        "audit_manifest": {"manifest_hash": "b" * 64},
    }


def test_agent_result_preserves_verdicts_scope_and_audit_without_advice() -> None:
    result = agent_safe_result(_response())
    assert result["verdicts"] == _response()["claim_results"]
    assert result["requires_agent_resolution"] is False
    assert result["audit_manifest_hash"] == "b" * 64
    assert "investment advice" in result["limitation"]


def test_agent_result_marks_review_or_resolution_for_human_handling() -> None:
    response = _response()
    response["review_items"] = [{"reason": "ambiguous"}]
    assert agent_safe_result(response)["requires_agent_resolution"] is True


def test_agent_result_rejects_wrong_scope_or_unknown_verdict() -> None:
    response = _response()
    response["evidence_scope"]["source"] = "web"
    with pytest.raises(ValueError, match="scope"):
        agent_safe_result(response)
    response = _response()
    response["claim_results"][0]["verdict"] = "buy"
    with pytest.raises(ValueError, match="verdict"):
        agent_safe_result(response)


def test_agent_tool_delegates_exactly_one_verification_call() -> None:
    class _Verifier:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def verify(self, **kwargs: str) -> dict[str, object]:
            self.calls.append(kwargs)
            return _response()

    verifier = _Verifier()
    result = QuantifyAgentTool(verifier).quantify_verify(
        cik="0000789019", analysis="Microsoft revenue increased.", as_of_date="2024-07-30"
    )
    assert verifier.calls == [{"cik": "0000789019", "analysis": "Microsoft revenue increased.", "as_of_date": "2024-07-30"}]
    assert result["verdicts"][0]["verdict"] == "verified"
