"""Fail-closed public-admission controls for the internal research-task surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
from threading import Lock
from typing import Mapping

from quantify.policy_control import PolicyControlPlane, PolicyControlPointers


class PublicAdmissionError(RuntimeError):
    pass


class WafRejectedError(PublicAdmissionError):
    pass


class RateLimitExceededError(PublicAdmissionError):
    pass


@dataclass(frozen=True, slots=True)
class PublicAccessPolicy:
    per_identity_window_requests: int
    window_seconds: int
    maximum_request_bytes: int
    identity_hmac_key: bytes

    def __post_init__(self) -> None:
        if self.per_identity_window_requests <= 0 or self.window_seconds <= 0 or self.maximum_request_bytes <= 0 or len(self.identity_hmac_key) < 32:
            raise ValueError("public access policy is invalid")


class PublicAdmissionGuard:
    """WAF-like shape checks plus HMAC-derived, short-lived rate buckets."""

    def __init__(self, *, policy: PublicAccessPolicy) -> None:
        self._policy = policy
        self._buckets: dict[tuple[str, int], int] = {}
        self._lock = Lock()

    def admit(self, *, source_identifier: str, request_body: bytes, now: datetime) -> str:
        if not source_identifier or len(request_body) > self._policy.maximum_request_bytes:
            raise WafRejectedError("request rejected by public admission policy")
        if b"\x00" in request_body:
            raise WafRejectedError("request rejected by public admission policy")
        identity = hmac.new(self._policy.identity_hmac_key, source_identifier.encode(), sha256).hexdigest()
        bucket = int(now.astimezone(timezone.utc).timestamp()) // self._policy.window_seconds
        with self._lock:
            key = (identity, bucket)
            count = self._buckets.get(key, 0)
            if count >= self._policy.per_identity_window_requests:
                raise RateLimitExceededError("public rate limit reached")
            self._buckets[key] = count + 1
        return identity


def cache_result_is_servable(*, policy_control: PolicyControlPlane, pointers: PolicyControlPointers) -> bool:
    """A cached result is usable only under the currently active controls."""

    try:
        policy_control.authorize_serving(task_pointers=pointers)
    except Exception:
        return False
    return True


def abuse_telemetry(*, identity_hash: str, outcome: str, queue_depth: int, cache_hit: bool) -> Mapping[str, object]:
    """Aggregate-only event; it deliberately has no source identifier or request text."""

    return {
        "identity_hash_prefix": identity_hash[:12],
        "outcome": outcome,
        "queue_depth": queue_depth,
        "cache_hit": cache_hit,
    }
