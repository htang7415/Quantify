"""Deterministic evidence-coverage assessment for bounded acquisition."""

from __future__ import annotations

from enum import StrEnum

from quantify.engine import EvidenceSnapshot

class EvidenceRequestType(StrEnum):
    PRIOR_ANNUAL_PERIOD = "prior_annual_period"
    PRIOR_QUARTER = "prior_quarter"
    PROFITABILITY_METRICS = "profitability_metrics"
    CASH_FLOW_METRICS = "cash_flow_metrics"
    BALANCE_SHEET_METRICS = "balance_sheet_metrics"
    DILUTION_METRICS = "dilution_metrics"


def assess_coverage(*, snapshot: EvidenceSnapshot) -> tuple[EvidenceRequestType, ...]:
    """Return unmet, closed-vocabulary evidence needs in canonical order."""

    metrics = {item.metric for item in snapshot.evidence if item.eligible}
    annual_facts = [
        item
        for item in snapshot.evidence
        if (item.period_end - item.period_start).days >= 300
    ]
    interim_facts = [
        item
        for item in snapshot.evidence
        if 0 < (item.period_end - item.period_start).days < 300
    ]
    requests: list[EvidenceRequestType] = []
    if not annual_facts:
        requests.append(EvidenceRequestType.PRIOR_ANNUAL_PERIOD)
    if not interim_facts:
        requests.append(EvidenceRequestType.PRIOR_QUARTER)
    if not {"gross_profit", "operating_income", "net_income"}.issubset(metrics):
        requests.append(EvidenceRequestType.PROFITABILITY_METRICS)
    if not {"operating_cash_flow", "capital_expenditure"}.issubset(metrics):
        requests.append(EvidenceRequestType.CASH_FLOW_METRICS)
    if not {"cash", "debt_current", "debt_noncurrent"}.issubset(metrics):
        requests.append(EvidenceRequestType.BALANCE_SHEET_METRICS)
    if "diluted_share_count" not in metrics:
        requests.append(EvidenceRequestType.DILUTION_METRICS)
    return tuple(requests)
