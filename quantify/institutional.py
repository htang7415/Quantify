"""Private-data policy and authorization primitives; no private content is accepted.

This module is deliberately incapable of storing or retrieving private
material.  It validates the prerequisite policy and makes workspace access
decisions only.  A separate, approved private-evidence contract would be
required before any private material could affect a verifier result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping


class InstitutionalPolicyError(ValueError):
    """A private-data policy or access decision is invalid."""


class Role(StrEnum):
    OWNER = "owner"
    REVIEWER = "reviewer"
    MEMBER = "member"


class DataClass(StrEnum):
    PUBLIC_RELEASE = "public_release"
    PRIVATE_WORKSPACE = "private_workspace"
    PRIVATE_SOURCE = "private_source"
    USER_REQUEST = "user_request"
    AUDIT_RECORD = "audit_record"
    OPERATIONAL_SECRET = "operational_secret"


_REQUIRED_AUDIT_FIELDS = (
    "audit_id",
    "occurred_at",
    "actor_id",
    "workspace_id",
    "event_type",
    "data_class",
    "policy_version",
    "decision",
)
_INCIDENT_RESPONSE_STEPS = (
    "detect_and_triage",
    "contain_access",
    "preserve_audit_record",
    "investigate_scope",
    "notify_under_applicable_policy",
    "recover_and_review",
)


@dataclass(frozen=True, slots=True)
class RolePermission:
    role: Role
    actions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.actions or any(not action or not isinstance(action, str) for action in self.actions):
            raise InstitutionalPolicyError("role permission is invalid")


_DEFAULT_ROLE_PERMISSIONS = (
    RolePermission(Role.OWNER, ("read", "manage")),
    RolePermission(Role.REVIEWER, ("read", "review")),
    RolePermission(Role.MEMBER, ("read",)),
)


@dataclass(frozen=True, slots=True)
class PrivateDataPolicy:
    """Versioned prerequisite policy; it authorizes no private-data intake."""

    version: str
    retention_days: int
    legal_hold_supported: bool
    access_review_days: int
    schema_version: str = "1.0.0"
    data_classes: tuple[DataClass, ...] = tuple(DataClass)
    deletion_sla_days: int = 30
    workspace_ownership_required: bool = True
    audit_fields: tuple[str, ...] = _REQUIRED_AUDIT_FIELDS
    incident_response_steps: tuple[str, ...] = _INCIDENT_RESPONSE_STEPS
    role_permissions: tuple[RolePermission, ...] = _DEFAULT_ROLE_PERMISSIONS

    def __post_init__(self) -> None:
        if (
            not self.schema_version
            or not self.version
            or self.retention_days <= 0
            or self.deletion_sla_days <= 0
            or self.access_review_days <= 0
            or not self.legal_hold_supported
            or not self.workspace_ownership_required
        ):
            raise InstitutionalPolicyError("private data policy is incomplete")
        if set(self.data_classes) != set(DataClass) or len(self.data_classes) != len(DataClass):
            raise InstitutionalPolicyError("private data policy data classes are incomplete")
        if set(self.audit_fields) != set(_REQUIRED_AUDIT_FIELDS):
            raise InstitutionalPolicyError("private data policy audit fields are incomplete")
        if set(self.incident_response_steps) != set(_INCIDENT_RESPONSE_STEPS):
            raise InstitutionalPolicyError("private data policy incident response is incomplete")
        permissions = {permission.role: permission.actions for permission in self.role_permissions}
        if set(permissions) != set(Role) or len(permissions) != len(self.role_permissions):
            raise InstitutionalPolicyError("private data policy role permissions are incomplete")
        if "manage" not in permissions[Role.OWNER] or "read" not in permissions[Role.REVIEWER]:
            raise InstitutionalPolicyError("private data policy role permissions are invalid")

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "version": self.version,
            "data_classes": [data_class.value for data_class in self.data_classes],
            "retention": {
                "retention_days": self.retention_days,
                "deletion_sla_days": self.deletion_sla_days,
                "legal_hold_supported": self.legal_hold_supported,
            },
            "workspace": {
                "ownership_required": self.workspace_ownership_required,
                "role_permissions": [
                    {"role": permission.role.value, "actions": list(permission.actions)}
                    for permission in self.role_permissions
                ],
            },
            "audit_fields": list(self.audit_fields),
            "incident_response_steps": list(self.incident_response_steps),
            "access_review_days": self.access_review_days,
            "private_data_intake_enabled": False,
        }

    @property
    def content_hash(self) -> str:
        return sha256(_canonical_json(self.to_document())).hexdigest()


def load_private_data_policy(path: Path) -> PrivateDataPolicy:
    """Load the published prerequisite artifact and reject broadening fields."""

    try:
        raw = json.loads(path.read_text())
        if not isinstance(raw, Mapping) or set(raw) != {
            "schema_version", "version", "data_classes", "retention", "workspace",
            "audit_fields", "incident_response_steps", "access_review_days",
            "private_data_intake_enabled",
        }:
            raise InstitutionalPolicyError("private data policy document is invalid")
        if raw["private_data_intake_enabled"] is not False:
            raise InstitutionalPolicyError("private data policy cannot enable private-data intake")
        retention = _mapping(raw["retention"])
        workspace = _mapping(raw["workspace"])
        if set(retention) != {"retention_days", "deletion_sla_days", "legal_hold_supported"}:
            raise InstitutionalPolicyError("private data retention policy is invalid")
        if set(workspace) != {"ownership_required", "role_permissions"}:
            raise InstitutionalPolicyError("private data workspace policy is invalid")
        permissions = tuple(
            RolePermission(role=Role(item["role"]), actions=tuple(item["actions"]))
            for item in _list_of_mappings(workspace["role_permissions"])
        )
        policy = PrivateDataPolicy(
            schema_version=_string(raw["schema_version"]),
            version=_string(raw["version"]),
            data_classes=tuple(DataClass(value) for value in _list_of_strings(raw["data_classes"])),
            retention_days=_positive_int(retention["retention_days"]),
            deletion_sla_days=_positive_int(retention["deletion_sla_days"]),
            legal_hold_supported=_bool(retention["legal_hold_supported"]),
            workspace_ownership_required=_bool(workspace["ownership_required"]),
            audit_fields=tuple(_list_of_strings(raw["audit_fields"])),
            incident_response_steps=tuple(_list_of_strings(raw["incident_response_steps"])),
            access_review_days=_positive_int(raw["access_review_days"]),
            role_permissions=permissions,
        )
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError) as error:
        if isinstance(error, InstitutionalPolicyError):
            raise
        raise InstitutionalPolicyError("private data policy document is invalid") from error
    if policy.to_document() != raw:
        raise InstitutionalPolicyError("private data policy document does not replay")
    return policy


@dataclass(frozen=True, slots=True)
class WorkspaceMember:
    workspace_id: str
    principal_id: str
    role: Role

    def __post_init__(self) -> None:
        if not self.workspace_id or not self.principal_id:
            raise InstitutionalPolicyError("workspace member is invalid")


class WorkspaceAuthorization:
    """Authorization only; it has no private-data persistence capability."""

    def __init__(self, *, policy: PrivateDataPolicy, members: tuple[WorkspaceMember, ...]) -> None:
        self.policy = policy
        self._members = {(member.workspace_id, member.principal_id): member for member in members}
        if len(self._members) != len(members):
            raise InstitutionalPolicyError("workspace membership is ambiguous")
        self._permissions = {permission.role: frozenset(permission.actions) for permission in policy.role_permissions}

    def require(self, *, workspace_id: str, principal_id: str, action: str) -> None:
        member = self._members.get((workspace_id, principal_id))
        if member is None or action not in self._permissions[member.role]:
            raise PermissionError("workspace access denied")

    def can_join_public_release(self, *, data_class: DataClass) -> bool:
        return data_class is DataClass.PUBLIC_RELEASE


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InstitutionalPolicyError("private data policy document is invalid")
    return value


def _list_of_mappings(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise InstitutionalPolicyError("private data policy document is invalid")
    return list(value)


def _list_of_strings(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InstitutionalPolicyError("private data policy document is invalid")
    return list(value)


def _string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise InstitutionalPolicyError("private data policy document is invalid")
    return value


def _positive_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InstitutionalPolicyError("private data policy document is invalid")
    return value


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise InstitutionalPolicyError("private data policy document is invalid")
    return value
