"""Auditable derivation of debt and margin metrics from eligible inputs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext
from hashlib import sha256

from .schemas import EvidenceValue


def _require_eligible(*items: EvidenceValue) -> None:
    if not all(item.eligible for item in items):
        raise ValueError("derived metrics require eligible input evidence")


def _derived_id(metric: str, inputs: tuple[EvidenceValue, ...]) -> str:
    material = ":".join(sorted(item.evidence_id for item in inputs))
    return f"derived-{metric}-{sha256(material.encode()).hexdigest()[:16]}"


def derive_total_debt(*, current: EvidenceValue, noncurrent: EvidenceValue) -> EvidenceValue:
    """Aggregate current and noncurrent debt only for the same entity/date/unit."""

    _require_eligible(current, noncurrent)
    if (
        current.entity_cik != noncurrent.entity_cik
        or current.unit != noncurrent.unit
        or current.period_end != noncurrent.period_end
    ):
        raise ValueError("debt components must share entity, unit, and period end")
    inputs = (current, noncurrent)
    return EvidenceValue(
        evidence_id=_derived_id("debt", inputs),
        entity_cik=current.entity_cik,
        metric="debt",
        value=current.value + noncurrent.value,
        unit=current.unit,
        period_start=current.period_end,
        period_end=current.period_end,
        accession=f"derived:{_derived_id('debt', inputs)}",
        filed_at=max(item.filed_at for item in inputs),
        source_url=current.source_url,
        derived_from_evidence_ids=tuple(sorted(item.evidence_id for item in inputs)),
    )


def derive_margin(*, metric: str, numerator: EvidenceValue, revenue: EvidenceValue) -> EvidenceValue:
    """Derive a dimensionless margin with shared entity/unit/period semantics."""

    _require_eligible(numerator, revenue)
    if (
        numerator.entity_cik != revenue.entity_cik
        or numerator.unit != revenue.unit
        or numerator.period_start != revenue.period_start
        or numerator.period_end != revenue.period_end
    ):
        raise ValueError("margin inputs must share entity, unit, and full period")
    if revenue.value == 0:
        raise ValueError("cannot derive a margin from zero revenue")
    inputs = (numerator, revenue)
    with localcontext() as context:
        context.prec = 28
        value = (numerator.value / revenue.value).quantize(Decimal("0.00000001"))
    return EvidenceValue(
        evidence_id=_derived_id(metric, inputs),
        entity_cik=numerator.entity_cik,
        metric=metric,
        value=value,
        unit="ratio",
        period_start=numerator.period_start,
        period_end=numerator.period_end,
        accession=f"derived:{_derived_id(metric, inputs)}",
        filed_at=max(item.filed_at for item in inputs),
        source_url=numerator.source_url,
        derived_from_evidence_ids=tuple(sorted(item.evidence_id for item in inputs)),
    )
