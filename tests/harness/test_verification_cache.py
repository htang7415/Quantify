from __future__ import annotations

from quantify.harness import VerificationCache


def test_identical_replay_identity_hits_cache_without_recomputing() -> None:
    cache = VerificationCache()
    key = cache.key(report_text="Revenue increased.", snapshot_manifest_hash="snapshot", replay_manifest_hash="manifest")
    calls = 0

    def compute() -> dict:
        nonlocal calls
        calls += 1
        return {"verdict": "verified"}

    first, first_hit = cache.get_or_compute(key=key, compute=compute)
    second, second_hit = cache.get_or_compute(key=key, compute=compute)

    assert first == second == {"verdict": "verified"}
    assert (first_hit, second_hit, calls) == (False, True, 1)


def test_changed_report_or_manifest_invalidates_cache_identity() -> None:
    baseline = VerificationCache.key(report_text="A", snapshot_manifest_hash="snapshot", replay_manifest_hash="manifest-a")
    assert baseline != VerificationCache.key(report_text="B", snapshot_manifest_hash="snapshot", replay_manifest_hash="manifest-a")
    assert baseline != VerificationCache.key(report_text="A", snapshot_manifest_hash="snapshot", replay_manifest_hash="manifest-b")
