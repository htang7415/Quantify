"""Deterministic per-tenant admission policy for the future account path."""

from __future__ import annotations

from dataclasses import dataclass


class TenantQuotaExceededError(RuntimeError):
    """Raised before a tenant request can reach the model-backed verifier."""


@dataclass(frozen=True, slots=True)
class TenantQuotaPolicy:
    """Initial free-account limits, expressed in replayable integer units."""

    version: str = "tenant-quota-v1"
    daily_request_limit: int = 5
    daily_cost_limit_micro_usd: int = 15_000
    request_cost_reservation_micro_usd: int = 2_500

    def __post_init__(self) -> None:
        if min(
            self.daily_request_limit,
            self.daily_cost_limit_micro_usd,
            self.request_cost_reservation_micro_usd,
        ) <= 0 or self.request_cost_reservation_micro_usd > self.daily_cost_limit_micro_usd:
            raise ValueError("tenant quota policy is invalid")

    def admits(self, *, request_count: int, reserved_micro_usd: int) -> bool:
        """Return whether one more request fits both hard daily limits."""

        if request_count < 0 or reserved_micro_usd < 0:
            raise ValueError("tenant usage is invalid")
        return (
            request_count < self.daily_request_limit
            and reserved_micro_usd
            <= self.daily_cost_limit_micro_usd - self.request_cost_reservation_micro_usd
        )

    def require_admission(self, *, request_count: int, reserved_micro_usd: int) -> None:
        if not self.admits(request_count=request_count, reserved_micro_usd=reserved_micro_usd):
            raise TenantQuotaExceededError("tenant daily quota is exhausted")
