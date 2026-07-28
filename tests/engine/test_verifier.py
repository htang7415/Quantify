from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tests.conftest import load_snapshot

from quantify.engine import (
    EvidenceSnapshot,
    EvidenceValue,
    MetricComparisonClaim,
    MetricThresholdClaim,
    Relation,
    SourceType,
    VerificationOutcome,
    analyze_claims,
    verify_claim,
)


FIXTURE_PATH = (
    Path(__file__).parents[2] / "fixtures" / "sec" / "quantum_revenue_restatement.json"
)


@pytest.fixture()
def quantum_snapshot() -> EvidenceSnapshot:
    return load_snapshot("quantum_revenue_restatement.json", allow_conflicting_evidence=True)


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


def test_returns_verified_for_a_period_to_period_claim(
    quantum_snapshot: EvidenceSnapshot,
) -> None:
    result = verify_claim(
        snapshot=quantum_snapshot,
        claim=MetricComparisonClaim(
            claim_id="fy2023-revenue-exceeded-fy2022",
            left_evidence_id="qtm-revenue-fy2023-as-filed",
            relation=Relation.GREATER_THAN,
            right_evidence_id="qtm-revenue-fy2022-as-filed",
        ),
    )

    assert result.outcome is VerificationOutcome.VERIFIED
    assert result.cited_evidence_ids == (
        "qtm-revenue-fy2023-as-filed",
        "qtm-revenue-fy2022-as-filed",
    )


def test_returns_unsupported_for_an_unwarranted_period_to_period_claim(
    quantum_snapshot: EvidenceSnapshot,
) -> None:
    result = verify_claim(
        snapshot=quantum_snapshot,
        claim=MetricComparisonClaim(
            claim_id="fy2023-revenue-below-fy2022",
            left_evidence_id="qtm-revenue-fy2023-as-filed",
            relation=Relation.LESS_THAN,
            right_evidence_id="qtm-revenue-fy2022-as-filed",
        ),
    )

    assert result.outcome is VerificationOutcome.UNSUPPORTED


def test_rejects_incompatible_period_to_period_claims(
    quantum_snapshot: EvidenceSnapshot,
) -> None:
    incompatible_evidence = EvidenceValue(
        evidence_id="qtm-revenue-fy2022-eur",
        entity_cik="0000709283",
        metric="revenue",
        value=Decimal("372827000"),
        unit="EUR",
        period_start=date(2021, 4, 1),
        period_end=date(2022, 3, 31),
        accession="0000709283-23-000013",
        filed_at=date(2023, 6, 6),
        source_url="https://www.sec.gov/Archives/edgar/data/709283/000070928323000013/qtm-20230331.htm",
    )
    snapshot = EvidenceSnapshot.freeze(
        snapshot_id="unit-mismatch-v1",
        evidence=(
            quantum_snapshot.evidence_by_id("qtm-revenue-fy2023-as-filed"),
            incompatible_evidence,
        ),
        source_type=SourceType.SEC_COMPANY_FACTS,
    )

    result = verify_claim(
        snapshot=snapshot,
        claim=MetricComparisonClaim(
            claim_id="mismatched-units",
            left_evidence_id="qtm-revenue-fy2023-as-filed",
            relation=Relation.GREATER_THAN,
            right_evidence_id="qtm-revenue-fy2022-eur",
        ),
    )

    assert result.outcome is VerificationOutcome.UNSUPPORTED


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


def test_analyze_claims_keeps_local_warrant_and_ce1_separate(
    quantum_snapshot: EvidenceSnapshot,
) -> None:
    analysis = analyze_claims(
        snapshot=quantum_snapshot,
        claims=(
            MetricThresholdClaim(
                claim_id="unsupported",
                cited_evidence_id="qtm-revenue-fy2023-as-filed",
                relation=Relation.LESS_THAN,
                threshold=Decimal("400000000"),
            ),
            MetricThresholdClaim(
                claim_id="countered",
                cited_evidence_id="qtm-revenue-fy2023-as-filed",
                relation=Relation.LESS_THAN,
                threshold=Decimal("415000000"),
            ),
        ),
    )

    assert [(item.claim_id, item.passed) for item in analysis.local_warrants] == [
        ("countered", True),
        ("unsupported", False),
    ]
    assert [(item.claim_id, item.evidence_id) for item in analysis.counterevidence_pairs] == [
        ("countered", "qtm-revenue-fy2023-restated"),
    ]


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
        source_type=SourceType.SEC_COMPANY_FACTS,
        allow_conflicting_evidence=True,
    )

    assert repeated_snapshot.manifest_hash == quantum_snapshot.manifest_hash
    assert verify_claim(snapshot=quantum_snapshot, claim=claim) == verify_claim(
        snapshot=repeated_snapshot, claim=claim
    )
