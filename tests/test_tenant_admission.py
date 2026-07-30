from __future__ import annotations

import datetime as dt

import pytest

from quantify.tenant_admission import (
    TenantAdmission,
    TenantLedgerUnavailableError,
    TenantQuotaExceededError,
    TenantQuotaPolicy,
    load_tenant_admission,
)


def test_default_free_tenant_policy_admits_within_both_limits() -> None:
    policy = TenantQuotaPolicy()

    assert policy.admits(request_count=4, reserved_micro_usd=12_500)
    assert not policy.admits(request_count=5, reserved_micro_usd=10_000)
    assert not policy.admits(request_count=4, reserved_micro_usd=12_501)


def test_tenant_policy_fails_closed_at_the_limit() -> None:
    with pytest.raises(TenantQuotaExceededError):
        TenantQuotaPolicy().require_admission(request_count=5, reserved_micro_usd=12_500)


def test_tenant_admission_reserves_a_tenant_day_bucket() -> None:
    calls: list[dict[str, object]] = []
    admission = TenantAdmission(
        "tenant-ledger",
        TenantQuotaPolicy(),
        type("Client", (), {"transact_write_items": lambda _, **kwargs: calls.append(kwargs)})(),
    )
    admission.reserve(tenant_id="tenant-1", now=dt.datetime(2026, 7, 30, tzinfo=dt.UTC))
    update = calls[0]["TransactItems"][0]["Update"]
    assert update["TableName"] == "tenant-ledger"
    assert update["Key"] == {"bucket": {"S": "tenant#tenant-1#2026-07-30"}}
    assert "reserved_micro_usd" in update["UpdateExpression"]


def test_tenant_loader_rejects_missing_or_invalid_policy_configuration() -> None:
    client = type("Client", (), {"transact_write_items": lambda *_: {}})()
    with pytest.raises(TenantLedgerUnavailableError):
        load_tenant_admission(environment={}, client=client)
    with pytest.raises(TenantLedgerUnavailableError):
        load_tenant_admission(
            environment={
                "QUANTIFY_TENANT_USAGE_LEDGER_TABLE_NAME": "tenant-ledger",
                "QUANTIFY_TENANT_DAILY_REQUEST_LIMIT": "1",
                "QUANTIFY_TENANT_DAILY_COST_LIMIT_MICRO_USD": "1",
                "QUANTIFY_TENANT_REQUEST_COST_RESERVATION_MICRO_USD": "2",
            },
            client=client,
        )
