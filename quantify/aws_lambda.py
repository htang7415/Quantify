"""AWS Lambda boundary for Quantify's private, fixture-only production app.

The verifier remains cloud-provider independent.  This module is deliberately
small: it reads one pinned secret version at Lambda initialization and adapts
API Gateway HTTP API (payload v2) events to the existing ASGI application.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable, Mapping
from functools import lru_cache
import os
import json
import re
import datetime as dt
from typing import Any, Protocol
from urllib.parse import unquote

from fastapi import FastAPI

from quantify.harness.audit import AuditManifest
from quantify.policy_control import (
    ArtifactKind,
    PolicyControlPlane,
    PolicyControlPointers,
    PolicySigner,
    PolicyStatus,
    ReleaseGatePolicy,
    RuntimePolicyBundle,
    SignedPolicyEnvelope,
)
from quantify.cost_guard import GeminiCostPolicy
from quantify.production import ProductionConfigurationError, create_production_app
from quantify.runtime import (
    AuditPersistenceError,
    CostLedgerUnavailableError,
    MonthlyCostLimitError,
)


_SECRET_ARN_ENV = "QUANTIFY_GEMINI_SECRET_ARN"
_SECRET_VERSION_ENV = "QUANTIFY_GEMINI_SECRET_VERSION_ID"
_IMAGE_DIGEST_ENV = "QUANTIFY_IMAGE_DIGEST"
_AUDIT_BUCKET_ENV = "QUANTIFY_AUDIT_BUCKET_NAME"
_COST_LEDGER_TABLE_ENV = "QUANTIFY_COST_LEDGER_TABLE_NAME"
_MONTHLY_COST_LIMIT_ENV = "QUANTIFY_MONTHLY_COST_LIMIT_MICRO_USD"
_AUDIT_STORAGE_SCHEMA_VERSION = "1.0.0"
_POLICY_STORAGE_SCHEMA_VERSION = "1.0.0"
_MANIFEST_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SecretsManagerClient(Protocol):
    def get_secret_value(self, **kwargs: str) -> Mapping[str, object]: ...


class S3Client(Protocol):
    def put_object(self, **kwargs: object) -> Mapping[str, object]: ...


class S3PolicyReadClient(Protocol):
    def get_object(self, **kwargs: object) -> Mapping[str, object]: ...


class DynamoDbClient(Protocol):
    def update_item(self, **kwargs: object) -> Mapping[str, object]: ...


class DynamoMonthlyCostGuard:
    def __init__(self, *, table_name: str, monthly_limit_micro_usd: int, client: DynamoDbClient) -> None:
        self._table_name = table_name
        self._limit = monthly_limit_micro_usd
        self._client = client
        self._reservation = GeminiCostPolicy().maximum_request_micro_usd

    def reserve(self) -> None:
        month = dt.datetime.now(dt.UTC).strftime("%Y-%m")
        try:
            self._client.update_item(
                TableName=self._table_name,
                Key={"month": {"S": month}},
                UpdateExpression="SET reserved_micro_usd = if_not_exists(reserved_micro_usd, :zero) + :amount",
                ConditionExpression="attribute_not_exists(reserved_micro_usd) OR reserved_micro_usd <= :remaining",
                ExpressionAttributeValues={
                    ":zero": {"N": "0"},
                    ":amount": {"N": str(self._reservation)},
                    ":remaining": {"N": str(self._limit - self._reservation)},
                },
            )
        except Exception as error:
            response = getattr(error, "response", None)
            code = response.get("Error", {}).get("Code") if isinstance(response, Mapping) else None
            if code == "ConditionalCheckFailedException":
                raise MonthlyCostLimitError("monthly model-cost limit is reached") from error
            raise CostLedgerUnavailableError("monthly cost ledger is unavailable") from error


class S3AuditManifestStore:
    """Write one canonical, encrypted audit record per semantic manifest."""

    def __init__(self, *, bucket_name: str, client: S3Client) -> None:
        self._bucket_name = bucket_name
        self._client = client

    def persist(self, manifest: Mapping[str, object]) -> None:
        record, manifest_hash = self._canonical_record(manifest=manifest)
        try:
            self._client.put_object(
                Bucket=self._bucket_name,
                Key=f"audit-manifests/v1/{manifest_hash}.json",
                Body=json.dumps(record, sort_keys=True, separators=(",", ":")).encode(),
                ContentType="application/json",
                ServerSideEncryption="aws:kms",
                BucketKeyEnabled=True,
                IfNoneMatch="*",
                Metadata={
                    "audit-storage-schema-version": _AUDIT_STORAGE_SCHEMA_VERSION,
                    "manifest-hash": manifest_hash,
                },
            )
        except Exception as error:
            # A concurrent identical write is safe: the semantic hash and
            # canonical payload are identical, so S3's conditional conflict
            # means the durable record already exists.
            response = getattr(error, "response", None)
            code = response.get("Error", {}).get("Code") if isinstance(response, Mapping) else None
            if code in {"PreconditionFailed", "412"}:
                return
            raise AuditPersistenceError("audit manifest persistence did not complete") from error

    @staticmethod
    def _canonical_record(*, manifest: Mapping[str, object]) -> tuple[dict[str, object], str]:
        expected_keys = {"manifest_hash", *AuditManifest.__dataclass_fields__}
        if set(manifest) != expected_keys:
            raise AuditPersistenceError("audit manifest has an unsupported schema")
        manifest_hash = manifest.get("manifest_hash")
        if not isinstance(manifest_hash, str) or not _MANIFEST_HASH_PATTERN.fullmatch(manifest_hash):
            raise AuditPersistenceError("audit manifest hash is invalid")
        # Cache state belongs in aggregate observability, not durable replay
        # data: it is deliberately excluded from the semantic manifest hash.
        canonical_manifest = {
            key: value
            for key, value in manifest.items()
            if key not in {"cache_hit", "manifest_hash"}
        }
        return (
            {
                "audit_storage_schema_version": _AUDIT_STORAGE_SCHEMA_VERSION,
                "manifest_hash": manifest_hash,
                "manifest": canonical_manifest,
            },
            manifest_hash,
        )


class S3SignedPolicyArtifactStore:
    """Persist only verified, canonical policy artifacts under content hashes."""

    def __init__(self, *, bucket_name: str, client: S3Client, signer: PolicySigner) -> None:
        self._bucket_name = bucket_name
        self._client = client
        self._signer = signer

    def persist(self, envelope: SignedPolicyEnvelope) -> None:
        self._signer.verify(envelope)
        record = {
            "policy_storage_schema_version": _POLICY_STORAGE_SCHEMA_VERSION,
            "kind": envelope.kind.value,
            "artifact_hash": envelope.artifact_hash,
            "signer_key_id": envelope.signer_key_id,
            "signature_algorithm": envelope.signature_algorithm,
            "signature": envelope.signature,
            "artifact": envelope.artifact.payload(),
        }
        try:
            self._client.put_object(
                Bucket=self._bucket_name,
                Key=(
                    "policy-artifacts/v1/"
                    f"{envelope.kind.value}/{envelope.artifact_hash}.json"
                ),
                Body=json.dumps(record, sort_keys=True, separators=(",", ":")).encode(),
                ContentType="application/json",
                ServerSideEncryption="aws:kms",
                BucketKeyEnabled=True,
                IfNoneMatch="*",
                Metadata={
                    "policy-storage-schema-version": _POLICY_STORAGE_SCHEMA_VERSION,
                    "artifact-hash": envelope.artifact_hash,
                    "artifact-kind": envelope.kind.value,
                },
            )
        except Exception as error:
            response = getattr(error, "response", None)
            code = response.get("Error", {}).get("Code") if isinstance(response, Mapping) else None
            if code in {"PreconditionFailed", "412"}:
                return
            raise AuditPersistenceError("policy artifact persistence did not complete") from error


class S3SignedPolicyArtifactLoader:
    """Read and verify one exact, content-addressed policy artifact from S3.

    The caller supplies the expected kind and hash, so an object cannot select
    a different policy merely by changing its JSON payload or key.  Parsing,
    signature verification, and hash verification all happen before the
    artifact is returned.
    """

    def __init__(
        self, *, bucket_name: str, client: S3PolicyReadClient, signer: PolicySigner
    ) -> None:
        if not bucket_name:
            raise ValueError("policy artifact bucket is required")
        self._bucket_name = bucket_name
        self._client = client
        self._signer = signer

    def load(
        self, *, kind: ArtifactKind, artifact_hash: str
    ) -> SignedPolicyEnvelope[RuntimePolicyBundle | ReleaseGatePolicy]:
        if not _MANIFEST_HASH_PATTERN.fullmatch(artifact_hash):
            raise ProductionConfigurationError("policy artifact hash is invalid")
        try:
            response = self._client.get_object(
                Bucket=self._bucket_name,
                Key=f"policy-artifacts/v1/{kind.value}/{artifact_hash}.json",
            )
            body = response["Body"]
            payload_bytes = body.read() if hasattr(body, "read") else body
            if not isinstance(payload_bytes, bytes):
                raise TypeError("policy artifact body is not bytes")
            record = json.loads(payload_bytes)
            if not isinstance(record, dict) or set(record) != {
                "policy_storage_schema_version",
                "kind",
                "artifact_hash",
                "signer_key_id",
                "signature_algorithm",
                "signature",
                "artifact",
            }:
                raise ValueError("policy artifact record schema is invalid")
            if record["policy_storage_schema_version"] != _POLICY_STORAGE_SCHEMA_VERSION:
                raise ValueError("policy artifact storage schema is unsupported")
            if record["kind"] != kind.value or record["artifact_hash"] != artifact_hash:
                raise ValueError("policy artifact identity does not match its object key")
            artifact = self._artifact_from_payload(kind=kind, payload=record["artifact"])
            envelope = SignedPolicyEnvelope(
                kind=kind,
                artifact=artifact,
                artifact_hash=record["artifact_hash"],
                signer_key_id=record["signer_key_id"],
                signature_algorithm=record["signature_algorithm"],
                signature=record["signature"],
            )
            self._signer.verify(envelope)
            return envelope
        except ProductionConfigurationError:
            raise
        except Exception as error:
            raise ProductionConfigurationError(
                "pinned policy artifact cannot be read or verified"
            ) from error

    @staticmethod
    def _artifact_from_payload(
        *, kind: ArtifactKind, payload: object
    ) -> RuntimePolicyBundle | ReleaseGatePolicy:
        if not isinstance(payload, dict):
            raise ValueError("policy artifact payload is invalid")
        if kind is ArtifactKind.RUNTIME_POLICY:
            expected = set(RuntimePolicyBundle.__dataclass_fields__)
            if set(payload) != expected:
                raise ValueError("runtime policy payload schema is invalid")
            normalized = dict(payload)
            for field in (
                "allowed_tools",
                "disabled_tools",
                "allowed_sources",
                "prohibited_actions",
            ):
                if not isinstance(normalized[field], list):
                    raise ValueError("runtime policy list field is invalid")
                normalized[field] = tuple(normalized[field])
            return RuntimePolicyBundle(**normalized)
        if kind is ArtifactKind.RELEASE_GATE_POLICY:
            if set(payload) != set(ReleaseGatePolicy.__dataclass_fields__):
                raise ValueError("release-gate policy payload schema is invalid")
            return ReleaseGatePolicy(**payload)
        raise ValueError("only signed policy artifacts can be loaded")


class DynamoDbPolicyControlStore:
    """Read the independently managed policy pointers and status registry.

    This adapter deliberately has no mutation methods: publishing and
    emergency control changes belong to an offline, separately authorized
    control path.  Workers use strongly consistent reads so a revoked or
    superseded policy cannot be hidden behind a stale task process cache.
    """

    def __init__(self, *, table_name: str, client: object) -> None:
        if not table_name:
            raise ValueError("policy control table name is required")
        self._table_name = table_name
        self._client = client

    def _read(self, *, pk: str, sk: str) -> Mapping[str, object]:
        try:
            response = self._client.get_item(
                TableName=self._table_name,
                Key={"pk": {"S": pk}, "sk": {"S": sk}},
                ConsistentRead=True,
            )
            item = response.get("Item")
            if not isinstance(item, Mapping):
                raise ValueError("policy control record is missing")
            return item
        except Exception as error:
            raise ProductionConfigurationError("policy control record is unavailable") from error

    @staticmethod
    def _string(item: Mapping[str, object], *, field: str) -> str:
        value = item.get(field)
        if not isinstance(value, Mapping) or not isinstance(value.get("S"), str):
            raise ProductionConfigurationError("policy control record is malformed")
        return value["S"]

    def current_pointers(self) -> PolicyControlPointers:
        item = self._read(pk="CONTROL#POINTERS", sk="CURRENT")
        try:
            return PolicyControlPointers(
                evidence_release_manifest_hash=self._string(
                    item, field="evidence_release_manifest_hash"
                ),
                runtime_policy_bundle_hash=self._string(
                    item, field="runtime_policy_bundle_hash"
                ),
                release_gate_policy_hash=self._string(
                    item, field="release_gate_policy_hash"
                ),
            )
        except (TypeError, ValueError) as error:
            raise ProductionConfigurationError("policy control pointers are malformed") from error

    def status(self, *, kind: ArtifactKind, artifact_hash: str) -> PolicyStatus:
        item = self._read(pk=f"CONTROL#STATUS#{kind.value}#{artifact_hash}", sk="STATUS")
        try:
            return PolicyStatus(self._string(item, field="status"))
        except ValueError as error:
            raise ProductionConfigurationError("policy control status is malformed") from error


class DynamoDbPolicyControlPublisher:
    """Offline transactional publisher for statuses and the three pointers."""

    def __init__(self, *, table_name: str, client: object, signer: PolicySigner) -> None:
        if not table_name:
            raise ValueError("policy control table name is required")
        self._table_name = table_name
        self._client = client
        self._signer = signer

    def publish(
        self,
        *,
        runtime: SignedPolicyEnvelope[RuntimePolicyBundle],
        release_gate: SignedPolicyEnvelope[ReleaseGatePolicy],
        pointers: PolicyControlPointers,
        expected_current: PolicyControlPointers | None = None,
    ) -> None:
        self._signer.verify(runtime)
        self._signer.verify(release_gate)
        if runtime.artifact_hash != pointers.runtime_policy_bundle_hash or release_gate.artifact_hash != pointers.release_gate_policy_hash:
            raise ProductionConfigurationError("policy artifact does not match requested pointers")
        items: list[dict[str, object]] = []
        for kind, artifact_hash in (
            (ArtifactKind.EVIDENCE_RELEASE, pointers.evidence_release_manifest_hash),
            (ArtifactKind.RUNTIME_POLICY, runtime.artifact_hash),
            (ArtifactKind.RELEASE_GATE_POLICY, release_gate.artifact_hash),
        ):
            items.append({"Put": {"TableName": self._table_name, "Item": {
                "pk": {"S": f"CONTROL#STATUS#{kind.value}#{artifact_hash}"},
                "sk": {"S": "STATUS"}, "status": {"S": PolicyStatus.ACTIVE.value},
            }}})
        values = {
            ":evidence": {"S": pointers.evidence_release_manifest_hash},
            ":runtime": {"S": pointers.runtime_policy_bundle_hash},
            ":gate": {"S": pointers.release_gate_policy_hash},
        }
        pointer_put: dict[str, object] = {"TableName": self._table_name, "Item": {
            "pk": {"S": "CONTROL#POINTERS"}, "sk": {"S": "CURRENT"},
            "evidence_release_manifest_hash": values[":evidence"],
            "runtime_policy_bundle_hash": values[":runtime"],
            "release_gate_policy_hash": values[":gate"],
        }}
        if expected_current is not None:
            values.update({
                ":old_evidence": {"S": expected_current.evidence_release_manifest_hash},
                ":old_runtime": {"S": expected_current.runtime_policy_bundle_hash},
                ":old_gate": {"S": expected_current.release_gate_policy_hash},
            })
            pointer_put["ConditionExpression"] = (
                "evidence_release_manifest_hash = :old_evidence AND "
                "runtime_policy_bundle_hash = :old_runtime AND release_gate_policy_hash = :old_gate"
            )
            pointer_put["ExpressionAttributeValues"] = values
        else:
            pointer_put["ConditionExpression"] = "attribute_not_exists(pk)"
        items.append({"Put": pointer_put})
        try:
            self._client.transact_write_items(TransactItems=items)
        except Exception as error:
            raise ProductionConfigurationError("policy control publication did not complete") from error


class DynamoDbReloadingPolicyControlPlane:
    """Fail-closed policy facade that reloads controls before every decision."""

    def __init__(
        self,
        *,
        registry: DynamoDbPolicyControlStore,
        artifacts: S3SignedPolicyArtifactLoader,
        signer: PolicySigner,
    ) -> None:
        self._registry = registry
        self._artifacts = artifacts
        self._signer = signer

    def _load(self) -> PolicyControlPlane:
        pointers = self._registry.current_pointers()
        runtime = self._artifacts.load(
            kind=ArtifactKind.RUNTIME_POLICY,
            artifact_hash=pointers.runtime_policy_bundle_hash,
        )
        gate = self._artifacts.load(
            kind=ArtifactKind.RELEASE_GATE_POLICY,
            artifact_hash=pointers.release_gate_policy_hash,
        )
        plane = PolicyControlPlane(signer=self._signer)
        plane.publish(runtime)
        plane.publish(gate)
        plane.register_evidence_release(
            manifest_hash=pointers.evidence_release_manifest_hash
        )
        for kind, artifact_hash in (
            (ArtifactKind.EVIDENCE_RELEASE, pointers.evidence_release_manifest_hash),
            (ArtifactKind.RUNTIME_POLICY, pointers.runtime_policy_bundle_hash),
            (ArtifactKind.RELEASE_GATE_POLICY, pointers.release_gate_policy_hash),
        ):
            plane.set_status(
                kind=kind,
                artifact_hash=artifact_hash,
                status=self._registry.status(kind=kind, artifact_hash=artifact_hash),
            )
        plane.set_pointers(pointers)
        return plane

    def current_pointers(self) -> PolicyControlPointers:
        return self._load().current_pointers()

    def authorize_tool(
        self, *, task_pointers: PolicyControlPointers, tool_name: str
    ) -> RuntimePolicyBundle:
        return self._load().authorize_tool(
            task_pointers=task_pointers, tool_name=tool_name
        )

    def authorize_serving(self, *, task_pointers: PolicyControlPointers) -> None:
        self._load().authorize_serving(task_pointers=task_pointers)


def load_pinned_gemini_api_key(
    *,
    environment: Mapping[str, str] | None = None,
    secret_client: SecretsManagerClient | None = None,
) -> str:
    """Return the exact AWS Secrets Manager version selected for this image."""

    environment = environment if environment is not None else os.environ
    secret_arn = environment.get(_SECRET_ARN_ENV)
    version_id = environment.get(_SECRET_VERSION_ENV)
    if not secret_arn or not version_id:
        raise ProductionConfigurationError(
            "QUANTIFY_GEMINI_SECRET_ARN and QUANTIFY_GEMINI_SECRET_VERSION_ID are required"
        )
    if secret_client is None:
        try:
            import boto3
        except ImportError as error:  # pragma: no cover - Lambda base image provides boto3.
            raise ProductionConfigurationError("AWS Lambda runtime boto3 is unavailable") from error
        secret_client = boto3.client("secretsmanager")
    try:
        response = secret_client.get_secret_value(SecretId=secret_arn, VersionId=version_id)
    except Exception as error:  # AWS SDK exception types are intentionally not exposed.
        raise ProductionConfigurationError("pinned Gemini secret cannot be retrieved") from error
    secret = response.get("SecretString")
    if not isinstance(secret, str):
        raise ProductionConfigurationError("pinned Gemini secret is empty or not a string")
    # Secret files conventionally end with a newline.  Never carry formatting
    # whitespace into an HTTP header, where a provider library could echo a
    # malformed value in an exception or log record.
    normalized_secret = secret.strip()
    if not normalized_secret:
        raise ProductionConfigurationError("pinned Gemini secret is empty or not a string")
    return normalized_secret


def create_aws_production_app(
    *,
    environment: Mapping[str, str] | None = None,
    secret_client: SecretsManagerClient | None = None,
    audit_client: S3Client | None = None,
    cost_ledger_client: DynamoDbClient | None = None,
) -> FastAPI:
    """Compose the existing production app with an AWS-pinned Gemini secret."""

    environment = environment if environment is not None else os.environ
    api_key = load_pinned_gemini_api_key(
        environment=environment, secret_client=secret_client
    )
    audit_manifest_store = load_audit_manifest_store(
        environment=environment, client=audit_client
    )
    cost_guard = load_monthly_cost_guard(environment=environment, client=cost_ledger_client)
    return create_production_app(
        api_key=api_key,
        image_digest=environment.get(_IMAGE_DIGEST_ENV),
        environment=environment,
        audit_manifest_sink=audit_manifest_store.persist,
        before_model_call=cost_guard.reserve,
    )


def load_audit_manifest_store(
    *,
    environment: Mapping[str, str] | None = None,
    client: S3Client | None = None,
) -> S3AuditManifestStore:
    """Configure the mandatory private S3 audit store without reading objects."""

    environment = environment if environment is not None else os.environ
    bucket_name = environment.get(_AUDIT_BUCKET_ENV)
    if not bucket_name:
        raise ProductionConfigurationError("QUANTIFY_AUDIT_BUCKET_NAME is required")
    if client is None:
        try:
            import boto3
        except ImportError as error:  # pragma: no cover - Lambda base image provides boto3.
            raise ProductionConfigurationError("AWS Lambda runtime boto3 is unavailable") from error
        client = boto3.client("s3")
    return S3AuditManifestStore(bucket_name=bucket_name, client=client)


def load_monthly_cost_guard(*, environment: Mapping[str, str] | None = None, client: DynamoDbClient | None = None) -> DynamoMonthlyCostGuard:
    environment = environment if environment is not None else os.environ
    table_name = environment.get(_COST_LEDGER_TABLE_ENV)
    raw_limit = environment.get(_MONTHLY_COST_LIMIT_ENV)
    if not table_name or not raw_limit:
        raise ProductionConfigurationError("QUANTIFY_COST_LEDGER_TABLE_NAME and QUANTIFY_MONTHLY_COST_LIMIT_MICRO_USD are required")
    try:
        limit = int(raw_limit)
    except ValueError as error:
        raise ProductionConfigurationError("monthly cost limit must be an integer micro-USD value") from error
    if limit < GeminiCostPolicy().maximum_request_micro_usd:
        raise ProductionConfigurationError("monthly cost limit cannot cover one maximum request")
    if client is None:
        import boto3
        client = boto3.client("dynamodb")
    return DynamoMonthlyCostGuard(table_name=table_name, monthly_limit_micro_usd=limit, client=client)


AsgiApp = Callable[
    [dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]],
    Awaitable[None],
]


def create_api_gateway_handler(app: AsgiApp) -> Callable[[dict[str, Any], object], dict[str, object]]:
    """Adapt API Gateway HTTP API payload v2 without a second web framework.

    API Gateway route configuration is a perimeter control, while FastAPI's
    production factory remains the authoritative in-process allowlist.
    """

    def handler(event: dict[str, Any], _context: object) -> dict[str, object]:
        return asyncio.run(_invoke_asgi(app, event))

    return handler


async def _invoke_asgi(app: AsgiApp, event: Mapping[str, Any]) -> dict[str, object]:
    request_context = event.get("requestContext")
    http_context = request_context.get("http") if isinstance(request_context, Mapping) else None
    if not isinstance(http_context, Mapping):
        raise ValueError("API Gateway HTTP API event lacks requestContext.http")
    method = http_context.get("method")
    if not isinstance(method, str) or not method:
        raise ValueError("API Gateway HTTP API event lacks an HTTP method")

    raw_path = event.get("rawPath") or http_context.get("path") or "/"
    if not isinstance(raw_path, str) or not raw_path.startswith("/"):
        raise ValueError("API Gateway HTTP API event has an invalid path")
    # HTTP API payload-v2 events for a named stage include the stage segment in
    # rawPath.  It is API Gateway routing metadata, not part of Quantify's
    # public route allowlist.  Preserve it as ASGI root_path and dispatch the
    # remaining application path to FastAPI.
    stage = request_context.get("stage") if isinstance(request_context, Mapping) else None
    root_path = ""
    if isinstance(stage, str) and stage:
        stage_prefix = f"/{stage}"
        if raw_path == stage_prefix:
            root_path = stage_prefix
            raw_path = "/"
        elif raw_path.startswith(f"{stage_prefix}/"):
            root_path = stage_prefix
            raw_path = raw_path[len(stage_prefix) :]
    headers = event.get("headers") or {}
    if not isinstance(headers, Mapping):
        raise ValueError("API Gateway HTTP API event has invalid headers")
    raw_body = event.get("body") or ""
    if not isinstance(raw_body, str):
        raise ValueError("API Gateway HTTP API event has an invalid body")
    try:
        body = (
            base64.b64decode(raw_body, validate=True)
            if event.get("isBase64Encoded")
            else raw_body.encode("utf-8")
        )
    except ValueError as error:
        raise ValueError("API Gateway HTTP API body is not valid base64") from error

    normalized_headers = [
        (str(name).lower().encode("latin-1"), str(value).encode("latin-1"))
        for name, value in headers.items()
    ]
    host = str(headers.get("host", "lambda"))
    source_ip = str(http_context.get("sourceIp", ""))
    raw_query_string = event.get("rawQueryString") or ""
    if not isinstance(raw_query_string, str):
        raise ValueError("API Gateway HTTP API event has an invalid query string")
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": str(headers.get("x-forwarded-proto", "https")),
        "path": unquote(raw_path),
        "raw_path": raw_path.encode("utf-8"),
        "query_string": raw_query_string.encode("utf-8"),
        "headers": normalized_headers,
        "server": (host, 443),
        "client": (source_ip, 0),
        "root_path": root_path,
    }
    received = False
    response_status: int | None = None
    response_headers: list[tuple[bytes, bytes]] = []
    response_body: list[bytes] = []

    async def receive() -> dict[str, Any]:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        nonlocal response_status, response_headers
        if message["type"] == "http.response.start":
            response_status = int(message["status"])
            response_headers = list(message.get("headers", ()))
        elif message["type"] == "http.response.body":
            response_body.append(message.get("body", b""))

    await app(scope, receive, send)
    if response_status is None:
        raise RuntimeError("ASGI application did not start an HTTP response")

    body_bytes = b"".join(response_body)
    response: dict[str, object] = {
        "statusCode": response_status,
        "headers": {},
        "isBase64Encoded": False,
    }
    header_values: dict[str, str] = {}
    cookies: list[str] = []
    for raw_name, raw_value in response_headers:
        name = raw_name.decode("latin-1")
        value = raw_value.decode("latin-1")
        if name.lower() == "set-cookie":
            cookies.append(value)
        else:
            header_values[name] = value
    response["headers"] = header_values
    if cookies:
        response["cookies"] = cookies
    try:
        response["body"] = body_bytes.decode("utf-8")
    except UnicodeDecodeError:
        response["body"] = base64.b64encode(body_bytes).decode("ascii")
        response["isBase64Encoded"] = True
    return response


@lru_cache(maxsize=1)
def _production_handler() -> Callable[[dict[str, Any], object], dict[str, object]]:
    return create_api_gateway_handler(create_aws_production_app())


def handler(event: dict[str, Any], context: object) -> dict[str, object]:
    """AWS Lambda handler configured by ``deploy/aws/template.yaml``."""

    return _production_handler()(event, context)
