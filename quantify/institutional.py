"""Internal institutional authorization primitives; no private content is accepted."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum

class InstitutionalPolicyError(ValueError): pass
class Role(StrEnum): OWNER="owner"; REVIEWER="reviewer"; MEMBER="member"
class DataClass(StrEnum): PUBLIC_RELEASE="public_release"; PRIVATE_WORKSPACE="private_workspace"

@dataclass(frozen=True, slots=True)
class PrivateDataPolicy:
    version: str; retention_days: int; legal_hold_supported: bool; access_review_days: int
    def __post_init__(self):
        if not self.version or self.retention_days <= 0 or not self.legal_hold_supported or self.access_review_days <= 0: raise InstitutionalPolicyError("private data policy is incomplete")

@dataclass(frozen=True, slots=True)
class WorkspaceMember: workspace_id: str; principal_id: str; role: Role

class WorkspaceAuthorization:
    def __init__(self, *, policy: PrivateDataPolicy, members: tuple[WorkspaceMember,...]): self.policy=policy; self._members={(m.workspace_id,m.principal_id):m for m in members}
    def require(self, *, workspace_id: str, principal_id: str, action: str) -> None:
        member=self._members.get((workspace_id,principal_id))
        if member is None: raise PermissionError("workspace access denied")
        allowed={Role.OWNER:{"read","manage"},Role.REVIEWER:{"read","review"},Role.MEMBER:{"read"}}
        if action not in allowed[member.role]: raise PermissionError("workspace action denied")
    def can_join_public_release(self, *, data_class: DataClass) -> bool: return data_class is DataClass.PUBLIC_RELEASE
