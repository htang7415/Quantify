from __future__ import annotations

import importlib.util
from pathlib import Path

from quantify.private_catalog import CatalogAction, CatalogStageAction, SignedCatalogStageAction


ROOT = Path(__file__).parents[1]
STAGING = ROOT / "deploy" / "aws" / "stage_private_release_catalog.py"
staging_spec = importlib.util.spec_from_file_location("stage_private_release_catalog", STAGING)
staging = importlib.util.module_from_spec(staging_spec)
assert staging_spec and staging_spec.loader
staging_spec.loader.exec_module(staging)
import sys
sys.modules["stage_private_release_catalog"] = staging
SCRIPT = ROOT / "deploy" / "aws" / "check_private_release_catalog.py"
spec = importlib.util.spec_from_file_location("check_private_release_catalog", SCRIPT)
check_private_release_catalog = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(check_private_release_catalog)


def test_private_catalog_check_returns_only_safe_stage_metadata(monkeypatch) -> None:
    action = CatalogStageAction(
        stage="private-pilot", action=CatalogAction.PROMOTE, reviewer_id="reviewer-1",
        occurred_at="2026-07-31T12:00:00Z", catalog_manifest_hash="a" * 64,
        release_manifest_hash="b" * 64, release_approval_manifest_hash="c" * 64,
    )
    signed = SignedCatalogStageAction(
        action=action, signer_key_id="reviewer-1", signature_algorithm="RSASSA_PSS_SHA_256", signature="c2ln",
    )
    class _Store:
        def __init__(self, **kwargs): pass
        def load_stage(self, **kwargs): return signed, object()
    monkeypatch.setattr(check_private_release_catalog, "PrivateCatalogStore", _Store)

    result = check_private_release_catalog.check(
        stage="private-pilot", bucket_name="private", signing_key_arn="key",
        s3_client=object(), kms_client=object(),
    )

    assert result == {
        "action": "promote", "catalog_manifest_hash": "a" * 64,
        "release_manifest_hash": "b" * 64, "reviewer_id": "reviewer-1",
        "stage": "private-pilot", "stage_action_manifest_hash": action.manifest_hash, "serving": True,
    }
