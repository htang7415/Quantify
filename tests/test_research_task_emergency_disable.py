from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from quantify.policy_control import PolicyControlPointers, ReleaseGatePolicy, RuntimePolicyBundle


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "emergency_disable_research_task.py"
spec = importlib.util.spec_from_file_location("emergency_disable_research_task", SCRIPT)
emergency_disable_research_task = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(emergency_disable_research_task)


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
    return ReleaseGatePolicy("1.0.0", "pilot-gate-v1", 9_900, 100, 25, 30, True, True)


def test_emergency_disable_selects_only_a_signed_tool_disabled_runtime() -> None:
    runtime, gate = _runtime(), _gate()
    expected = PolicyControlPointers("e" * 64, runtime.content_hash, gate.content_hash)

    class _Kms:
        def sign(self, **kwargs): return {"Signature": b"approved"}
        def verify(self, **kwargs): return {"SignatureValid": True}

    class _S3:
        def __init__(self): self.calls = []
        def put_object(self, **kwargs): self.calls.append(kwargs); return {}

    class _Dynamo:
        def __init__(self): self.transactions = []
        def get_item(self, *, Key, **kwargs):
            pk = Key["pk"]["S"]
            if pk == "CONTROL#POINTERS":
                return {"Item": {
                    "evidence_release_manifest_hash": {"S": expected.evidence_release_manifest_hash},
                    "runtime_policy_bundle_hash": {"S": expected.runtime_policy_bundle_hash},
                    "release_gate_policy_hash": {"S": expected.release_gate_policy_hash},
                }}
            return {"Item": {"status": {"S": "active"}}}
        def transact_write_items(self, **kwargs): self.transactions.append(kwargs); return {}

    s3, ddb = _S3(), _Dynamo()
    selected = emergency_disable_research_task.emergency_disable(
        runtime=runtime, release_gate=gate, expected_current=expected,
        policy_bucket="artifacts", policy_table="controls",
        signing_key_arn="arn:aws:kms:us-east-2:123456789012:key/test",
        signer_key_id="offline-publisher-v1", s3_client=s3, dynamodb_client=ddb,
        kms_client=_Kms(),
    )

    assert selected.evidence_release_manifest_hash == expected.evidence_release_manifest_hash
    assert selected.release_gate_policy_hash == expected.release_gate_policy_hash
    assert selected.runtime_policy_bundle_hash != expected.runtime_policy_bundle_hash
    assert len(s3.calls) == 2
    pointer_put = ddb.transactions[0]["TransactItems"][-1]["Put"]
    assert pointer_put["Item"]["runtime_policy_bundle_hash"]["S"] == selected.runtime_policy_bundle_hash
    assert pointer_put["ExpressionAttributeValues"][":old_runtime"]["S"] == expected.runtime_policy_bundle_hash


def test_emergency_cli_uses_the_release_gate_policy_argument(tmp_path: Path, monkeypatch, capsys) -> None:
    runtime, gate = _runtime(), _gate()
    pointer_path = tmp_path / "pointers.json"
    pointer_path.write_text(json.dumps({
        "evidence_release_manifest_hash": "e" * 64,
        "runtime_policy_bundle_hash": runtime.content_hash,
        "release_gate_policy_hash": gate.content_hash,
    }))
    runtime_path = tmp_path / "runtime.json"
    runtime_path.write_text(json.dumps(runtime.payload()))
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate.payload()))
    monkeypatch.setattr(emergency_disable_research_task, "emergency_disable", lambda **kwargs: kwargs["expected_current"])
    class _Boto:
        @staticmethod
        def client(name):
            return object()
    import sys
    monkeypatch.setitem(sys.modules, "boto3", _Boto())
    emergency_disable_research_task.main([
        "--runtime-policy", str(runtime_path), "--release-gate-policy", str(gate_path),
        "--expected-current-pointers", str(pointer_path), "--policy-bucket", "bucket",
        "--policy-table", "table", "--signing-key-arn", "key", "--signer-key-id", "operator",
    ])
    assert json.loads(capsys.readouterr().out)["runtime_policy_bundle_hash"] == runtime.content_hash
