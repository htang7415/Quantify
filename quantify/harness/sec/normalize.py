"""Deterministic normalization for the initial SEC revenue metric."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from quantify.engine import EvidenceValue


REVENUE_CONCEPT = "RevenueFromContractWithCustomerExcludingAssessedTax"


def normalize_revenue_facts(
    *, company_facts: dict, source_url: str, forms: tuple[str, ...] = ("10-K", "10-Q")
) -> tuple[EvidenceValue, ...]:
    """Normalize attributable USD revenue facts with complete SEC provenance.

    This initial router intentionally accepts only the standardized US-GAAP
    revenue concept. Custom tags and derived metrics remain outside this layer.
    """

    cik = str(company_facts["cik"]).zfill(10)
    units = company_facts["facts"]["us-gaap"][REVENUE_CONCEPT]["units"]["USD"]
    normalized: list[EvidenceValue] = []
    for item in units:
        if (
            item.get("form") not in forms
            or item.get("fp") != "FY"
            or not item.get("start")
            or not item.get("accn")
        ):
            continue
        normalized.append(
            EvidenceValue(
                evidence_id=(
                    f"{cik}-revenue-{item['end']}-{item['accn'].replace('-', '')}"
                ),
                entity_cik=cik,
                metric="revenue",
                value=Decimal(str(item["val"])),
                unit="USD",
                period_start=date.fromisoformat(item["start"]),
                period_end=date.fromisoformat(item["end"]),
                accession=item["accn"],
                filed_at=date.fromisoformat(item["filed"]),
                source_url=source_url,
            )
        )
    return tuple(sorted(normalized, key=lambda evidence: evidence.evidence_id))
