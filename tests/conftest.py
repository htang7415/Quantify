from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from quantify.engine import EvidenceSnapshot, EvidenceValue


FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "sec"


def load_snapshot(filename: str, *, allow_conflicting_evidence: bool = False) -> EvidenceSnapshot:
    fixture = json.loads((FIXTURE_ROOT / filename).read_text())
    evidence = tuple(
        EvidenceValue(
            evidence_id=item["evidence_id"],
            entity_cik=item["entity_cik"],
            metric=item["metric"],
            value=Decimal(item["value"]),
            unit=item["unit"],
            period_start=date.fromisoformat(item["period_start"]),
            period_end=date.fromisoformat(item["period_end"]),
            accession=item["accession"],
            filed_at=date.fromisoformat(item["filed_at"]),
            source_url=item["source_url"],
        )
        for item in fixture["evidence"]
    )
    return EvidenceSnapshot.freeze(
        snapshot_id=f"{Path(filename).stem}-v1",
        evidence=evidence,
        allow_conflicting_evidence=allow_conflicting_evidence,
    )
