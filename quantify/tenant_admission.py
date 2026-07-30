"""Fail-closed atomic admission for authenticated Quantify tenants."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass


class TenantQuotaExceededError(RuntimeError):
    """The tenant has exhausted its declared daily request or cost budget."""


class TenantLedgerUnavailableError(RuntimeError):
    """The service cannot safely prove tenant capacity remains."""


class DynamoTenantClient:
    def transact_write_items(self, **kwargs: object) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class TenantQuotaPolicy:
    """Replayable quota policy expressed entirely in integer micro-USD units."""

    version: str = "tenant-quota-v1"
    daily_request_limit: int = 5
    daily_cost_limit_micro_usd: int = 15_000
    request_cost_reservation_micro_usd: int = 2_500

    def __post_init__(self) -> None:
        values = (
            self.daily_request_limit,
            self.daily_cost_limit_micro_usd,
            self.request_cost_reservation_micro_usd,
        )
        if any(value <= 0 for value in values) or (
            self.request_cost_reservation_micro_usd > self.daily_cost_limit_micro_usd
        ):
            raise ValueError("tenant quota policy is invalid")

    def admits(self, *, request_count: int, reserved_micro_usd: int) -> bool:
        if request_count < 0 or reserved_micro_usd < 0:
            raise ValueError("tenant usage is invalid")
        return (
            request_count < self.daily_request_limit
            and reserved_micro_usd
            <= self.daily_cost_limit_micro_usd - self.request_cost_reservation_micro_usd
        )

    def require_admission(self, *, request_count: int, reserved_micro_usd: int) -> None:
        if not self.admits(
            request_count=request_count, reserved_micro_usd=reserved_micro_usd
        ):
            raise TenantQuotaExceededError("tenant daily quota is exhausted")


@dataclass(frozen=True, slots=True)
class TenantAdmission:
    """Reserve capacity before an authenticated request can reach the core."""

    table_name: str
    policy: TenantQuotaPolicy
    client: DynamoTenantClient

    def reserve(self, *, tenant_id: str, now: dt.datetime | None = None) -> None:
        if not tenant_id.strip():
            raise TenantLedgerUnavailableError("tenant identity is unavailable")
        current = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
        day = current.strftime("%Y-%m-%d")
        expiry_epoch = int((current + dt.timedelta(days=2)).timestamp())
        try:
            self.client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": self.table_name,
                            "Key": {"bucket": {"S": f"tenant#{tenant_id}#{day}"}},
                            "UpdateExpression": (
                                "SET request_count = if_not_exists(request_count, :zero) + :one, "
                                "reserved_micro_usd = if_not_exists(reserved_micro_usd, :zero) + :cost, "
                                "expires_at = :expires_at"
                            ),
                            "ConditionExpression": (
                                "(attribute_not_exists(request_count) OR request_count < :request_limit) "
                                "AND (attribute_not_exists(reserved_micro_usd) OR "
                                "reserved_micro_usd <= :remaining_cost)"
                            ),
                            "ExpressionAttributeValues": {
                                ":zero": {"N": "0"},
                                ":one": {"N": "1"},
                                ":cost": {
                                    "N": str(
                                        self.policy.request_cost_reservation_micro_usd
                                    )
                                },
                                ":request_limit": {
                                    "N": str(self.policy.daily_request_limit)
                                },
                                ":remaining_cost": {
                                    "N": str(
                                        self.policy.daily_cost_limit_micro_usd
                                        - self.policy.request_cost_reservation_micro_usd
                                    )
                                },
                                ":expires_at": {"N": str(expiry_epoch)},
                            },
                        }
                    }
                ]
            )
        except Exception as error:
            response = getattr(error, "response", None)
            code = (
                response.get("Error", {}).get("Code")
                if isinstance(response, Mapping)
                else None
            )
            if code == "TransactionCanceledException":
                raise TenantQuotaExceededError("tenant daily quota is exhausted") from error
            raise TenantLedgerUnavailableError("tenant admission ledger is unavailable") from error


def load_tenant_admission(
    *, environment: Mapping[str, str], client: DynamoTenantClient
) -> TenantAdmission:
    """Load an authenticated tenant boundary; malformed configuration fails closed."""

    required = (
        "QUANTIFY_TENANT_USAGE_LEDGER_TABLE_NAME",
        "QUANTIFY_TENANT_DAILY_REQUEST_LIMIT",
        "QUANTIFY_TENANT_DAILY_COST_LIMIT_MICRO_USD",
        "QUANTIFY_TENANT_REQUEST_COST_RESERVATION_MICRO_USD",
    )
    values = {name: environment.get(name, "") for name in required}
    if not all(values.values()):
        raise TenantLedgerUnavailableError("tenant admission is unavailable")
    try:
        policy = TenantQuotaPolicy(
            daily_request_limit=int(values["QUANTIFY_TENANT_DAILY_REQUEST_LIMIT"]),
            daily_cost_limit_micro_usd=int(
                values["QUANTIFY_TENANT_DAILY_COST_LIMIT_MICRO_USD"]
            ),
            request_cost_reservation_micro_usd=int(
                values["QUANTIFY_TENANT_REQUEST_COST_RESERVATION_MICRO_USD"]
            ),
        )
    except ValueError as error:
        raise TenantLedgerUnavailableError("tenant admission is unavailable") from error
    return TenantAdmission(
        table_name=values["QUANTIFY_TENANT_USAGE_LEDGER_TABLE_NAME"],
        policy=policy,
        client=client,
    )
