from __future__ import annotations

import json

import pytest

from quantify.sdk import QuantifyClient, QuantifySdkError, parse_public_verification
from quantify.tool_adapter import execute_quantify_verify_tool, quantify_verify_tool_definition


_SAFE = {"verdicts": [{"claim_id": "c1", "verdict": "verified"}], "requires_agent_resolution": False, "evidence_scope": {"source": "SEC EDGAR", "forms": ["10-K"], "snapshot_manifest_hash": "a" * 64}, "audit_manifest_hash": "b" * 64, "limitation": "Verdicts apply only to frozen evidence; they are not investment advice."}


def test_sdk_preserves_complete_safe_contract_and_tool_schema() -> None:
    client = QuantifyClient(endpoint="https://agent.example/verify", transport=lambda _: (200, json.dumps(_SAFE).encode()))
    result = execute_quantify_verify_tool(client=client, access_token="token", arguments={"cik": "0000789019", "analysis": "Microsoft revenue increased.", "as_of_date": "2024-07-30"})

    assert result == _SAFE
    assert quantify_verify_tool_definition()["input_schema"]["additionalProperties"] is False


def test_sdk_rejects_report_text_or_unsafe_response_fields() -> None:
    with pytest.raises(QuantifySdkError):
        parse_public_verification({**_SAFE, "report_text": "private"})
