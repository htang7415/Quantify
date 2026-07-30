"""Narrow deterministic adapter for an external AI agent using Quantify."""

from __future__ import annotations

import re
from typing import Mapping, Protocol


_HASH = re.compile(r"^[0-9a-f]{64}$")
_VERDICTS = {
    "verified",
    "unsupported",
    "defeated",
    "qualified",
    "requires_agent_resolution",
}
_LIMITATION = (
    "Verdicts apply only to the declared frozen SEC evidence snapshot; "
    "they are not investment advice."
)


class QuantifyVerifier(Protocol):
    def verify(self, *, cik: str, analysis: str, as_of_date: str) -> Mapping[str, object]: ...


def agent_safe_result(response: Mapping[str, object]) -> dict[str, object]:
    """Validate a V1 result and expose only agent-safe, decision-neutral fields."""

    scope = response.get("evidence_scope")
    audit = response.get("audit_manifest")
    claims = response.get("claim_results")
    if not isinstance(scope, Mapping) or not isinstance(audit, Mapping) or not isinstance(claims, list):
        raise ValueError("Quantify response does not match the V1 tool contract")
    if scope.get("source") != "SEC EDGAR" or scope.get("entity_level_only") is not True:
        raise ValueError("Quantify response has an unsupported evidence scope")
    snapshot_hash = scope.get("snapshot_manifest_hash")
    audit_hash = audit.get("manifest_hash")
    if not isinstance(snapshot_hash, str) or not _HASH.fullmatch(snapshot_hash):
        raise ValueError("Quantify response has an invalid snapshot manifest hash")
    if not isinstance(audit_hash, str) or not _HASH.fullmatch(audit_hash):
        raise ValueError("Quantify response has an invalid audit manifest hash")
    verdicts: list[dict[str, str]] = []
    for claim in claims:
        if not isinstance(claim, Mapping):
            raise ValueError("Quantify response has an invalid claim result")
        claim_id, verdict = claim.get("claim_id"), claim.get("verdict")
        if not isinstance(claim_id, str) or not claim_id or verdict not in _VERDICTS:
            raise ValueError("Quantify response has an invalid claim verdict")
        verdicts.append({"claim_id": claim_id, "verdict": verdict})
    return {
        "verdicts": verdicts,
        "requires_agent_resolution": any(
            item["verdict"] == "requires_agent_resolution" for item in verdicts
        ) or bool(response.get("review_items")),
        "evidence_scope": {
            "source": "SEC EDGAR",
            "forms": scope.get("forms", []),
            "snapshot_manifest_hash": snapshot_hash,
        },
        "audit_manifest_hash": audit_hash,
        "limitation": _LIMITATION,
    }


class QuantifyAgentTool:
    """One tool call for an agent; transport and IAM stay outside this boundary."""

    def __init__(self, verifier: QuantifyVerifier) -> None:
        self._verifier = verifier

    def quantify_verify(self, *, cik: str, analysis: str, as_of_date: str) -> dict[str, object]:
        return agent_safe_result(
            self._verifier.verify(cik=cik, analysis=analysis, as_of_date=as_of_date)
        )
