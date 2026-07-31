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
def test_lane_a_publishes_immutable_approved_release():
 r=release(); gate=evaluate_release(release=r,sources=(source(),),evaluation=evaluation(),thresholds=thresholds(),lane=ReleaseLane.A); c=ReleaseCatalog(); assert c.publish(release=r,gate=gate).status is ReleaseStatus.APPROVED; assert c.serving_entry(release_id=r.release_id)
def test_lane_b_requires_reviewer_and_bad_sources_or_metrics_fail_gate():
 r=release(); assert not evaluate_release(release=r,sources=(source(),),evaluation=evaluation(),thresholds=thresholds(),lane=ReleaseLane.B).approved
 bad=evaluate_release(release=r,sources=(SourceValidation("bad",False,"b"*64,99),),evaluation=ReleaseEvaluation(9800,200,50),thresholds=thresholds(),lane=ReleaseLane.B,reviewer=ReviewerApproval("reviewer", "c"*64)); assert not bad.approved and "source_stale" in bad.reasons and "automated_pass_rate" in bad.reasons
def test_revocation_and_rollback_stop_catalog_serving_without_mutating_manifest():
 r=release(); c=ReleaseCatalog(); c.publish(release=r,gate=evaluate_release(release=r,sources=(source(),),evaluation=evaluation(),thresholds=thresholds(),lane=ReleaseLane.A)); original=r.manifest_hash; c.revoke(release_id=r.release_id); assert c.serving_entry(release_id=r.release_id) is None and r.manifest_hash==original
