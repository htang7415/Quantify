from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from quantify.engine import (
    EvidenceEligibilityReason,
    EvidenceSnapshot,
    EvidenceValue,
    RestatementPolicy,
    MetricThresholdClaim,
    Relation,
    VerificationOutcome,
    analyze_claims,
    freeze_selected_snapshot,
    verify_claim,
)


FIXTURE_PATH = (
    Path(__file__).parents[2] / "fixtures" / "sec" / "quantum_revenue_restatement.json"
)


@pytest.fixture()
def quantum_evidence() -> tuple[EvidenceValue, ...]:
    fixture = json.loads(FIXTURE_PATH.read_text())
    return tuple(
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


def test_snapshot_rejects_unresolved_eligible_restatements(
    quantum_evidence: tuple[EvidenceValue, ...],
) -> None:
    with pytest.raises(ValueError, match="unresolved eligible facts"):
        EvidenceSnapshot.freeze(
            snapshot_id="invalid-unresolved-restatement", evidence=quantum_evidence
        )


def test_latest_available_policy_selects_restated_facts(
    quantum_evidence: tuple[EvidenceValue, ...],
) -> None:
    snapshot, selection = freeze_selected_snapshot(
        snapshot_id="quantum-current-v1",
        evidence=quantum_evidence,
        policy=RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
        as_of_date=date(2024, 6, 28),
    )

    assert tuple(item.evidence_id for item in snapshot.evidence) == (
        "qtm-revenue-fy2022-restated",
        "qtm-revenue-fy2023-restated",
    )
    assert selection.superseded_evidence_ids == (
        "qtm-revenue-fy2022-as-filed",
        "qtm-revenue-fy2023-as-filed",
    )
    assert all(
        decision.reason is EvidenceEligibilityReason.ELIGIBLE
        for decision in selection.eligibility_decisions
        if decision.evidence_id in selection.selected_evidence_ids
    )


def test_as_filed_policy_preserves_original_facts(
    quantum_evidence: tuple[EvidenceValue, ...],
) -> None:
    snapshot, selection = freeze_selected_snapshot(
        snapshot_id="quantum-historical-v1",
        evidence=tuple(reversed(quantum_evidence)),
        policy=RestatementPolicy.AS_FILED_AT_CUTOFF,
        as_of_date=date(2024, 6, 28),
    )

    assert tuple(item.evidence_id for item in snapshot.evidence) == (
        "qtm-revenue-fy2022-as-filed",
        "qtm-revenue-fy2023-as-filed",
    )
    assert selection.selected_evidence_ids == (
        "qtm-revenue-fy2022-as-filed",
        "qtm-revenue-fy2023-as-filed",
    )


def test_cutoff_excludes_later_restatement(
    quantum_evidence: tuple[EvidenceValue, ...],
) -> None:
    snapshot, selection = freeze_selected_snapshot(
        snapshot_id="quantum-before-restatement-v1",
        evidence=quantum_evidence,
        policy=RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
        as_of_date=date(2023, 12, 31),
    )

    assert tuple(item.evidence_id for item in snapshot.evidence) == (
        "qtm-revenue-fy2022-as-filed",
        "qtm-revenue-fy2023-as-filed",
    )
    assert {
        decision.evidence_id: decision.reason
        for decision in selection.eligibility_decisions
    }["qtm-revenue-fy2023-restated"] is EvidenceEligibilityReason.FUTURE_FILING


def test_policy_selected_snapshot_excludes_superseded_counterevidence(
    quantum_evidence: tuple[EvidenceValue, ...],
) -> None:
    snapshot, _ = freeze_selected_snapshot(
        snapshot_id="quantum-current-v1",
        evidence=quantum_evidence,
        policy=RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
        as_of_date=date(2024, 6, 28),
    )
    claim = MetricThresholdClaim(
        claim_id="fy2023-revenue-under-415m",
        cited_evidence_id="qtm-revenue-fy2023-restated",
        relation=Relation.LESS_THAN,
        threshold=Decimal("415000000"),
    )

    assert verify_claim(snapshot=snapshot, claim=claim).outcome is VerificationOutcome.UNSUPPORTED
    assert analyze_claims(snapshot=snapshot, claims=(claim,)).counterevidence_pairs == ()
