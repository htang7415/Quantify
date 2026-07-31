"""Private Lambda entrypoint for the bounded research-task worker.

This module intentionally exposes no HTTP contract.  It only adapts an SQS
batch to a fully composed ``ResearchTaskWorker``.  The production composition
must provide an indexed-release verifier, durable task store, and reloading
policy control plane before this entrypoint may be configured.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol
import os

from quantify.production import ProductionConfigurationError
from quantify.research_tasks import LambdaSqsBatchProcessor, ResearchTaskQueue, ResearchTaskWorker
from quantify.policy_control import PolicyControlPointers
from quantify.harness import AutonomousResolutionLoop
from quantify.service import ApplicationService


class _Worker(Protocol):
    def run_once(self) -> dict[str, object] | None: ...


WorkerFactory = Callable[[ResearchTaskQueue], _Worker]

def load_capacity_policy(*, environment=None):
    """Load explicit bounded worker admission settings; never default silently."""
    from quantify.research_tasks import TaskCapacityPolicy
    env = os.environ if environment is None else environment
    try:
        return TaskCapacityPolicy(
            shard_count=int(env["QUANTIFY_RESEARCH_TASK_SHARD_COUNT"]),
            daily_task_limit=int(env["QUANTIFY_RESEARCH_TASK_DAILY_LIMIT"]),
            monthly_reservation_limit_micro_usd=int(env["QUANTIFY_RESEARCH_TASK_MONTHLY_RESERVATION_LIMIT_MICRO_USD"]),
            reservation_micro_usd=int(env["QUANTIFY_RESEARCH_TASK_RESERVATION_MICRO_USD"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ProductionConfigurationError("research-task capacity configuration is invalid") from error


def create_indexed_worker_factory(
    *,
    archive_store: object,
    policy_control: object,
    task_service: object,
    task_store: object,
    verifier_factory: Callable[[object, PolicyControlPointers], object],
) -> WorkerFactory:
    """Compose a worker from the current pointer's exact archived release.

    ``verifier_factory`` is the only deployment-specific seam.  It receives an
    archived exact-fact snapshot provider and the pinned hashes, so it cannot
    silently select embedded fixtures, a different release, or live data.
    """
    pointers = policy_control.current_pointers()
    provider = archive_store.load(
        evidence_release_manifest_hash=pointers.evidence_release_manifest_hash
    )

    def factory(queue: ResearchTaskQueue) -> _Worker:
        return ResearchTaskWorker(
            service=task_service,
            store=task_store,
            queue=queue,
            policy_control=policy_control,
            verifier=verifier_factory(provider, pointers),
        )

    return factory


def create_indexed_verifier(
    *,
    snapshot_provider: object,
    pointers: PolicyControlPointers,
    extractor: object,
    extraction_model: str,
    prompt_hash: str,
    temperature: float,
    image_digest: str,
    audit_manifest_sink=None,
    before_model_call=None,
) -> ApplicationService:
    """Build the sole deterministic verdict authority for archived evidence."""
    if not image_digest.startswith("sha256:"):
        raise ProductionConfigurationError("research-task image digest is required")
    return ApplicationService(
        snapshot_provider=snapshot_provider,
        extractor=extractor,
        disclosure_detector=None,
        agent_resolution_loop=AutonomousResolutionLoop(max_actions=0),
        extraction_model=extraction_model,
        prompt_hash=prompt_hash,
        temperature=temperature,
        disclosure_detector_version="disabled-v1",
        evidence_release_manifest_hash=pointers.evidence_release_manifest_hash,
        runtime_policy_bundle_hash=pointers.runtime_policy_bundle_hash,
        release_gate_policy_hash=pointers.release_gate_policy_hash,
        deployment_image_digest=image_digest,
        audit_manifest_sink=audit_manifest_sink,
        before_model_call=before_model_call,
        sec_network_call_count=lambda: 0,
    )


def create_sqs_handler(*, worker_factory: WorkerFactory) -> Callable[[Mapping[str, object], object], dict[str, object]]:
    """Create an SQS-only handler from an already validated worker factory."""

    processor = LambdaSqsBatchProcessor(worker_factory=worker_factory)  # type: ignore[arg-type]

    def handle(event: Mapping[str, object], context: object) -> dict[str, object]:
        del context
        return processor.process(event=event)

    return handle


def handler(event: Mapping[str, object], context: object) -> dict[str, object]:
    """Fail closed until an indexed-release worker composition is installed."""

    del event, context
    raise ProductionConfigurationError(
        "research-task Lambda requires an indexed-release worker composition"
    )


def activation_preflight(*, policy_control: object, archive_store: object) -> PolicyControlPointers:
    """Prove the current controls and their declared archive are available."""
    pointers = policy_control.current_pointers()
    archive_store.load(
        evidence_release_manifest_hash=pointers.evidence_release_manifest_hash
    )
    policy_control.authorize_tool(task_pointers=pointers, tool_name="verify_claims")
    return pointers
