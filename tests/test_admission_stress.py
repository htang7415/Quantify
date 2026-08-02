from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from quantify.anonymous_trial import AnonymousTrialAdmission, TrialLimitError
from quantify.tenant_admission import (
    TenantAdmission,
    TenantQuotaExceededError,
    TenantQuotaPolicy,
)


class _TransactionCanceled(Exception):
    response = {"Error": {"Code": "TransactionCanceledException"}}


class _AtomicLedger:
    """Small DynamoDB conditional-write model used only for burst tests."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.buckets: dict[str, dict[str, int]] = {}

    def transact_write_items(self, *, TransactItems: list[dict[str, object]]) -> dict[str, object]:
        with self._lock:
            proposed: list[tuple[str, int, int, int | None, int | None]] = []
            for item in TransactItems:
                update = item["Update"]
                assert isinstance(update, dict)
                key = update["Key"]
                values = update["ExpressionAttributeValues"]
                assert isinstance(key, dict) and isinstance(values, dict)
                bucket = key["bucket"]["S"]
                assert isinstance(bucket, str)
                limit = values.get(":per_ip_limit") or values.get(":request_limit") or values.get(":daily_request_limit")
                assert isinstance(limit, dict)
                count_limit = int(limit["N"])
                cost = int(values.get(":cost", {"N": "0"})["N"])
                remaining = values.get(":remaining_cost")
                cost_limit = None if remaining is None else int(remaining["N"]) + cost
                current = self.buckets.get(bucket, {"request_count": 0, "reserved_micro_usd": 0})
                if current["request_count"] >= count_limit or (
                    cost_limit is not None
                    and current["reserved_micro_usd"] > cost_limit - cost
                ):
                    raise _TransactionCanceled()
                proposed.append((bucket, 1, cost, count_limit, cost_limit))
            for bucket, increment, cost, _, _ in proposed:
                current = self.buckets.setdefault(
                    bucket, {"request_count": 0, "reserved_micro_usd": 0}
                )
                current["request_count"] += increment
                current["reserved_micro_usd"] += cost
        return {}


def test_tenant_burst_never_exceeds_the_atomic_request_or_cost_reservation() -> None:
    ledger = _AtomicLedger()
    admission = TenantAdmission(
        table_name="tenant-ledger",
        policy=TenantQuotaPolicy(
            daily_request_limit=7,
            daily_cost_limit_micro_usd=700,
            request_cost_reservation_micro_usd=100,
        ),
        client=ledger,
    )
    now = dt.datetime(2026, 8, 1, tzinfo=dt.UTC)

    def reserve() -> bool:
        try:
            admission.reserve(tenant_id="tenant-1", now=now)
        except TenantQuotaExceededError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=24) as pool:
        admitted = list(pool.map(lambda _: reserve(), range(24)))

    assert sum(admitted) == 7
    assert ledger.buckets == {
        "tenant#tenant-1#2026-08-01": {
            "request_count": 7,
            "reserved_micro_usd": 700,
        }
    }


def test_anonymous_burst_enforces_global_capacity_without_retaining_raw_ips() -> None:
    ledger = _AtomicLedger()
    admission = AnonymousTrialAdmission(
        table_name="trial-ledger",
        per_ip_daily_limit=3,
        daily_request_limit=11,
        daily_cost_limit_micro_usd=1_100,
        request_cost_reservation_micro_usd=100,
        ip_hash_key="test-hmac-key",
        origin_key="origin-key",
        expires_at=dt.datetime(2026, 8, 2, tzinfo=dt.UTC),
        client=ledger,
    )
    now = dt.datetime(2026, 8, 1, tzinfo=dt.UTC)

    def reserve(index: int) -> bool:
        source_ip = f"203.0.113.{index % 5 + 1}"
        try:
            admission.reserve(source_ip=source_ip, now=now)
        except TrialLimitError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=32) as pool:
        admitted = list(pool.map(reserve, range(32)))

    assert sum(admitted) == 11
    assert ledger.buckets["day#2026-08-01"] == {
        "request_count": 11,
        "reserved_micro_usd": 1_100,
    }
    assert all("203.0.113." not in bucket for bucket in ledger.buckets)
