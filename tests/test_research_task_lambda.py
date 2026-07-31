from __future__ import annotations

import pytest

from quantify.production import ProductionConfigurationError
from quantify.research_task_lambda import activation_preflight, create_indexed_verifier, create_indexed_worker_factory, create_sqs_handler, handler, load_capacity_policy
from quantify.policy_control import PolicyControlPointers
from quantify.indexed_release_archive import IndexedReleaseArchive
from tests.test_indexed_release import _MicrosoftGrowthExtractor, _compiled_msft_release
from quantify.api import VerifyRequest
from datetime import date


def test_sqs_lambda_entrypoint_delegates_to_the_bounded_batch_processor() -> None:
    class _Worker:
        def __init__(self, queue) -> None:
            self._queue = queue

        def run_once(self) -> dict[str, object] | None:
            message = self._queue.receive()
            assert message is not None
            self._queue.acknowledge(message=message)
            return {"task_id": message.task_id}

    response = create_sqs_handler(worker_factory=lambda queue: _Worker(queue))(
        {"Records": [{"messageId": "message-1", "body": '{"task_id":"task-1"}'}]},
        object(),
    )

    assert response == {"batchItemFailures": []}


def test_default_lambda_entrypoint_fails_closed_without_indexed_release_composition() -> None:
    with pytest.raises(ProductionConfigurationError, match="indexed-release worker"):
        handler({"Records": []}, object())


def test_indexed_worker_factory_loads_only_the_current_pointer_release() -> None:
    pointers = PolicyControlPointers("e" * 64, "a" * 64, "b" * 64)
    loaded: list[str] = []
    captured: dict[str, object] = {}
    class _Policies:
        def current_pointers(self): return pointers
    class _Archives:
        def load(self, *, evidence_release_manifest_hash):
            loaded.append(evidence_release_manifest_hash); return "exact-provider"
    def verifier(provider, selected):
        captured.update(provider=provider, pointers=selected)
        return object()
    factory = create_indexed_worker_factory(
        archive_store=_Archives(), policy_control=_Policies(), task_service=object(), task_store=object(), verifier_factory=verifier
    )
    # Creation is lazy for queue-bound worker state, but archive selection is fixed.
    assert loaded == ["e" * 64]
    assert factory(object()).__class__.__name__ == "ResearchTaskWorker"
    assert captured == {"provider": "exact-provider", "pointers": pointers}


def test_indexed_verifier_records_current_hashes_and_replays_archived_release() -> None:
    release, _, request = _compiled_msft_release()
    provider = IndexedReleaseArchive.load(IndexedReleaseArchive.dump(release))
    pointers = PolicyControlPointers(release.evidence_release.manifest_hash, "a" * 64, "b" * 64)
    service = create_indexed_verifier(snapshot_provider=provider, pointers=pointers, extractor=_MicrosoftGrowthExtractor(), extraction_model="test-model", prompt_hash="c" * 64, temperature=0.0, image_digest="sha256:" + "d" * 64)
    response = service.verify(cik=request.cik, request=VerifyRequest(analysis="Microsoft revenue increased.", as_of_date=date(2024, 7, 30), forms=("10-K",)))
    audit = response["audit_manifest"]
    assert audit["evidence_release_manifest_hash"] == pointers.evidence_release_manifest_hash
    assert audit["runtime_policy_bundle_hash"] == pointers.runtime_policy_bundle_hash
    assert audit["release_gate_policy_hash"] == pointers.release_gate_policy_hash

def test_capacity_policy_requires_explicit_valid_environment() -> None:
    env={"QUANTIFY_RESEARCH_TASK_SHARD_COUNT":"2","QUANTIFY_RESEARCH_TASK_DAILY_LIMIT":"10","QUANTIFY_RESEARCH_TASK_MONTHLY_RESERVATION_LIMIT_MICRO_USD":"10000","QUANTIFY_RESEARCH_TASK_RESERVATION_MICRO_USD":"500"}
    assert load_capacity_policy(environment=env).shard_count == 2
    with pytest.raises(ProductionConfigurationError): load_capacity_policy(environment={})

def test_activation_preflight_requires_current_controls_and_exact_archive():
    pointers=PolicyControlPointers("e"*64,"a"*64,"b"*64); seen=[]
    class _Control:
        def current_pointers(self): return pointers
        def authorize_tool(self, **kwargs): seen.append(kwargs); return object()
    class _Archive:
        def load(self, **kwargs): seen.append(kwargs); return object()
    assert activation_preflight(policy_control=_Control(),archive_store=_Archive()) == pointers
    assert seen[0]["evidence_release_manifest_hash"] == "e"*64
