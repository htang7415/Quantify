from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quantify.access_control import (
    PublicAccessPolicy,
    PublicAdmissionGuard,
    RateLimitExceededError,
    WafRejectedError,
    abuse_telemetry,
)
from quantify.research_tasks import InMemoryResearchTaskQueue, TaskQueueUnavailableError


def test_burst_is_rate_limited_by_hmac_identity_without_retaining_source() -> None:
    guard = PublicAdmissionGuard(policy=PublicAccessPolicy(2, 60, 100, b"k" * 32))
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    first = guard.admit(source_identifier="203.0.113.5", request_body=b"{}", now=now)
    second = guard.admit(source_identifier="203.0.113.5", request_body=b"{}", now=now)
    assert first == second and "203.0.113.5" not in first
    with pytest.raises(RateLimitExceededError):
        guard.admit(source_identifier="203.0.113.5", request_body=b"{}", now=now)


def test_waf_shape_checks_and_queue_saturation_fail_closed() -> None:
    guard = PublicAdmissionGuard(policy=PublicAccessPolicy(1, 60, 2, b"k" * 32))
    with pytest.raises(WafRejectedError):
        guard.admit(source_identifier="id", request_body=b"too-large", now=datetime.now(timezone.utc))
    queue = InMemoryResearchTaskQueue(maximum_messages=1)
    queue.enqueue(task_id="one")
    with pytest.raises(TaskQueueUnavailableError):
        queue.enqueue(task_id="two")


def test_abuse_telemetry_cannot_contain_request_text_or_raw_identity() -> None:
    event = abuse_telemetry(identity_hash="a" * 64, outcome="admitted", queue_depth=2, cache_hit=True)
    assert event == {"identity_hash_prefix": "a" * 12, "outcome": "admitted", "queue_depth": 2, "cache_hit": True}
