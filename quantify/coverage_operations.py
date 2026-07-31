"""Measured issuer-coverage planning; availability never exceeds approved releases."""
from __future__ import annotations
from dataclasses import dataclass
from quantify.release_operations import ReleaseCatalog

@dataclass(frozen=True, slots=True)
class FactoryMetrics:
    issuers_completed: int; reviewer_hours: float; automated_pass_rate_basis_points: int; correction_rate_basis_points: int; source_freshness_days: int
    def __post_init__(self):
        if self.issuers_completed < 0 or self.reviewer_hours < 0 or not 0 <= self.automated_pass_rate_basis_points <= 10_000 or not 0 <= self.correction_rate_basis_points <= 10_000 or self.source_freshness_days < 0: raise ValueError("factory metrics are invalid")
    @property
    def issuers_per_reviewer_hour(self) -> float: return self.issuers_completed / self.reviewer_hours if self.reviewer_hours else 0.0

@dataclass(frozen=True, slots=True)
class CoverageDecision:
    release_id: str; serve: bool; reason: str

def issuer_coverage_decision(*, catalog: ReleaseCatalog, release_id: str, metrics: FactoryMetrics, minimum_pass_rate_basis_points: int, maximum_correction_rate_basis_points: int, maximum_source_freshness_days: int) -> CoverageDecision:
    if catalog.serving_entry(release_id=release_id) is None: return CoverageDecision(release_id,False,"release_not_approved")
    if metrics.automated_pass_rate_basis_points < minimum_pass_rate_basis_points: return CoverageDecision(release_id,False,"quality_below_threshold")
    if metrics.correction_rate_basis_points > maximum_correction_rate_basis_points: return CoverageDecision(release_id,False,"correction_rate_above_threshold")
    if metrics.source_freshness_days > maximum_source_freshness_days: return CoverageDecision(release_id,False,"source_stale")
    return CoverageDecision(release_id,True,"approved_measured_coverage")
