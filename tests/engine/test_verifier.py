from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from quantify.engine import (
    EvidenceSnapshot,
    EvidenceValue,
    MetricThresholdClaim,
    Relation,
    VerificationOutcome,
    verify_claim,
)


FIXTURE_PATH = (
    Path(__file__).parents[2] / "fixtures" / "sec" / "quantum_revenue_restatement.json"
)


@pytest.fixture()
def quantum_snapshot() -> EvidenceSnapshot:
    fixture = json.loads(FIXTURE_PATH.read_text())
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
        snapshot_id="quantum-revenue-restatement-v1", evidence=evidence
    )


def test_returns_verified_when_all_compatible_facts_support_claim(
    quantum_snapshot: EvidenceSnapshot,
) -> None:
    result = verify_claim(
        snapshot=quantum_snapshot,
        claim=MetricThresholdClaim(
            claim_id="fy2023-revenue-over-400m",
            cited_evidence_id="qtm-revenue-fy2023-as-filed",
            relation=Relation.GREATER_THAN,
            threshold=Decimal("400000000"),
        ),
    )

    assert result.outcome is VerificationOutcome.VERIFIED
    assert result.counterevidence_evidence_ids == ()


def test_returns_unsupported_when_cited_fact_does_not_warrant_claim(
    quantum_snapshot: EvidenceSnapshot,
) -> None:
    result = verify_claim(
        snapshot=quantum_snapshot,
        claim=MetricThresholdClaim(
            claim_id="fy2023-revenue-under-400m",
            cited_evidence_id="qtm-revenue-fy2023-as-filed",
            relation=Relation.LESS_THAN,
            threshold=Decimal("400000000"),
        ),
    )

    assert result.outcome is VerificationOutcome.UNSUPPORTED
    assert result.counterevidence_evidence_ids == ()


def test_returns_counterevidence_for_a_real_subsequent_restatement(
    quantum_snapshot: EvidenceSnapshot,
) -> None:
    result = verify_claim(
        snapshot=quantum_snapshot,
        claim=MetricThresholdClaim(
            claim_id="fy2023-revenue-under-415m",
            cited_evidence_id="qtm-revenue-fy2023-as-filed",
            relation=Relation.LESS_THAN,
            threshold=Decimal("415000000"),
        ),
    )

    assert result.outcome is VerificationOutcome.COUNTEREVIDENCE
    assert result.counterevidence_evidence_ids == ("qtm-revenue-fy2023-restated",)


def test_frozen_snapshot_and_verification_are_deterministic(
    quantum_snapshot: EvidenceSnapshot,
) -> None:
    claim = MetricThresholdClaim(
        claim_id="fy2023-revenue-over-400m",
        cited_evidence_id="qtm-revenue-fy2023-as-filed",
        relation=Relation.GREATER_THAN,
        threshold=Decimal("400000000"),
    )

    repeated_snapshot = EvidenceSnapshot.freeze(
        snapshot_id=quantum_snapshot.snapshot_id,
        evidence=tuple(reversed(quantum_snapshot.evidence)),
    )

    assert repeated_snapshot.manifest_hash == quantum_snapshot.manifest_hash
    assert verify_claim(snapshot=quantum_snapshot, claim=claim) == verify_claim(
        snapshot=repeated_snapshot, claim=claim
    )
