"""Deterministic report-specific verification cache."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Callable, TypeVar


T = TypeVar("T")


class VerificationCache:
    def __init__(self) -> None:
        self._entries: dict[str, T] = {}

    @staticmethod
    def key(*, report_text: str, snapshot_manifest_hash: str, replay_manifest_hash: str) -> str:
        payload = {
            "report_hash": sha256(report_text.encode()).hexdigest(),
            "snapshot_manifest_hash": snapshot_manifest_hash,
            "replay_manifest_hash": replay_manifest_hash,
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def get_or_compute(self, *, key: str, compute: Callable[[], T]) -> tuple[T, bool]:
        if key in self._entries:
            return self._entries[key], True
        value = compute()
        self._entries[key] = value
        return value, False
