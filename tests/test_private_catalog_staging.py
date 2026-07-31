from __future__ import annotations

import importlib.util
from pathlib import Path

from quantify.private_catalog import CatalogAction
from quantify.release_operations import ReleaseApprovalRecord, ReleaseLane


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "stage_private_release_catalog.py"
spec = importlib.util.spec_from_file_location("stage_private_release_catalog", SCRIPT)
stage_private_release_catalog = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(stage_private_release_catalog)


def _approval() -> ReleaseApprovalRecord:
    return ReleaseApprovalRecord(
        release_manifest_hash="a" * 64, release_gate_policy_hash="b" * 64,
        release_gate_record_hash="c" * 64, source_validation_hashes=("d" * 64,),
        evaluation_hash="e" * 64, lane=ReleaseLane.A, reasons=(),
        reviewer_approval_record_hash="f" * 64, approved=True,
    )


def test_private_catalog_staging_binds_approved_release_and_never_exposes_a_url(monkeypatch) -> None:
    seen = {}
    class _Store:
        def __init__(self, **kwargs): seen["store"] = kwargs
        def stage(self, **kwargs):
            seen["stage"] = kwargs
            return "f" * 64
    monkeypatch.setattr(stage_private_release_catalog, "PrivateCatalogStore", _Store)
    monkeypatch.setattr(stage_private_release_catalog, "sign_action", lambda **kwargs: kwargs["action"])

    result = stage_private_release_catalog.stage(
        action_name=CatalogAction.PROMOTE, stage_name="private-pilot", reviewer_id="reviewer-1",
        release_id="release-v1", release_manifest_hash="a" * 64, approval=_approval(),
        expected_current_action_hash=None, bucket_name="private", signer_key_arn="key",
        signer=object(), s3_client=object(),
    )

    assert result["action"] == "promote" and result["stage_action_manifest_hash"] == "f" * 64
    assert seen["stage"]["catalog"].entries[0].release_hash == "a" * 64
    assert "url" not in result


def test_private_catalog_revoke_has_no_release_or_catalog(monkeypatch) -> None:
    seen = {}
    class _Store:
        def __init__(self, **kwargs): pass
        def stage(self, **kwargs): seen.update(kwargs); return "f" * 64
    monkeypatch.setattr(stage_private_release_catalog, "PrivateCatalogStore", _Store)
    monkeypatch.setattr(stage_private_release_catalog, "sign_action", lambda **kwargs: kwargs["action"])

    result = stage_private_release_catalog.stage(
        action_name=CatalogAction.REVOKE, stage_name="private-pilot", reviewer_id="reviewer-1",
        release_id=None, release_manifest_hash=None, approval=None, expected_current_action_hash="a" * 64,
        bucket_name="private", signer_key_arn="key", signer=object(), s3_client=object(),
    )

    assert result["catalog_manifest_hash"] is None and seen["catalog"] is None
