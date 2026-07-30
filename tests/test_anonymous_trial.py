from __future__ import annotations

import datetime as dt

import pytest

from quantify.anonymous_trial import (
    AnonymousTrialAdmission,
    TrialLedgerUnavailableError,
    TrialLimitError,
    TrialUnavailableError,
    load_anonymous_trial_admission,
)


class _Client:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def transact_write_items(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {}


class _AwsError(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


def _admission(client: _Client) -> AnonymousTrialAdmission:
    return AnonymousTrialAdmission(
        table_name="trial-ledger",
        per_ip_daily_limit=2,
        daily_request_limit=100,
        daily_cost_limit_micro_usd=250_000,
        request_cost_reservation_micro_usd=2_500,
        ip_hash_key="test-key",
        origin_key="origin-key",
        expires_at=dt.datetime(2026, 8, 15, tzinfo=dt.UTC),
        client=client,
    )


def test_reservation_is_atomic_and_does_not_store_a_raw_ip() -> None:
    client = _Client()
    _admission(client).reserve(source_ip="203.0.113.9", now=dt.datetime(2026, 7, 30, tzinfo=dt.UTC))

    writes = client.calls[0]["TransactItems"]
    assert isinstance(writes, list) and len(writes) == 2
    assert "203.0.113.9" not in repr(writes)
    assert "ip#2026-07-30#" in repr(writes)
    assert "reserved_micro_usd" in repr(writes)
    assert "request_count < :per_ip_limit" in repr(writes)


def test_reservation_fails_closed_at_a_limit_or_ledger_error() -> None:
    with pytest.raises(TrialLimitError):
        _admission(_Client(_AwsError("TransactionCanceledException"))).reserve(source_ip="203.0.113.9")
    with pytest.raises(TrialLedgerUnavailableError):
        _admission(_Client(RuntimeError("network"))).reserve(source_ip="203.0.113.9")


def test_expired_or_disabled_trial_cannot_reserve() -> None:
    with pytest.raises(TrialUnavailableError):
        _admission(_Client()).reserve(source_ip="203.0.113.9", now=dt.datetime(2026, 8, 15, tzinfo=dt.UTC))
    with pytest.raises(TrialUnavailableError):
        load_anonymous_trial_admission(environment={}, client=_Client())
