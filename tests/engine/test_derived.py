from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from quantify.engine import EvidenceValue, derive_margin, derive_total_debt


def _fact(metric: str, value: str, evidence_id: str, *, period_start: date = date(2023, 7, 1)) -> EvidenceValue:
    return EvidenceValue(
        evidence_id=evidence_id,
        entity_cik="0000789019",
        metric=metric,
        value=Decimal(value),
        unit="USD",
        period_start=period_start,
        period_end=date(2024, 6, 30),
        accession="0000950170-24-087843",
        filed_at=date(2024, 7, 30),
        source_url="https://www.sec.gov/Archives/edgar/data/789019/000095017024087843/msft-20240630.htm",
    )


def test_derives_microsoft_total_debt_with_component_provenance() -> None:
    debt = derive_total_debt(
        current=_fact("debt_current", "2249000000", "msft-debt-current", period_start=date(2024, 6, 30)),
        noncurrent=_fact("debt_noncurrent", "42688000000", "msft-debt-noncurrent", period_start=date(2024, 6, 30)),
    )

    assert debt.value == Decimal("44937000000")
    assert debt.derived_from_evidence_ids == ("msft-debt-current", "msft-debt-noncurrent")


def test_derives_microsoft_margins_deterministically() -> None:
    revenue = _fact("revenue", "245122000000", "msft-revenue")
    gross_profit = _fact("gross_profit", "171008000000", "msft-gross-profit")
    operating_income = _fact("operating_income", "109433000000", "msft-operating-income")
    cash_flow = _fact("operating_cash_flow", "118548000000", "msft-cash-flow")

    assert derive_margin(metric="gross_margin", numerator=gross_profit, revenue=revenue).value == Decimal("0.69764444")
    assert derive_margin(metric="operating_margin", numerator=operating_income, revenue=revenue).value == Decimal("0.44644300")
    assert derive_margin(metric="cash_flow_margin", numerator=cash_flow, revenue=revenue).value == Decimal("0.48362856")


def test_rejects_ineligible_or_incompatible_derived_inputs() -> None:
    revenue = _fact("revenue", "245122000000", "msft-revenue")
    gross_profit = _fact("gross_profit", "171008000000", "msft-gross-profit")

    with pytest.raises(ValueError, match="eligible"):
        derive_margin(metric="gross_margin", numerator=replace(gross_profit, eligible=False), revenue=revenue)
    with pytest.raises(ValueError, match="full period"):
        derive_margin(metric="gross_margin", numerator=replace(gross_profit, period_start=date(2023, 10, 1)), revenue=revenue)
