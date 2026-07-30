"""Small provider-neutral SDK for Quantify's safe public verification contract."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen


_HASH = re.compile(r"^[0-9a-f]{64}$")
_VERDICTS = {"verified", "unsupported", "defeated", "qualified", "requires_agent_resolution"}


class QuantifySdkError(RuntimeError):
    """The public endpoint was unavailable or returned an unsafe contract."""


@dataclass(frozen=True, slots=True)
class QuantifyVerification:
    verdicts: tuple[tuple[str, str], ...]
    requires_agent_resolution: bool
    evidence_source: str
    evidence_forms: tuple[str, ...]
    snapshot_manifest_hash: str
    audit_manifest_hash: str
    limitation: str

    def as_dict(self) -> dict[str, object]:
        return {
            "verdicts": [
                {"claim_id": claim_id, "verdict": verdict}
                for claim_id, verdict in self.verdicts
            ],
            "requires_agent_resolution": self.requires_agent_resolution,
            "evidence_scope": {
                "source": self.evidence_source,
                "forms": list(self.evidence_forms),
                "snapshot_manifest_hash": self.snapshot_manifest_hash,
            },
            "audit_manifest_hash": self.audit_manifest_hash,
            "limitation": self.limitation,
        }


def parse_public_verification(payload: object) -> QuantifyVerification:
    """Fail closed unless the response is exactly Quantify's safe public shape."""

    if not isinstance(payload, Mapping) or set(payload) != {
        "verdicts", "requires_agent_resolution", "evidence_scope", "audit_manifest_hash", "limitation"
    }:
        raise QuantifySdkError("Quantify returned an unsafe verification contract")
    evidence = payload["evidence_scope"]
    verdicts = payload["verdicts"]
    if not isinstance(evidence, Mapping) or not isinstance(verdicts, list):
        raise QuantifySdkError("Quantify returned an invalid verification contract")
    source = evidence.get("source")
    forms = evidence.get("forms")
    snapshot = evidence.get("snapshot_manifest_hash")
    audit = payload["audit_manifest_hash"]
    limitation = payload["limitation"]
    if (
        set(evidence) != {"source", "forms", "snapshot_manifest_hash"}
        or not isinstance(source, str)
        or not isinstance(forms, list)
        or not all(isinstance(form, str) and form for form in forms)
        or not isinstance(snapshot, str)
        or not isinstance(audit, str)
        or not _HASH.fullmatch(snapshot)
        or not _HASH.fullmatch(audit)
        or not isinstance(limitation, str)
        or "investment advice" not in limitation.lower()
        or not isinstance(payload["requires_agent_resolution"], bool)
    ):
        raise QuantifySdkError("Quantify returned an invalid verification contract")
    safe_verdicts: list[tuple[str, str]] = []
    for verdict in verdicts:
        if not isinstance(verdict, Mapping) or set(verdict) != {"claim_id", "verdict"}:
            raise QuantifySdkError("Quantify returned an invalid claim verdict")
        claim_id, outcome = verdict.get("claim_id"), verdict.get("verdict")
        if not isinstance(claim_id, str) or not claim_id or outcome not in _VERDICTS:
            raise QuantifySdkError("Quantify returned an invalid claim verdict")
        safe_verdicts.append((claim_id, outcome))
    return QuantifyVerification(
        tuple(safe_verdicts), payload["requires_agent_resolution"], source, tuple(forms), snapshot, audit, limitation
    )


class QuantifyClient:
    """Client for a scoped endpoint; callers provide their own bearer token."""

    def __init__(self, *, endpoint: str, transport: Callable[[Request], tuple[int, bytes]] | None = None) -> None:
        if not endpoint.startswith("https://"):
            raise ValueError("Quantify endpoint must use HTTPS")
        self._endpoint = endpoint
        self._transport = transport or _urlopen_transport

    def verify(self, *, access_token: str, cik: str, analysis: str, as_of_date: str) -> QuantifyVerification:
        if not access_token or not cik or not analysis or not as_of_date:
            raise ValueError("access token and bounded verification inputs are required")
        request = Request(
            self._endpoint,
            data=json.dumps({"cik": cik, "analysis": analysis, "as_of_date": as_of_date}, separators=(",", ":")).encode(),
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            method="POST",
        )
        status, body = self._transport(request)
        if status != 200:
            raise QuantifySdkError(f"Quantify verification failed with HTTP {status}")
        try:
            return parse_public_verification(json.loads(body))
        except json.JSONDecodeError as error:
            raise QuantifySdkError("Quantify returned invalid JSON") from error


def _urlopen_transport(request: Request) -> tuple[int, bytes]:
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - caller supplied HTTPS endpoint.
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()
