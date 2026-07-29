"""Deterministic normalization for the initial SEC fundamentals metrics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from quantify.engine import EvidenceValue


from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricRoute:
    metric: str
    concept: str
    unit: str
    requires_duration: bool


INITIAL_METRIC_ROUTES = (
    MetricRoute("revenue", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD", True),
    MetricRoute("gross_profit", "GrossProfit", "USD", True),
    MetricRoute("operating_income", "OperatingIncomeLoss", "USD", True),
    MetricRoute("net_income", "NetIncomeLoss", "USD", True),
    MetricRoute("operating_cash_flow", "NetCashProvidedByUsedInOperatingActivities", "USD", True),
    MetricRoute("capital_expenditure", "PaymentsToAcquirePropertyPlantAndEquipment", "USD", True),
    MetricRoute("cash", "CashAndCashEquivalentsAtCarryingValue", "USD", False),
    MetricRoute("debt_current", "LongTermDebtCurrent", "USD", False),
    MetricRoute("debt_noncurrent", "LongTermDebtNoncurrent", "USD", False),
    MetricRoute("diluted_share_count", "WeightedAverageNumberOfDilutedSharesOutstanding", "shares", True),
)
REVENUE_CONCEPT = INITIAL_METRIC_ROUTES[0].concept


def normalize_company_facts(
    *,
    company_facts: dict,
    source_url: str,
    forms: tuple[str, ...] = ("10-K", "10-Q"),
    routes: tuple[MetricRoute, ...] = INITIAL_METRIC_ROUTES,
) -> tuple[EvidenceValue, ...]:
    """Normalize routed standardized facts with complete SEC provenance.

    Missing standardized concepts are simply absent from the output. Custom tags,
    debt aggregation, and derived margins remain explicit later policy work.
    """

    cik = str(company_facts["cik"]).zfill(10)
    normalized: list[EvidenceValue] = []
    gaap_facts = company_facts["facts"].get("us-gaap", {})
    for route in routes:
        units = gaap_facts.get(route.concept, {}).get("units", {}).get(route.unit, ())
        for item in units:
            if item.get("form") not in forms or item.get("fp") != "FY" or not item.get("accn"):
                continue
            if route.requires_duration and not item.get("start"):
                continue
            period_end = date.fromisoformat(item["end"])
            period_start = (
                date.fromisoformat(item["start"]) if route.requires_duration else period_end
            )
            normalized.append(
                EvidenceValue(
                    evidence_id=(
                        f"{cik}-{route.metric}-{period_start.isoformat()}-"
                        f"{period_end.isoformat()}-{item['accn'].replace('-', '')}"
                    ),
                    entity_cik=cik,
                    metric=route.metric,
                    value=Decimal(str(item["val"])),
                    unit=route.unit,
                    period_start=period_start,
                    period_end=period_end,
                    accession=item["accn"],
                    filed_at=date.fromisoformat(item["filed"]),
                    source_url=source_url,
                )
            )
    return tuple(sorted(normalized, key=lambda evidence: evidence.evidence_id))


def normalize_revenue_facts(
    *, company_facts: dict, source_url: str, forms: tuple[str, ...] = ("10-K", "10-Q")
) -> tuple[EvidenceValue, ...]:
    """Compatibility wrapper for the first revenue-only snapshot builder."""

    return normalize_company_facts(
        company_facts=company_facts,
        source_url=source_url,
        forms=forms,
        routes=(INITIAL_METRIC_ROUTES[0],),
    )
