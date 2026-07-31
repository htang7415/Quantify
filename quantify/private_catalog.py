"""Private, signed staging controls for immutable release catalogs.

This module intentionally has no HTTP, CloudFront, or public-read path.  A
future delivery layer may consume only a pointer whose referenced action and
catalog both verify.  Promotion and revocation are separately signed offline
actions, not side effects of a release gate.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Mapping, Protocol

from quantify.release_operations import CatalogEntry, ReleaseCatalogManifest, ReleaseStatus


_HASH = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
_STAGE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_SCHEMA = "1.0.0"


class PrivateCatalogError(RuntimeError):
    """A private catalog cannot safely be staged or read."""


class CatalogAction(StrEnum):
    PROMOTE = "promote"
    REVOKE = "revoke"


class CatalogSigner(Protocol):
    def sign(self, *, payload: bytes) -> bytes: ...
    def verify(self, *, payload: bytes, signature: bytes) -> None: ...


@dataclass(frozen=True, slots=True)
class CatalogStageAction:
    stage: str
    action: CatalogAction
    reviewer_id: str
    occurred_at: str
    catalog_manifest_hash: str | None
    release_manifest_hash: str | None
    release_approval_manifest_hash: str | None

    def __post_init__(self) -> None:
        if not _STAGE.fullmatch(self.stage) or not _IDENTIFIER.fullmatch(self.reviewer_id):
            raise ValueError("catalog stage action identity is invalid")
        try:
            parsed = datetime.fromisoformat(self.occurred_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("catalog stage action time is invalid") from error
        if parsed.tzinfo is None or parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") != self.occurred_at:
            raise ValueError("catalog stage action time is invalid")
        hashes = (self.catalog_manifest_hash, self.release_manifest_hash, self.release_approval_manifest_hash)
        if self.action is CatalogAction.PROMOTE:
            if any(not isinstance(value, str) or not _HASH.fullmatch(value) for value in hashes):
                raise ValueError("catalog promotion is incomplete")
        elif any(value is not None for value in hashes):
            raise ValueError("catalog revocation cannot select a release")

    @property
    def manifest_hash(self) -> str:
        return sha256(self.serialized()).hexdigest()

    def serialized(self) -> bytes:
        return json.dumps(
            {
                "schema_version": _SCHEMA, "stage": self.stage, "action": self.action.value,
                "reviewer_id": self.reviewer_id, "occurred_at": self.occurred_at,
                "catalog_manifest_hash": self.catalog_manifest_hash,
                "release_manifest_hash": self.release_manifest_hash,
                "release_approval_manifest_hash": self.release_approval_manifest_hash,
            }, sort_keys=True, separators=(",", ":"),
        ).encode()

    def as_dict(self) -> dict[str, object]:
        return {**json.loads(self.serialized()), "manifest_hash": self.manifest_hash}

    @classmethod
    def from_dict(cls, payload: object) -> "CatalogStageAction":
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version", "stage", "action", "reviewer_id", "occurred_at",
            "catalog_manifest_hash", "release_manifest_hash", "release_approval_manifest_hash", "manifest_hash",
        } or payload["schema_version"] != _SCHEMA:
            raise PrivateCatalogError("catalog stage action is invalid")
        try:
            action = cls(
                stage=payload["stage"], action=CatalogAction(payload["action"]), reviewer_id=payload["reviewer_id"],
                occurred_at=payload["occurred_at"], catalog_manifest_hash=payload["catalog_manifest_hash"],
                release_manifest_hash=payload["release_manifest_hash"],
                release_approval_manifest_hash=payload["release_approval_manifest_hash"],
            )
        except (TypeError, ValueError) as error:
            raise PrivateCatalogError("catalog stage action is invalid") from error
        if payload["manifest_hash"] != action.manifest_hash:
            raise PrivateCatalogError("catalog stage action does not replay")
        return action


@dataclass(frozen=True, slots=True)
class SignedCatalogStageAction:
    action: CatalogStageAction
    signer_key_id: str
    signature_algorithm: str
    signature: str

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.signer_key_id) or self.signature_algorithm != "RSASSA_PSS_SHA_256":
            raise ValueError("catalog stage signature metadata is invalid")
        try:
            if not base64.b64decode(self.signature.encode("ascii"), validate=True):
                raise ValueError
        except ValueError as error:
            raise ValueError("catalog stage signature is invalid") from error

    def signing_payload(self) -> bytes:
        return b"quantify-private-catalog-stage-v1\0" + self.action.manifest_hash.encode() + b"\0" + self.signer_key_id.encode()

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA, "action": self.action.as_dict(), "signer_key_id": self.signer_key_id,
            "signature_algorithm": self.signature_algorithm, "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "SignedCatalogStageAction":
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version", "action", "signer_key_id", "signature_algorithm", "signature",
        } or payload["schema_version"] != _SCHEMA:
            raise PrivateCatalogError("signed catalog stage action is invalid")
        try:
            return cls(
                action=CatalogStageAction.from_dict(payload["action"]), signer_key_id=payload["signer_key_id"],
                signature_algorithm=payload["signature_algorithm"], signature=payload["signature"],
            )
        except (TypeError, ValueError) as error:
            raise PrivateCatalogError("signed catalog stage action is invalid") from error


def sign_action(*, action: CatalogStageAction, signer_key_id: str, signer: CatalogSigner) -> SignedCatalogStageAction:
    if action.reviewer_id != signer_key_id:
        raise PrivateCatalogError("catalog reviewer and signing identity must match")
    unsigned = SignedCatalogStageAction(
        action=action, signer_key_id=signer_key_id, signature_algorithm="RSASSA_PSS_SHA_256",
        signature=base64.b64encode(b"placeholder").decode(),
    )
    try:
        signature = signer.sign(payload=unsigned.signing_payload())
    except Exception as error:
        raise PrivateCatalogError("catalog action signing is unavailable") from error
    if not isinstance(signature, bytes) or not signature:
        raise PrivateCatalogError("catalog action signing is unavailable")
    return SignedCatalogStageAction(
        action=action, signer_key_id=signer_key_id, signature_algorithm="RSASSA_PSS_SHA_256",
        signature=base64.b64encode(signature).decode(),
    )


def verify_action(*, signed: SignedCatalogStageAction, signer: CatalogSigner) -> None:
    try:
        signer.verify(payload=signed.signing_payload(), signature=base64.b64decode(signed.signature.encode("ascii"), validate=True))
    except Exception as error:
        raise PrivateCatalogError("catalog action signature is invalid") from error


class PrivateCatalogStore:
    """S3 persistence for private immutable catalogs and a CAS stage pointer."""

    def __init__(self, *, bucket_name: str, client: object) -> None:
        if not bucket_name:
            raise ValueError("private catalog bucket is required")
        self._bucket_name, self._client = bucket_name, client

    @staticmethod
    def _catalog_key(manifest_hash: str) -> str:
        return f"release-catalogs/v1/{manifest_hash}/catalog.json"

    @staticmethod
    def _action_key(*, stage: str, action_hash: str) -> str:
        return f"release-catalogs/v1/stages/{stage}/actions/{action_hash}.json"

    @staticmethod
    def _pointer_key(*, stage: str) -> str:
        return f"release-catalogs/v1/stages/{stage}/current.json"

    def stage(
        self, *, catalog: ReleaseCatalogManifest | None, signed_action: SignedCatalogStageAction,
        signer: CatalogSigner, expected_current_action_hash: str | None,
    ) -> str:
        verify_action(signed=signed_action, signer=signer)
        action = signed_action.action
        if action.action is CatalogAction.PROMOTE:
            if catalog is None or catalog.manifest_hash != action.catalog_manifest_hash:
                raise PrivateCatalogError("catalog promotion does not match its catalog")
            if len(catalog.entries) != 1 or catalog.entries[0].release_hash != action.release_manifest_hash:
                raise PrivateCatalogError("catalog promotion does not match its release")
            self._put_immutable(key=self._catalog_key(catalog.manifest_hash), payload=catalog.serialized())
        elif catalog is not None:
            raise PrivateCatalogError("catalog revocation cannot publish a catalog")
        action_payload = json.dumps(signed_action.as_dict(), sort_keys=True, separators=(",", ":")).encode()
        self._put_immutable(key=self._action_key(stage=action.stage, action_hash=action.manifest_hash), payload=action_payload)
        pointer = json.dumps({"schema_version": _SCHEMA, "action_manifest_hash": action.manifest_hash}, sort_keys=True, separators=(",", ":")).encode()
        self._replace_pointer(stage=action.stage, payload=pointer, expected_current_action_hash=expected_current_action_hash)
        return action.manifest_hash

    def load_stage(self, *, stage: str, signer: CatalogSigner) -> tuple[SignedCatalogStageAction, ReleaseCatalogManifest | None]:
        if not _STAGE.fullmatch(stage):
            raise PrivateCatalogError("private catalog stage is invalid")
        pointer_payload, _ = self._read(key=self._pointer_key(stage=stage))
        try:
            pointer = json.loads(pointer_payload)
        except (TypeError, json.JSONDecodeError) as error:
            raise PrivateCatalogError("private catalog pointer is invalid") from error
        action_hash = pointer.get("action_manifest_hash") if isinstance(pointer, dict) else None
        if not isinstance(pointer, dict) or pointer.get("schema_version") != _SCHEMA:
            raise PrivateCatalogError("private catalog pointer is invalid")
        if not isinstance(action_hash, str) or not _HASH.fullmatch(action_hash):
            raise PrivateCatalogError("private catalog pointer is invalid")
        action_payload, _ = self._read(key=self._action_key(stage=stage, action_hash=action_hash))
        try:
            signed = SignedCatalogStageAction.from_dict(json.loads(action_payload))
        except (TypeError, json.JSONDecodeError, PrivateCatalogError) as error:
            raise PrivateCatalogError("private catalog action is invalid") from error
        if signed.action.stage != stage or signed.action.manifest_hash != action_hash:
            raise PrivateCatalogError("private catalog action does not match its pointer")
        verify_action(signed=signed, signer=signer)
        if signed.action.action is CatalogAction.REVOKE:
            return signed, None
        assert signed.action.catalog_manifest_hash is not None
        catalog_payload, _ = self._read(key=self._catalog_key(signed.action.catalog_manifest_hash))
        try:
            raw_catalog = json.loads(catalog_payload)
            entries = raw_catalog["entries"]
            catalog = ReleaseCatalogManifest(
                schema_version=raw_catalog["schema_version"],
                entries=tuple(CatalogEntry(str(row["release_id"]), str(row["release_hash"]), ReleaseStatus.APPROVED) for row in entries),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise PrivateCatalogError("private catalog manifest is invalid") from error
        if catalog.manifest_hash != signed.action.catalog_manifest_hash or len(catalog.entries) != 1 or catalog.entries[0].release_hash != signed.action.release_manifest_hash:
            raise PrivateCatalogError("private catalog manifest does not match its action")
        return signed, catalog

    def _put_immutable(self, *, key: str, payload: bytes) -> None:
        try:
            self._client.put_object(Bucket=self._bucket_name, Key=key, Body=payload, ContentType="application/json", ServerSideEncryption="aws:kms", BucketKeyEnabled=True, IfNoneMatch="*")
        except Exception as error:
            code = getattr(error, "response", {}).get("Error", {}).get("Code") if isinstance(getattr(error, "response", None), Mapping) else None
            if code not in {"PreconditionFailed", "412"}:
                raise PrivateCatalogError("private catalog object cannot be persisted") from error
            if self._read(key=key)[0] != payload:
                raise PrivateCatalogError("private catalog object conflicts with existing content")

    def _read(self, *, key: str) -> tuple[bytes, str]:
        try:
            result = self._client.get_object(Bucket=self._bucket_name, Key=key)
            body = result["Body"]
            payload = body.read() if hasattr(body, "read") else body
            etag = result.get("ETag")
        except Exception as error:
            raise PrivateCatalogError("private catalog object cannot be read") from error
        if not isinstance(payload, bytes) or not isinstance(etag, str) or not etag:
            raise PrivateCatalogError("private catalog object is invalid")
        return payload, etag

    def _replace_pointer(self, *, stage: str, payload: bytes, expected_current_action_hash: str | None) -> None:
        key = self._pointer_key(stage=stage)
        if expected_current_action_hash is None:
            condition = {"IfNoneMatch": "*"}
        else:
            if not _HASH.fullmatch(expected_current_action_hash):
                raise PrivateCatalogError("expected catalog action hash is invalid")
            try:
                current_payload, etag = self._read(key=key)
            except PrivateCatalogError as error:
                raise PrivateCatalogError("private catalog pointer cannot be read") from error
            try:
                current = json.loads(current_payload)
            except (TypeError, json.JSONDecodeError) as error:
                raise PrivateCatalogError("private catalog pointer is invalid") from error
            if current != {"schema_version": _SCHEMA, "action_manifest_hash": expected_current_action_hash}:
                raise PrivateCatalogError("private catalog pointer changed or is invalid")
            condition = {"IfMatch": etag}
        try:
            self._client.put_object(Bucket=self._bucket_name, Key=key, Body=payload, ContentType="application/json", ServerSideEncryption="aws:kms", BucketKeyEnabled=True, **condition)
        except Exception as error:
            raise PrivateCatalogError("private catalog pointer cannot be updated") from error
