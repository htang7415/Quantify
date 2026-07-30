"""Fail-closed admission control for Quantify's time-bounded anonymous trial."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
from collections.abc import Mapping
from dataclasses import dataclass


_LOGGER = logging.getLogger(__name__)


class TrialUnavailableError(RuntimeError):
    """The anonymous trial is disabled, expired, or cannot safely admit work."""


class TrialLimitError(TrialUnavailableError):
    """A per-IP, request, or reserved-cost trial cap was reached."""


class TrialLedgerUnavailableError(TrialUnavailableError):
    """The trial ledger cannot prove that this request fits the configured cap."""


class DynamoTrialClient:
    def transact_write_items(self, **kwargs: object) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class AnonymousTrialAdmission:
    """Reserve bounded anonymous capacity without retaining a raw source IP."""

    table_name: str
    per_ip_daily_limit: int
    daily_request_limit: int
    daily_cost_limit_micro_usd: int
    request_cost_reservation_micro_usd: int
    ip_hash_key: str
    origin_key: str
    expires_at: dt.datetime
    client: DynamoTrialClient

    def reserve(self, *, source_ip: str, now: dt.datetime | None = None) -> None:
        current = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
        if current >= self.expires_at or not source_ip:
            raise TrialUnavailableError("anonymous trial is unavailable")
        day = current.strftime("%Y-%m-%d")
        ip_hash = hmac.new(
            self.ip_hash_key.encode(), source_ip.encode(), hashlib.sha256
        ).hexdigest()
        expiry_epoch = int((current + dt.timedelta(days=2)).timestamp())
        try:
            self.client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": self.table_name,
                            "Key": {"bucket": {"S": f"ip#{day}#{ip_hash}"}},
                            "UpdateExpression": "SET request_count = if_not_exists(request_count, :zero) + :one, expires_at = :expires_at",
                            "ConditionExpression": "attribute_not_exists(request_count) OR request_count < :per_ip_limit",
                            "ExpressionAttributeValues": {
                                ":zero": {"N": "0"},
                                ":one": {"N": "1"},
                                ":per_ip_limit": {"N": str(self.per_ip_daily_limit)},
                                ":expires_at": {"N": str(expiry_epoch)},
                            },
                        }
                    },
                    {
                        "Update": {
                            "TableName": self.table_name,
                            "Key": {"bucket": {"S": f"day#{day}"}},
                            "UpdateExpression": "SET request_count = if_not_exists(request_count, :zero) + :one, reserved_micro_usd = if_not_exists(reserved_micro_usd, :zero) + :cost, expires_at = :expires_at",
                            "ConditionExpression": "(attribute_not_exists(request_count) OR request_count < :daily_request_limit) AND (attribute_not_exists(reserved_micro_usd) OR reserved_micro_usd <= :remaining_cost)",
                            "ExpressionAttributeValues": {
                                ":zero": {"N": "0"},
                                ":one": {"N": "1"},
                                ":cost": {"N": str(self.request_cost_reservation_micro_usd)},
                                ":daily_request_limit": {"N": str(self.daily_request_limit)},
                                ":remaining_cost": {
                                    "N": str(
                                        self.daily_cost_limit_micro_usd
                                        - self.request_cost_reservation_micro_usd
                                    )
                                },
                                ":expires_at": {"N": str(expiry_epoch)},
                            },
                        }
                    },
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
                raise TrialLimitError("anonymous trial limit reached") from error
            _LOGGER.warning(
                "anonymous trial ledger transaction unavailable: %s",
                code or type(error).__name__,
            )
            raise TrialLedgerUnavailableError("anonymous trial ledger is unavailable") from error


def load_anonymous_trial_admission(
    *, environment: Mapping[str, str], client: DynamoTrialClient
) -> AnonymousTrialAdmission:
    if environment.get("QUANTIFY_TRIAL_ENABLED") != "true":
        raise TrialUnavailableError("anonymous trial is unavailable")
    required = (
        "QUANTIFY_TRIAL_LEDGER_TABLE_NAME",
        "QUANTIFY_TRIAL_PER_IP_DAILY_LIMIT",
        "QUANTIFY_TRIAL_DAILY_REQUEST_LIMIT",
        "QUANTIFY_TRIAL_DAILY_COST_LIMIT_MICRO_USD",
        "QUANTIFY_TRIAL_REQUEST_COST_RESERVATION_MICRO_USD",
        "QUANTIFY_TRIAL_IP_HASH_KEY",
        "QUANTIFY_TRIAL_ORIGIN_KEY",
        "QUANTIFY_TRIAL_EXPIRES_AT",
    )
    values = {name: environment.get(name, "") for name in required}
    if not all(values.values()):
        raise TrialUnavailableError("anonymous trial is unavailable")
    try:
        expires_at = dt.datetime.fromisoformat(
            values["QUANTIFY_TRIAL_EXPIRES_AT"].replace("Z", "+00:00")
        )
        if expires_at.tzinfo is None:
            raise ValueError
        limits = {
            name: int(values[name])
            for name in (
                "QUANTIFY_TRIAL_PER_IP_DAILY_LIMIT",
                "QUANTIFY_TRIAL_DAILY_REQUEST_LIMIT",
                "QUANTIFY_TRIAL_DAILY_COST_LIMIT_MICRO_USD",
                "QUANTIFY_TRIAL_REQUEST_COST_RESERVATION_MICRO_USD",
            )
        }
    except ValueError as error:
        raise TrialUnavailableError("anonymous trial is unavailable") from error
    if (
        any(value <= 0 for value in limits.values())
        or limits["QUANTIFY_TRIAL_REQUEST_COST_RESERVATION_MICRO_USD"]
        > limits["QUANTIFY_TRIAL_DAILY_COST_LIMIT_MICRO_USD"]
    ):
        raise TrialUnavailableError("anonymous trial is unavailable")
    return AnonymousTrialAdmission(
        table_name=values["QUANTIFY_TRIAL_LEDGER_TABLE_NAME"],
        per_ip_daily_limit=limits["QUANTIFY_TRIAL_PER_IP_DAILY_LIMIT"],
        daily_request_limit=limits["QUANTIFY_TRIAL_DAILY_REQUEST_LIMIT"],
        daily_cost_limit_micro_usd=limits["QUANTIFY_TRIAL_DAILY_COST_LIMIT_MICRO_USD"],
        request_cost_reservation_micro_usd=limits[
            "QUANTIFY_TRIAL_REQUEST_COST_RESERVATION_MICRO_USD"
        ],
        ip_hash_key=values["QUANTIFY_TRIAL_IP_HASH_KEY"],
        origin_key=values["QUANTIFY_TRIAL_ORIGIN_KEY"],
        expires_at=expires_at.astimezone(dt.UTC),
        client=client,
    )
