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
    metrics = {item.metric for item in snapshot.evidence if item.eligible}
    requests = []
    if not {"gross_profit", "operating_income", "net_income"}.intersection(metrics): requests.append(EvidenceRequestType.PROFITABILITY_METRICS)
    if "operating_cash_flow" not in metrics: requests.append(EvidenceRequestType.CASH_FLOW_METRICS)
    if not {"cash", "debt"}.issubset(metrics): requests.append(EvidenceRequestType.BALANCE_SHEET_METRICS)
    if "diluted_share_count" not in metrics: requests.append(EvidenceRequestType.DILUTION_METRICS)
    return tuple(requests)
