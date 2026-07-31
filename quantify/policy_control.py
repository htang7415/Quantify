"""Immutable, signed policy controls for bounded research-agent work.

This module deliberately contains no provider calls, AWS clients, or mutable
global state.  An infrastructure adapter may persist the signed envelopes and
status records, but every authorization decision is made from the immutable
payload, its signature, the status registry, and the three independently
selected pointers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import base64
import hmac
import json
import re
from typing import Generic, Mapping, Protocol, TypeVar


_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_VERSION_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_REQUIRED_PROHIBITED_ACTIONS = frozenset(
    {
        "arbitrary_url_fetch",
        "live_sec_retrieval",
        "private_document_access",
        "policy_mutation",
        "verdict_composition",
        "trade_execution",
    }
)
_KNOWN_TOOLS = frozenset(
    {
        "verify_claims",
        "search_approved_evidence_release",
        "create_review_task",
        "narrative_context",
    }
)
_KNOWN_SOURCES = frozenset({"structured_fact", "narrative_disclosure"})


class PolicyControlError(RuntimeError):
    """Base class for fail-closed policy-control failures."""


class InvalidPolicyArtifactError(PolicyControlError):
    """An artifact is malformed, unsigned, or does not match its digest."""


class PolicyUnavailableError(PolicyControlError):
    """A required policy/release is absent or not active."""


class PolicySupersededError(PolicyControlError):
    """A task's pinned controls are no longer the current controls."""


class ToolNotPermittedError(PolicyControlError):
    """The currently active policy does not permit the requested tool."""


class ArtifactKind(str, Enum):
    EVIDENCE_RELEASE = "evidence_release"
    RUNTIME_POLICY = "runtime_policy"
    RELEASE_GATE_POLICY = "release_gate_policy"


class PolicyStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"
    EMERGENCY_DISABLED = "emergency_disabled"


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _content_hash(value: Mapping[str, object]) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _validate_hash(value: str, *, field: str) -> None:
    if not _HASH_PATTERN.fullmatch(value):
        raise InvalidPolicyArtifactError(f"{field} must be a lowercase SHA-256 hash")


def _validate_identifier(value: str, *, field: str) -> None:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise InvalidPolicyArtifactError(f"{field} is invalid")


def _validate_version_token(value: str, *, field: str) -> None:
    if not _VERSION_TOKEN_PATTERN.fullmatch(value):
        raise InvalidPolicyArtifactError(f"{field} is invalid")


@dataclass(frozen=True, slots=True)
class RuntimePolicyBundle:
    """The complete, pinned permission set for one planner policy."""

    schema_version: str
    policy_id: str
    planner_provider: str
    planner_model: str
    planner_model_version: str
    secret_version: str
    prompt_hash: str
    maximum_model_calls: int
    maximum_input_tokens: int
    maximum_output_tokens: int
    allowed_tools: tuple[str, ...]
    disabled_tools: tuple[str, ...]
    allowed_sources: tuple[str, ...]
    prohibited_actions: tuple[str, ...]
    admission_policy_version: str
    cache_policy_version: str

    def __post_init__(self) -> None:
        _validate_version_token(self.schema_version, field="schema_version")
        for field in (
            "policy_id",
            "planner_provider",
            "planner_model",
            "admission_policy_version",
            "cache_policy_version",
        ):
            _validate_identifier(getattr(self, field), field=field)
        _validate_version_token(self.planner_model_version, field="planner_model_version")
        _validate_version_token(self.secret_version, field="secret_version")
        _validate_hash(self.prompt_hash, field="prompt_hash")
        if (
            self.maximum_model_calls < 0
            or self.maximum_input_tokens < 0
            or self.maximum_output_tokens < 0
        ):
            raise InvalidPolicyArtifactError("model budgets cannot be negative")
        if not self.allowed_tools or len(set(self.allowed_tools)) != len(self.allowed_tools):
            raise InvalidPolicyArtifactError("allowed_tools must be a non-empty unique list")
        if not set(self.allowed_tools).issubset(_KNOWN_TOOLS):
            raise InvalidPolicyArtifactError("allowed_tools contains an unknown tool")
        if len(set(self.disabled_tools)) != len(self.disabled_tools) or not set(
            self.disabled_tools
        ).issubset(self.allowed_tools):
            raise InvalidPolicyArtifactError("disabled_tools must be an allowed unique tool")
        if not self.allowed_sources or len(set(self.allowed_sources)) != len(self.allowed_sources):
            raise InvalidPolicyArtifactError("allowed_sources must be a non-empty unique list")
        if not set(self.allowed_sources).issubset(_KNOWN_SOURCES):
            raise InvalidPolicyArtifactError("allowed_sources contains an unknown source")
        if not _REQUIRED_PROHIBITED_ACTIONS.issubset(self.prohibited_actions):
            raise InvalidPolicyArtifactError("runtime policy omits a required prohibited action")

    def payload(self) -> dict[str, object]:
        return asdict(self)

    @property
    def content_hash(self) -> str:
        return _content_hash(self.payload())


@dataclass(frozen=True, slots=True)
class ReleaseGatePolicy:
    """Immutable release-factory thresholds, independent of runtime policy."""

    schema_version: str
    policy_id: str
    minimum_automated_pass_rate_basis_points: int
    maximum_review_exception_rate_basis_points: int
    maximum_correction_rate_basis_points: int
    maximum_source_age_days: int
    lane_a_spot_review_required: bool
    lane_b_reviewer_approval_required: bool

    def __post_init__(self) -> None:
        _validate_version_token(self.schema_version, field="schema_version")
        _validate_identifier(self.policy_id, field="policy_id")
        for value in (
            self.minimum_automated_pass_rate_basis_points,
            self.maximum_review_exception_rate_basis_points,
            self.maximum_correction_rate_basis_points,
        ):
            if not 0 <= value <= 10_000:
                raise InvalidPolicyArtifactError("release-gate rates must be basis points")
        if self.maximum_source_age_days < 0:
            raise InvalidPolicyArtifactError("maximum_source_age_days cannot be negative")
        if not self.lane_b_reviewer_approval_required:
            raise InvalidPolicyArtifactError("Lane B reviewer approval is required")

    def payload(self) -> dict[str, object]:
        return asdict(self)

    @property
    def content_hash(self) -> str:
        return _content_hash(self.payload())


Artifact = RuntimePolicyBundle | ReleaseGatePolicy
ArtifactT = TypeVar("ArtifactT", bound=Artifact)


@dataclass(frozen=True, slots=True)
class SignedPolicyEnvelope(Generic[ArtifactT]):
    """Content-addressed policy payload plus a detached signature."""

    kind: ArtifactKind
    artifact: ArtifactT
    artifact_hash: str
    signer_key_id: str
    signature_algorithm: str
    signature: str


class PolicySigner(Protocol):
    def sign(self, *, kind: ArtifactKind, artifact: Artifact) -> SignedPolicyEnvelope[Artifact]: ...

    def verify(self, envelope: SignedPolicyEnvelope[Artifact]) -> None: ...


class HmacPolicySigner:
    """Deterministic signer suitable for tests and a KMS-adapter boundary.

    Production persistence must keep keys outside source control (for example,
    an HMAC key in a versioned secret or a KMS signing adapter).  The registry
    accepts the signer abstraction so cryptographic storage is not coupled to
    authorization semantics.
    """

    algorithm = "HMAC-SHA256"

    def __init__(self, *, key_id: str, key: bytes) -> None:
        _validate_identifier(key_id, field="signer_key_id")
        if len(key) < 32:
            raise ValueError("policy signing key must be at least 32 bytes")
        self._key_id = key_id
        self._key = key

    @staticmethod
    def _signature_payload(
        *, kind: ArtifactKind, artifact_hash: str, signer_key_id: str
    ) -> bytes:
        return _canonical_json(
            {
                "artifact_hash": artifact_hash,
                "kind": kind.value,
                "signer_key_id": signer_key_id,
            }
        )

    def sign(self, *, kind: ArtifactKind, artifact: Artifact) -> SignedPolicyEnvelope[Artifact]:
        _validate_artifact_kind(kind=kind, artifact=artifact)
        artifact_hash = artifact.content_hash
        signature = hmac.new(
            self._key,
            self._signature_payload(
                kind=kind, artifact_hash=artifact_hash, signer_key_id=self._key_id
            ),
            sha256,
        ).hexdigest()
        return SignedPolicyEnvelope(
            kind=kind,
            artifact=artifact,
            artifact_hash=artifact_hash,
            signer_key_id=self._key_id,
            signature_algorithm=self.algorithm,
            signature=signature,
        )

    def verify(self, envelope: SignedPolicyEnvelope[Artifact]) -> None:
        _validate_artifact_kind(kind=envelope.kind, artifact=envelope.artifact)
        _validate_hash(envelope.artifact_hash, field="artifact_hash")
        _validate_identifier(envelope.signer_key_id, field="signer_key_id")
        if envelope.signer_key_id != self._key_id or envelope.signature_algorithm != self.algorithm:
            raise InvalidPolicyArtifactError("policy signature key or algorithm is not trusted")
        if envelope.artifact.content_hash != envelope.artifact_hash:
            raise InvalidPolicyArtifactError("policy artifact hash does not match payload")
        expected = hmac.new(
            self._key,
            self._signature_payload(
                kind=envelope.kind,
                artifact_hash=envelope.artifact_hash,
                signer_key_id=envelope.signer_key_id,
            ),
            sha256,
        ).hexdigest()
        if not hmac.compare_digest(envelope.signature, expected):
            raise InvalidPolicyArtifactError("policy signature is invalid")


class KmsPolicyVerifier:
    """Verify publisher-signed policy envelopes without granting signing power.

    This is the worker-side production boundary for an asymmetric AWS KMS
    signing key.  The offline publisher owns ``kms:Sign``; a worker receives
    only ``kms:Verify`` and therefore cannot mint a looser policy bundle.
    ``sign`` intentionally fails so this object cannot accidentally become a
    publishing credential.
    """

    algorithm = "RSASSA_PSS_SHA_256"

    def __init__(self, *, key_id: str, client: "KmsVerifyClient") -> None:
        if not key_id or len(key_id) > 2048:
            raise ValueError("KMS policy verification key is invalid")
        self._key_id = key_id
        self._client = client

    def sign(
        self, *, kind: ArtifactKind, artifact: Artifact
    ) -> SignedPolicyEnvelope[Artifact]:
        del kind, artifact
        raise PolicyControlError("KMS policy verifier cannot sign policy artifacts")

    def verify(self, envelope: SignedPolicyEnvelope[Artifact]) -> None:
        _validate_artifact_kind(kind=envelope.kind, artifact=envelope.artifact)
        _validate_hash(envelope.artifact_hash, field="artifact_hash")
        _validate_identifier(envelope.signer_key_id, field="signer_key_id")
        if envelope.signature_algorithm != self.algorithm:
            raise InvalidPolicyArtifactError("policy signature algorithm is not trusted")
        if envelope.artifact.content_hash != envelope.artifact_hash:
            raise InvalidPolicyArtifactError("policy artifact hash does not match payload")
        try:
            signature = base64.b64decode(envelope.signature.encode("ascii"), validate=True)
            response = self._client.verify(
                KeyId=self._key_id,
                Message=self._signature_payload(
                    kind=envelope.kind,
                    artifact_hash=envelope.artifact_hash,
                    signer_key_id=envelope.signer_key_id,
                ),
                Signature=signature,
                SigningAlgorithm=self.algorithm,
                MessageType="RAW",
            )
        except Exception as error:
            raise InvalidPolicyArtifactError("policy signature is invalid") from error
        if response.get("SignatureValid") is not True:
            raise InvalidPolicyArtifactError("policy signature is invalid")

    @staticmethod
    def _signature_payload(
        *, kind: ArtifactKind, artifact_hash: str, signer_key_id: str
    ) -> bytes:
        return HmacPolicySigner._signature_payload(
            kind=kind, artifact_hash=artifact_hash, signer_key_id=signer_key_id
        )


class KmsVerifyClient(Protocol):
    def verify(self, **kwargs: object) -> Mapping[str, object]: ...


def _validate_artifact_kind(*, kind: ArtifactKind, artifact: Artifact) -> None:
    if kind is ArtifactKind.RUNTIME_POLICY and isinstance(artifact, RuntimePolicyBundle):
        return
    if kind is ArtifactKind.RELEASE_GATE_POLICY and isinstance(artifact, ReleaseGatePolicy):
        return
    raise InvalidPolicyArtifactError("policy artifact type does not match its kind")


@dataclass(frozen=True, slots=True)
class PolicyControlPointers:
    """The three independently chosen hashes pinned when work is accepted."""

    evidence_release_manifest_hash: str
    runtime_policy_bundle_hash: str
    release_gate_policy_hash: str

    def __post_init__(self) -> None:
        _validate_hash(self.evidence_release_manifest_hash, field="evidence_release_manifest_hash")
        _validate_hash(self.runtime_policy_bundle_hash, field="runtime_policy_bundle_hash")
        _validate_hash(self.release_gate_policy_hash, field="release_gate_policy_hash")


class PolicyControlPlane:
    """Status registry and pointer resolver for policy-bounded work.

    The object is intentionally deterministic and storage-agnostic.  Callers
    must load it from durable, encrypted control records and call
    ``authorize_tool`` immediately before each side effect and
    ``authorize_serving`` before exposing cached or model-derived output.
    """

    def __init__(self, *, signer: PolicySigner) -> None:
        self._signer = signer
        self._artifacts: dict[tuple[ArtifactKind, str], SignedPolicyEnvelope[Artifact]] = {}
        self._statuses: dict[tuple[ArtifactKind, str], PolicyStatus] = {}
        self._pointers: PolicyControlPointers | None = None

    def publish(self, envelope: SignedPolicyEnvelope[Artifact]) -> str:
        self._signer.verify(envelope)
        key = (envelope.kind, envelope.artifact_hash)
        existing = self._artifacts.get(key)
        if existing is not None and existing != envelope:
            raise InvalidPolicyArtifactError("content hash already has a different signed envelope")
        self._artifacts[key] = envelope
        self._statuses.setdefault(key, PolicyStatus.ACTIVE)
        return envelope.artifact_hash

    def register_evidence_release(self, *, manifest_hash: str) -> None:
        _validate_hash(manifest_hash, field="evidence_release_manifest_hash")
        self._statuses.setdefault((ArtifactKind.EVIDENCE_RELEASE, manifest_hash), PolicyStatus.ACTIVE)

    def set_status(
        self, *, kind: ArtifactKind, artifact_hash: str, status: PolicyStatus
    ) -> None:
        key = (kind, artifact_hash)
        if key not in self._statuses:
            raise PolicyUnavailableError("cannot change the status of an unpublished artifact")
        self._statuses[key] = status

    def set_evidence_release_pointer(self, *, manifest_hash: str) -> PolicyControlPointers:
        _validate_hash(manifest_hash, field="evidence_release_manifest_hash")
        self._require_active(kind=ArtifactKind.EVIDENCE_RELEASE, artifact_hash=manifest_hash)
        return self._replace_pointer(evidence_release_manifest_hash=manifest_hash)

    def set_runtime_policy_pointer(self, *, artifact_hash: str) -> PolicyControlPointers:
        self._require_active(kind=ArtifactKind.RUNTIME_POLICY, artifact_hash=artifact_hash)
        return self._replace_pointer(runtime_policy_bundle_hash=artifact_hash)

    def set_release_gate_policy_pointer(self, *, artifact_hash: str) -> PolicyControlPointers:
        self._require_active(kind=ArtifactKind.RELEASE_GATE_POLICY, artifact_hash=artifact_hash)
        return self._replace_pointer(release_gate_policy_hash=artifact_hash)

    def set_pointers(self, pointers: PolicyControlPointers) -> None:
        self._require_active(
            kind=ArtifactKind.EVIDENCE_RELEASE,
            artifact_hash=pointers.evidence_release_manifest_hash,
        )
        self._require_active(
            kind=ArtifactKind.RUNTIME_POLICY,
            artifact_hash=pointers.runtime_policy_bundle_hash,
        )
        self._require_active(
            kind=ArtifactKind.RELEASE_GATE_POLICY,
            artifact_hash=pointers.release_gate_policy_hash,
        )
        self._pointers = pointers

    def current_pointers(self) -> PolicyControlPointers:
        if self._pointers is None:
            raise PolicyUnavailableError("policy pointers have not been configured")
        return self._pointers

    def authorize_tool(self, *, task_pointers: PolicyControlPointers, tool_name: str) -> RuntimePolicyBundle:
        self._require_current_and_active(task_pointers=task_pointers)
        envelope = self._artifacts[(ArtifactKind.RUNTIME_POLICY, task_pointers.runtime_policy_bundle_hash)]
        runtime = envelope.artifact
        assert isinstance(runtime, RuntimePolicyBundle)
        if tool_name not in runtime.allowed_tools or tool_name in runtime.disabled_tools:
            raise ToolNotPermittedError("tool is not permitted by the current runtime policy")
        return runtime

    def authorize_serving(self, *, task_pointers: PolicyControlPointers) -> None:
        """Fail closed if a cached/model result was made under superseded controls."""

        self._require_current_and_active(task_pointers=task_pointers)

    def _replace_pointer(self, **changes: str) -> PolicyControlPointers:
        current = self.current_pointers()
        updated = PolicyControlPointers(
            evidence_release_manifest_hash=changes.get(
                "evidence_release_manifest_hash", current.evidence_release_manifest_hash
            ),
            runtime_policy_bundle_hash=changes.get(
                "runtime_policy_bundle_hash", current.runtime_policy_bundle_hash
            ),
            release_gate_policy_hash=changes.get(
                "release_gate_policy_hash", current.release_gate_policy_hash
            ),
        )
        self._pointers = updated
        return updated

    def _require_current_and_active(self, *, task_pointers: PolicyControlPointers) -> None:
        current = self.current_pointers()
        if task_pointers != current:
            raise PolicySupersededError("task policy pointers are no longer current")
        self._require_active(
            kind=ArtifactKind.EVIDENCE_RELEASE,
            artifact_hash=task_pointers.evidence_release_manifest_hash,
        )
        self._require_active(
            kind=ArtifactKind.RUNTIME_POLICY,
            artifact_hash=task_pointers.runtime_policy_bundle_hash,
        )
        self._require_active(
            kind=ArtifactKind.RELEASE_GATE_POLICY,
            artifact_hash=task_pointers.release_gate_policy_hash,
        )

    def _require_active(self, *, kind: ArtifactKind, artifact_hash: str) -> None:
        _validate_hash(artifact_hash, field=f"{kind.value}_hash")
        if self._statuses.get((kind, artifact_hash)) is not PolicyStatus.ACTIVE:
            raise PolicyUnavailableError(f"{kind.value} is not active")
