from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
import pytest
from quantify.release_factory import build_evidence_release
from quantify.release_operations import *

ROOT=Path(__file__).parents[1]/"fixtures"/"sec"
def release():
 d=json.loads((ROOT/"release_v1.json").read_text()); return build_evidence_release(fixtures_directory=ROOT,release_id=d["release_id"],issuer_ciks=tuple(d["issuer_ciks"]),evaluation_corpus=ROOT/d["evaluation_corpus"])
def thresholds(): return ReleaseGateThresholds(9900,100,25,30)
def source(): return SourceValidation("sec-company-facts",True,"a"*64,2)
def evaluation(): return ReleaseEvaluation(9950,50,10)
def reviewer(): return ReviewerApproval("reviewer", "c" * 64)
def test_lane_a_publishes_immutable_approved_release():
 r=release(); gate=evaluate_release(release=r,sources=(source(),),evaluation=evaluation(),thresholds=thresholds(),lane=ReleaseLane.A,reviewer=reviewer()); c=ReleaseCatalog(); assert c.publish(release=r,gate=gate).status is ReleaseStatus.APPROVED; assert c.serving_entry(release_id=r.release_id); assert len(gate.manifest_hash) == 64
def test_lane_b_requires_reviewer_and_bad_sources_or_metrics_fail_gate():
 r=release(); assert not evaluate_release(release=r,sources=(source(),),evaluation=evaluation(),thresholds=thresholds(),lane=ReleaseLane.B).approved
 bad=evaluate_release(release=r,sources=(SourceValidation("bad",False,"b"*64,99),),evaluation=ReleaseEvaluation(9800,200,50),thresholds=thresholds(),lane=ReleaseLane.B,reviewer=ReviewerApproval("reviewer", "c"*64)); assert not bad.approved and "source_stale" in bad.reasons and "automated_pass_rate" in bad.reasons
def test_revocation_and_rollback_stop_catalog_serving_without_mutating_manifest():
 r=release(); c=ReleaseCatalog(); c.publish(release=r,gate=evaluate_release(release=r,sources=(source(),),evaluation=evaluation(),thresholds=thresholds(),lane=ReleaseLane.A,reviewer=reviewer())); original=r.manifest_hash; serving=c.serving_manifest(); assert serving.entries[0].release_hash == original and len(serving.manifest_hash) == 64; c.revoke(release_id=r.release_id); assert c.serving_entry(release_id=r.release_id) is None and not c.serving_manifest().entries and r.manifest_hash==original
def test_lane_a_requires_its_approved_spot_review_and_hashes_must_be_valid():
 r=release(); gate=evaluate_release(release=r,sources=(source(),),evaluation=evaluation(),thresholds=thresholds(),lane=ReleaseLane.A); assert not gate.approved and "lane_a_spot_reviewer_required" in gate.reasons
 with pytest.raises(ReleaseOperationError): SourceValidation("bad", True, "not-a-hash", 0)
 with pytest.raises(ReleaseOperationError): ReleaseGateThresholds(10_001,100,25,30)

def test_policy_bound_gate_record_replays_its_exact_inputs():
 r=release(); policy=ReleaseGatePolicy("1.0.0","gate-policy-v1",9900,100,25,30,True,True)
 record=gate_release(release=r,sources=(source(),),evaluation=evaluation(),policy=policy,lane=ReleaseLane.A,reviewer=reviewer())
 assert record.approved and record.release_manifest_hash == r.manifest_hash
 assert record.release_gate_policy_hash == policy.content_hash
 assert len(record.manifest_hash) == 64 and record.as_dict()["manifest_hash"] == record.manifest_hash
 assert ReleaseApprovalRecord.from_dict(record.as_dict()) == record
