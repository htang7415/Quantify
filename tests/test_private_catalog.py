from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest

from quantify.private_catalog import (
    CatalogAction, CatalogStageAction, PrivateCatalogError, PrivateCatalogStore,
    sign_action,
)
from quantify.release_operations import CatalogEntry, ReleaseCatalogManifest, ReleaseStatus


class _Signer:
    def sign(self, *, payload: bytes) -> bytes:
        return sha256(b"signing-key" + payload).digest()

    def verify(self, *, payload: bytes, signature: bytes) -> None:
        if signature != self.sign(payload=payload):
            raise ValueError("invalid")


class _S3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
    def put_object(self, **kwargs):
        key, body = kwargs["Key"], kwargs["Body"]
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            error = RuntimeError("exists")
            error.response = {"Error": {"Code": "PreconditionFailed"}}  # type: ignore[attr-defined]
            raise error
        if "IfMatch" in kwargs and kwargs["IfMatch"] != self._etag(key):
            raise RuntimeError("etag changed")
        self.objects[key] = body
    def get_object(self, **kwargs):
        key = kwargs["Key"]
        return {"Body": BytesIO(self.objects[key]), "ETag": self._etag(key)}
    def _etag(self, key: str) -> str:
        return '"' + sha256(self.objects[key]).hexdigest() + '"'


def _catalog() -> ReleaseCatalogManifest:
    return ReleaseCatalogManifest(
        schema_version="1.0.0",
        entries=(CatalogEntry("release-v1", "a" * 64, ReleaseStatus.APPROVED),),
    )


def _action(*, action: CatalogAction, catalog: ReleaseCatalogManifest | None = None) -> CatalogStageAction:
    return CatalogStageAction(
        stage="private-pilot", action=action, reviewer_id="reviewer-1",
        occurred_at="2026-07-31T12:00:00Z",
        catalog_manifest_hash=None if catalog is None else catalog.manifest_hash,
        release_manifest_hash=None if catalog is None else "a" * 64,
        release_approval_manifest_hash=None if catalog is None else "b" * 64,
    )


def test_private_catalog_requires_a_separate_signed_promotion_and_cas_pointer() -> None:
    signer, client, catalog = _Signer(), _S3(), _catalog()
    action = _action(action=CatalogAction.PROMOTE, catalog=catalog)
    signed = sign_action(action=action, signer_key_id="reviewer-1", signer=signer)
    store = PrivateCatalogStore(bucket_name="private", client=client)

    action_hash = store.stage(
        catalog=catalog, signed_action=signed, signer=signer, expected_current_action_hash=None
    )

    assert action_hash == action.manifest_hash
    assert any(key.endswith("/catalog.json") for key in client.objects)
    pointer = client.objects["release-catalogs/v1/stages/private-pilot/current.json"]
    assert action_hash.encode() in pointer
    assert client.objects and all("ServerSideEncryption" not in payload.decode(errors="ignore") for payload in client.objects.values())
    loaded, loaded_catalog = store.load_stage(stage="private-pilot", signer=signer)
    assert loaded.action.manifest_hash == action_hash
    assert loaded_catalog == catalog


def test_private_catalog_revoke_replaces_only_an_expected_signed_pointer() -> None:
    signer, client, catalog = _Signer(), _S3(), _catalog()
    store = PrivateCatalogStore(bucket_name="private", client=client)
    promotion = _action(action=CatalogAction.PROMOTE, catalog=catalog)
    store.stage(catalog=catalog, signed_action=sign_action(action=promotion, signer_key_id="reviewer-1", signer=signer), signer=signer, expected_current_action_hash=None)
    revocation = _action(action=CatalogAction.REVOKE)
    revoked = store.stage(catalog=None, signed_action=sign_action(action=revocation, signer_key_id="reviewer-1", signer=signer), signer=signer, expected_current_action_hash=promotion.manifest_hash)

    assert revoked == revocation.manifest_hash
    assert b'"action":"revoke"' in client.objects[f"release-catalogs/v1/stages/private-pilot/actions/{revoked}.json"]
    loaded, loaded_catalog = store.load_stage(stage="private-pilot", signer=signer)
    assert loaded.action.action is CatalogAction.REVOKE and loaded_catalog is None


def test_private_catalog_rejects_forged_reviewer_or_pointer_replacement() -> None:
    signer, client, catalog = _Signer(), _S3(), _catalog()
    action = _action(action=CatalogAction.PROMOTE, catalog=catalog)
    with pytest.raises(PrivateCatalogError, match="reviewer and signing"):
        sign_action(action=action, signer_key_id="publisher-1", signer=signer)
    signed = sign_action(action=action, signer_key_id="reviewer-1", signer=signer)
    with pytest.raises(PrivateCatalogError, match="pointer"):
        PrivateCatalogStore(bucket_name="private", client=client).stage(
            catalog=catalog, signed_action=signed, signer=signer, expected_current_action_hash="c" * 64
        )
