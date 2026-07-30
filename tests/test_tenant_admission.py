from __future__ import annotations

import pytest

from quantify.tenant_admission import TenantAdmission, TenantQuotaExceededError, TenantQuotaPolicy


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
    admission = TenantAdmission("tenant-ledger", TenantQuotaPolicy(), type("Client", (), {"transact_write_items": lambda _, **kwargs: calls.append(kwargs)})())
    admission.reserve(tenant_id="tenant-1")
    assert calls[0]["TransactItems"][0]["Update"]["TableName"] == "tenant-ledger"
