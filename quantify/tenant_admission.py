"""Deterministic per-tenant admission policy for the future account path."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from collections.abc import Mapping


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
        if min(self.daily_request_limit, self.daily_cost_limit_micro_usd, self.request_cost_reservation_micro_usd) <= 0 or self.request_cost_reservation_micro_usd > self.daily_cost_limit_micro_usd:
            raise ValueError("tenant quota policy is invalid")

    def admits(self, *, request_count: int, reserved_micro_usd: int) -> bool:
        if request_count < 0 or reserved_micro_usd < 0:
            raise ValueError("tenant usage is invalid")
        return request_count < self.daily_request_limit and reserved_micro_usd <= self.daily_cost_limit_micro_usd - self.request_cost_reservation_micro_usd

    def require_admission(self, *, request_count: int, reserved_micro_usd: int) -> None:
        if not self.admits(request_count=request_count, reserved_micro_usd=reserved_micro_usd):
            raise TenantQuotaExceededError("tenant daily quota is exhausted")


@dataclass(frozen=True, slots=True)
class TenantAdmission:
    """Atomic DynamoDB reservation boundary for one authenticated tenant."""

    table_name: str
    policy: TenantQuotaPolicy
    client: object

    def reserve(self, *, tenant_id: str, now: dt.datetime | None = None) -> None:
        if not tenant_id.strip():
            raise ValueError("tenant identity is required")
        current = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
        day = current.strftime("%Y-%m-%d")
        try:
            getattr(self.client, "transact_write_items")(
                TransactItems=[{"Update": {"TableName": self.table_name,
                    "Key": {"bucket": {"S": f"tenant#{tenant_id}#{day}"}},
                    "UpdateExpression": "SET request_count = if_not_exists(request_count, :zero) + :one, reserved_micro_usd = if_not_exists(reserved_micro_usd, :zero) + :cost, expires_at = :expires_at",
                    "ConditionExpression": "(attribute_not_exists(request_count) OR request_count < :request_limit) AND (attribute_not_exists(reserved_micro_usd) OR reserved_micro_usd <= :remaining_cost)",
                    "ExpressionAttributeValues": {":zero": {"N": "0"}, ":one": {"N": "1"}, ":cost": {"N": str(self.policy.request_cost_reservation_micro_usd)}, ":request_limit": {"N": str(self.policy.daily_request_limit)}, ":remaining_cost": {"N": str(self.policy.daily_cost_limit_micro_usd - self.policy.request_cost_reservation_micro_usd)}, ":expires_at": {"N": str(int((current + dt.timedelta(days=2)).timestamp()))}}}}]
            )
        except Exception as error:
            response = getattr(error, "response", None)
            if isinstance(response, Mapping) and response.get("Error", {}).get("Code") == "TransactionCanceledException":
                raise TenantQuotaExceededError("tenant daily quota is exhausted") from error
            raise RuntimeError("tenant admission ledger is unavailable") from error
