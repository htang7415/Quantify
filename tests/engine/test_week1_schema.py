from __future__ import annotations

import pytest

from quantify.engine import (
    EvidenceSnapshot,
    MeasurementMode,
    MetricComparisonClaim,
    Relation,
    SourceType,
    VerificationOutcome,
    verify_claim,
)
from tests.conftest import load_snapshot


def test_week1_closed_schema_vocabularies_are_stable() -> None:
    assert Relation.OUTSIDE_UPPER_BASELINE.value == "outside_upper_baseline"
    assert MeasurementMode.EXACT.value == "exact"
    assert SourceType.SEC_COMPANY_FACTS.value == "sec_company_facts"


def test_snapshot_hash_includes_source_and_declared_visibility() -> None:
    evidence = load_snapshot("msft_revenue_regression.json").evidence
    baseline = EvidenceSnapshot.freeze(
        snapshot_id="week1-contract",
        evidence=evidence,
        source_type=SourceType.SEC_COMPANY_FACTS,
    )
    restricted = EvidenceSnapshot.freeze(
        snapshot_id="week1-contract",
        evidence=evidence,
        source_type=SourceType.SEC_COMPANY_FACTS,
        visible_evidence_ids=("msft-revenue-fy2024",),
    )
    different_source = EvidenceSnapshot.freeze(
        snapshot_id="week1-contract",
        evidence=evidence,
        source_type=SourceType.USER_DECLARED_CORPUS,
    )

    assert baseline.visible_evidence_ids is None
    assert restricted.visible_evidence_ids == ("msft-revenue-fy2024",)
    assert baseline.manifest_hash != restricted.manifest_hash
    assert baseline.manifest_hash != different_source.manifest_hash


def test_snapshot_rejects_visibility_ids_not_in_the_full_pool() -> None:
    evidence = load_snapshot("msft_revenue_regression.json").evidence

    with pytest.raises(ValueError, match="visible evidence IDs"):
        EvidenceSnapshot.freeze(
            snapshot_id="invalid-visibility",
            evidence=evidence,
            source_type=SourceType.SEC_COMPANY_FACTS,
            visible_evidence_ids=("not-in-snapshot",),
        )

    with pytest.raises(ValueError, match="must be unique"):
        EvidenceSnapshot.freeze(
            snapshot_id="duplicate-visibility",
            evidence=evidence,
            source_type=SourceType.SEC_COMPANY_FACTS,
            visible_evidence_ids=("msft-revenue-fy2024", "msft-revenue-fy2024"),
        )


def test_verifier_uses_full_pool_not_reserved_visibility_mask() -> None:
    evidence = load_snapshot("msft_revenue_regression.json").evidence
    snapshot = EvidenceSnapshot.freeze(
        snapshot_id="full-pool-verifier",
        evidence=evidence,
        source_type=SourceType.SEC_COMPANY_FACTS,
        visible_evidence_ids=("msft-revenue-fy2024",),
    )

    result = verify_claim(
        snapshot=snapshot,
        claim=MetricComparisonClaim(
            claim_id="full-pool-still-applies",
            left_evidence_id="msft-revenue-fy2024",
            relation=Relation.GREATER_THAN,
            right_evidence_id="msft-revenue-fy2023",
        ),
    )

    assert result.outcome is VerificationOutcome.VERIFIED
