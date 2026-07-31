from __future__ import annotations

import base64
from dataclasses import replace

import pytest

from quantify.policy_control import (
    ArtifactKind,
    HmacPolicySigner,
    InvalidPolicyArtifactError,
    KmsPolicyVerifier,
    PolicyControlPlane,
    PolicyControlError,
    PolicyStatus,
    PolicySupersededError,
    PolicyUnavailableError,
    ReleaseGatePolicy,
    RuntimePolicyBundle,
    ToolNotPermittedError,
)


EVIDENCE_RELEASE_HASH = "e" * 64


def _runtime(*, disabled_tools: tuple[str, ...] = ()) -> RuntimePolicyBundle:
    return RuntimePolicyBundle(
        schema_version="1.0.0",
        policy_id="research-runtime-v1",
        planner_provider="google",
        planner_model="gemini-3.1-flash-lite",
        planner_model_version="2026-07",
        secret_version="secret-version-1",
        prompt_hash="a" * 64,
        maximum_model_calls=1,
        maximum_input_tokens=4_000,
        maximum_output_tokens=500,
        allowed_tools=("verify_claims",),
        disabled_tools=disabled_tools,
        allowed_sources=("structured_fact",),
        prohibited_actions=(
            "arbitrary_url_fetch",
            "live_sec_retrieval",
            "private_document_access",
            "policy_mutation",
            "verdict_composition",
            "trade_execution",
        ),
        admission_policy_version="admission-v1",
        cache_policy_version="cache-v1",
    )


def _release_gate(*, policy_id: str = "release-gate-v1") -> ReleaseGatePolicy:
    return ReleaseGatePolicy(
        schema_version="1.0.0",
        policy_id=policy_id,
        minimum_automated_pass_rate_basis_points=9_900,
        maximum_review_exception_rate_basis_points=100,
        maximum_correction_rate_basis_points=25,
        maximum_source_age_days=45,
        lane_a_spot_review_required=True,
        lane_b_reviewer_approval_required=True,
    )


def _configured_plane() -> tuple[PolicyControlPlane, RuntimePolicyBundle, ReleaseGatePolicy]:
    signer = HmacPolicySigner(key_id="policy-test-key", key=b"k" * 32)
    plane = PolicyControlPlane(signer=signer)
    runtime = _runtime()
    release_gate = _release_gate()
    plane.publish(signer.sign(kind=ArtifactKind.RUNTIME_POLICY, artifact=runtime))
    plane.publish(signer.sign(kind=ArtifactKind.RELEASE_GATE_POLICY, artifact=release_gate))
    plane.register_evidence_release(manifest_hash=EVIDENCE_RELEASE_HASH)
    from quantify.policy_control import PolicyControlPointers

    plane.set_pointers(
        PolicyControlPointers(
            evidence_release_manifest_hash=EVIDENCE_RELEASE_HASH,
            runtime_policy_bundle_hash=runtime.content_hash,
            release_gate_policy_hash=release_gate.content_hash,
        )
    )
    return plane, runtime, release_gate


def test_signed_content_addressed_bundles_are_required_before_policy_activation() -> None:
    signer = HmacPolicySigner(key_id="policy-test-key", key=b"k" * 32)
    runtime = _runtime()
    envelope = signer.sign(kind=ArtifactKind.RUNTIME_POLICY, artifact=runtime)
    plane = PolicyControlPlane(signer=signer)

    assert plane.publish(envelope) == runtime.content_hash

    with pytest.raises(InvalidPolicyArtifactError, match="hash does not match"):
        plane.publish(replace(envelope, artifact=replace(runtime, maximum_output_tokens=501)))

    with pytest.raises(InvalidPolicyArtifactError, match="signature is invalid"):
        plane.publish(replace(envelope, signature="0" * 64))


def test_kms_policy_verifier_has_no_signing_path_and_verifies_the_exact_envelope() -> None:
    class _KmsClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def verify(self, **kwargs: object) -> dict[str, object]:
            self.calls.append(kwargs)
            return {"SignatureValid": kwargs["Signature"] == b"approved"}

    client = _KmsClient()
    verifier = KmsPolicyVerifier(
        key_id="arn:aws:kms:us-east-2:123456789012:key/test", client=client
    )
    runtime = _runtime()
    from quantify.policy_control import SignedPolicyEnvelope

    envelope = SignedPolicyEnvelope(
        kind=ArtifactKind.RUNTIME_POLICY,
        artifact=runtime,
        artifact_hash=runtime.content_hash,
        signer_key_id="offline-publisher-v1",
        signature_algorithm="RSASSA_PSS_SHA_256",
        signature=base64.b64encode(b"approved").decode(),
    )

    verifier.verify(envelope)

    assert client.calls[0]["KeyId"].endswith(":key/test")
    assert client.calls[0]["Message"]
    with pytest.raises(PolicyControlError, match="cannot sign"):
        verifier.sign(kind=ArtifactKind.RUNTIME_POLICY, artifact=runtime)
    with pytest.raises(InvalidPolicyArtifactError, match="signature is invalid"):
        verifier.verify(replace(envelope, signature=base64.b64encode(b"rejected").decode()))


def test_runtime_policy_requires_all_non_bypassable_prohibitions() -> None:
    with pytest.raises(InvalidPolicyArtifactError, match="required prohibited"):
        RuntimePolicyBundle(
            # The constructor validates the full policy payload before it can
            # be signed or placed in a status registry.
            **{
                **_runtime().payload(),
                "prohibited_actions": ("trade_execution",),
            }
        )


def test_current_task_is_authorized_only_while_all_three_pointers_remain_active() -> None:
    plane, runtime, release_gate = _configured_plane()
    pointers = plane.current_pointers()

    assert plane.authorize_tool(task_pointers=pointers, tool_name="verify_claims") is runtime
    plane.authorize_serving(task_pointers=pointers)

    plane.set_status(
        kind=ArtifactKind.RELEASE_GATE_POLICY,
        artifact_hash=release_gate.content_hash,
        status=PolicyStatus.REVOKED,
    )

    with pytest.raises(PolicyUnavailableError, match="not active"):
        plane.authorize_tool(task_pointers=pointers, tool_name="verify_claims")
    with pytest.raises(PolicyUnavailableError, match="not active"):
        plane.authorize_serving(task_pointers=pointers)


@pytest.mark.parametrize(
    "status",
    (PolicyStatus.DEPRECATED, PolicyStatus.EMERGENCY_DISABLED),
)
def test_non_active_runtime_statuses_fail_closed(status: PolicyStatus) -> None:
    plane, runtime, _ = _configured_plane()
    pointers = plane.current_pointers()

    plane.set_status(
        kind=ArtifactKind.RUNTIME_POLICY,
        artifact_hash=runtime.content_hash,
        status=status,
    )

    with pytest.raises(PolicyUnavailableError, match="not active"):
        plane.authorize_tool(task_pointers=pointers, tool_name="verify_claims")


def test_emergency_tool_disable_uses_only_a_signed_runtime_pointer_change() -> None:
    plane, runtime, _ = _configured_plane()
    old_pointers = plane.current_pointers()
    signer = HmacPolicySigner(key_id="policy-test-key", key=b"k" * 32)
    emergency_runtime = _runtime(disabled_tools=("verify_claims",))
    plane.publish(signer.sign(kind=ArtifactKind.RUNTIME_POLICY, artifact=emergency_runtime))

    updated = plane.set_runtime_policy_pointer(artifact_hash=emergency_runtime.content_hash)

    assert updated.evidence_release_manifest_hash == old_pointers.evidence_release_manifest_hash
    assert updated.release_gate_policy_hash == old_pointers.release_gate_policy_hash
    assert updated.runtime_policy_bundle_hash != runtime.content_hash
    with pytest.raises(PolicySupersededError, match="no longer current"):
        plane.authorize_tool(task_pointers=old_pointers, tool_name="verify_claims")
    with pytest.raises(ToolNotPermittedError, match="not permitted"):
        plane.authorize_tool(task_pointers=updated, tool_name="verify_claims")


def test_release_gate_pointer_can_change_independently_of_runtime_and_evidence() -> None:
    plane, runtime, release_gate = _configured_plane()
    signer = HmacPolicySigner(key_id="policy-test-key", key=b"k" * 32)
    tighter_gate = _release_gate(policy_id="release-gate-v2")
    plane.publish(signer.sign(kind=ArtifactKind.RELEASE_GATE_POLICY, artifact=tighter_gate))

    updated = plane.set_release_gate_policy_pointer(artifact_hash=tighter_gate.content_hash)

    assert updated.runtime_policy_bundle_hash == runtime.content_hash
    assert updated.evidence_release_manifest_hash == EVIDENCE_RELEASE_HASH
    assert updated.release_gate_policy_hash != release_gate.content_hash
