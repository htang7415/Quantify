from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from quantify.engine import (
    EvidenceSnapshot,
    EvidenceValue,
    PersistenceDirection,
    SourceType,
    annotate_temporal_persistence,
)


def _fact(
    *, metric: str, evidence_id: str, value: str, year: int, eligible: bool = True
) -> EvidenceValue:
    return EvidenceValue(
        evidence_id=evidence_id,
        entity_cik="0000789019",
        metric=metric,
        value=Decimal(value),
        unit="USD",
        period_start=date(year - 1, 7, 1),
        period_end=date(year, 6, 30),
        accession=f"0000000000-{year}-000001",
        filed_at=date(year, 7, 30),
        source_url="https://www.sec.gov/Archives/example",
        eligible=eligible,
    )


def test_annotations_are_deterministic_and_do_not_cross_missing_periods() -> None:
    facts = (
        _fact(metric="revenue", evidence_id="revenue-2022", value="100", year=2022),
        _fact(metric="revenue", evidence_id="revenue-2023", value="120", year=2023),
        _fact(metric="revenue", evidence_id="revenue-2024", value="110", year=2024),
        _fact(metric="net_income", evidence_id="income-2022", value="40", year=2022),
        _fact(metric="net_income", evidence_id="income-2023", value="30", year=2023),
        _fact(metric="net_income", evidence_id="income-2024", value="20", year=2024),
        _fact(metric="cash", evidence_id="cash-2020", value="10", year=2020),
        _fact(metric="cash", evidence_id="cash-2022", value="20", year=2022),
        _fact(
            metric="operating_income",
            evidence_id="ineligible-2023",
            value="100",
            year=2023,
            eligible=False,
        ),
    )
    snapshot = EvidenceSnapshot.freeze(
        snapshot_id="persistence-v1",
        evidence=facts,
        source_type=SourceType.SEC_COMPANY_FACTS,
    )

    annotations = annotate_temporal_persistence(snapshot=snapshot)

    assert len(annotations) == 2
    assert annotations[0].metric_name == "net_income"
    assert annotations[0].direction is PersistenceDirection.NEGATIVE
    assert annotations[0].period_ids == ("income-2022", "income-2023", "income-2024")
    assert annotations[1].metric_name == "revenue"
    assert annotations[1].direction is PersistenceDirection.MIXED
    assert annotations[1].period_ids == ("revenue-2022", "revenue-2023", "revenue-2024")


def test_annual_and_year_to_date_facts_are_never_mixed() -> None:
    annual_2023 = _fact(
        metric="revenue", evidence_id="annual-2023", value="100", year=2023
    )
    annual_2024 = _fact(
        metric="revenue", evidence_id="annual-2024", value="120", year=2024
    )
    q1_2023 = replace(
        annual_2023,
        evidence_id="q1-2023",
        value=Decimal("20"),
        period_start=date(2022, 7, 1),
        period_end=date(2022, 9, 30),
    )
    q1_2024 = replace(
        annual_2024,
        evidence_id="q1-2024",
        value=Decimal("30"),
        period_start=date(2023, 7, 1),
        period_end=date(2023, 9, 30),
    )
    snapshot = EvidenceSnapshot.freeze(
        snapshot_id="periods-v1",
        evidence=(annual_2023, annual_2024, q1_2023, q1_2024),
        source_type=SourceType.SEC_COMPANY_FACTS,
    )

    annotations = annotate_temporal_persistence(snapshot=snapshot)

    assert [(item.direction, item.period_ids) for item in annotations] == [
        (PersistenceDirection.POSITIVE, ("annual-2023", "annual-2024")),
        (PersistenceDirection.POSITIVE, ("q1-2023", "q1-2024")),
    ]
