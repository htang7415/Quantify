from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from quantify.policy_control import PolicyControlPointers, ReleaseGatePolicy, RuntimePolicyBundle


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "publish_research_task_policy.py"
spec = importlib.util.spec_from_file_location("publish_research_task_policy", SCRIPT)
publish_research_task_policy = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(publish_research_task_policy)


def _runtime() -> RuntimePolicyBundle:
    return RuntimePolicyBundle(
        schema_version="1.0.0", policy_id="pilot-runtime-v1", planner_provider="google",
        planner_model="gemini-3.1-flash-lite", planner_model_version="2026-07",
        secret_version="secret-version-1", prompt_hash="a" * 64, maximum_model_calls=1,
        maximum_input_tokens=4_000, maximum_output_tokens=500,
        allowed_tools=("verify_claims",), disabled_tools=(), allowed_sources=("structured_fact",),
        prohibited_actions=("arbitrary_url_fetch", "live_sec_retrieval", "private_document_access", "policy_mutation", "verdict_composition", "trade_execution"),
        admission_policy_version="admission-v1", cache_policy_version="cache-v1",
    )


def _gate() -> ReleaseGatePolicy:
    return ReleaseGatePolicy(
        schema_version="1.0.0", policy_id="pilot-gate-v1",
        minimum_automated_pass_rate_basis_points=9_900,
        maximum_review_exception_rate_basis_points=100,
        maximum_correction_rate_basis_points=25,
        maximum_source_age_days=30,
        lane_a_spot_review_required=True,
        lane_b_reviewer_approval_required=True,
    )


def test_offline_publisher_persists_signed_artifacts_before_atomic_pointer_change() -> None:
    class _Kms:
        def sign(self, **kwargs): return {"Signature": b"approved"}
        def verify(self, **kwargs): return {"SignatureValid": kwargs["Signature"] == b"approved"}
    class _S3:
        def __init__(self): self.calls = []
        def put_object(self, **kwargs): self.calls.append(kwargs); return {}
    class _Dynamo:
        def __init__(self): self.calls = []
        def transact_write_items(self, **kwargs): self.calls.append(kwargs); return {}

    s3, ddb, kms = _S3(), _Dynamo(), _Kms()
    pointers = publish_research_task_policy.publish(
        runtime=_runtime(), release_gate=_gate(), evidence_release_manifest_hash="e" * 64,
        expected_current=None, policy_bucket="artifacts", policy_table="controls",
        signing_key_arn="arn:aws:kms:us-east-2:123456789012:key/test",
        signer_key_id="offline-publisher-v1", s3_client=s3, dynamodb_client=ddb, kms_client=kms,
    )

    assert pointers.evidence_release_manifest_hash == "e" * 64
    assert len(s3.calls) == 2
    assert all(call["ServerSideEncryption"] == "aws:kms" for call in s3.calls)
    assert len(ddb.calls) == 1
    transaction = ddb.calls[0]["TransactItems"]
    assert len(transaction) == 4
    assert transaction[-1]["Put"]["ConditionExpression"] == "attribute_not_exists(pk)"


def test_offline_publisher_requires_compare_and_swap_for_replacement() -> None:
    class _Kms:
        def sign(self, **kwargs): return {"Signature": b"approved"}
        def verify(self, **kwargs): return {"SignatureValid": True}
    class _S3:
        def put_object(self, **kwargs): return {}
    class _Dynamo:
        def __init__(self): self.call = None
        def transact_write_items(self, **kwargs): self.call = kwargs; return {}

    ddb = _Dynamo()
    expected = PolicyControlPointers("e" * 64, "a" * 64, "b" * 64)
    publish_research_task_policy.publish(
        runtime=_runtime(), release_gate=_gate(), evidence_release_manifest_hash="e" * 64,
        expected_current=expected, policy_bucket="artifacts", policy_table="controls",
        signing_key_arn="arn:aws:kms:us-east-2:123456789012:key/test",
        signer_key_id="offline-publisher-v1", s3_client=_S3(), dynamodb_client=ddb, kms_client=_Kms(),
    )
    pointer_put = ddb.call["TransactItems"][-1]["Put"]
    assert "runtime_policy_bundle_hash = :old_runtime" in pointer_put["ConditionExpression"]
    assert pointer_put["ExpressionAttributeValues"][":old_runtime"]["S"] == "a" * 64


def test_private_pilot_policy_input_cannot_enable_other_tools_or_sources(tmp_path: Path) -> None:
    payload = _runtime().payload()
    payload["allowed_tools"] = ["verify_claims", "narrative_context"]
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="only verify_claims"):
        publish_research_task_policy._runtime(path)
