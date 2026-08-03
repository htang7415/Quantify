from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantify.institutional import (
    DataClass,
    InstitutionalPolicyError,
    PrivateDataPolicy,
    Role,
    WorkspaceAuthorization,
    WorkspaceMember,
    load_private_data_policy,
)


POLICY_PATH = Path(__file__).parents[1] / "policies" / "private_data_policy_v1.json"


def _authorization() -> WorkspaceAuthorization:
    return WorkspaceAuthorization(
        policy=PrivateDataPolicy("private-v1", 30, True, 90),
        members=(
            WorkspaceMember("w1", "owner", Role.OWNER),
            WorkspaceMember("w1", "reviewer", Role.REVIEWER),
            WorkspaceMember("w2", "other", Role.OWNER),
        ),
    )


def test_workspace_rbac_and_tenant_isolation() -> None:
    authorization = _authorization()

    authorization.require(workspace_id="w1", principal_id="reviewer", action="review")
    with pytest.raises(PermissionError):
        authorization.require(workspace_id="w1", principal_id="reviewer", action="manage")
    with pytest.raises(PermissionError):
        authorization.require(workspace_id="w1", principal_id="other", action="read")


def test_private_workspace_data_cannot_join_public_release() -> None:
    authorization = _authorization()

    assert authorization.can_join_public_release(data_class=DataClass.PUBLIC_RELEASE)
    for data_class in set(DataClass) - {DataClass.PUBLIC_RELEASE}:
        assert not authorization.can_join_public_release(data_class=data_class)


def test_published_prerequisite_policy_is_complete_and_replayable() -> None:
    policy = load_private_data_policy(POLICY_PATH)

    assert policy.content_hash == "b94298b4f84757a9812957fe0e1aea943dbd3369e67771664b97e180cdc96a87"
    assert policy.to_document()["private_data_intake_enabled"] is False
    assert policy.to_document()["audit_fields"]
    assert policy.to_document()["incident_response_steps"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document.__setitem__("private_data_intake_enabled", True),
        lambda document: document["retention"].pop("deletion_sla_days"),
        lambda document: document.__setitem__("audit_fields", []),
        lambda document: document["workspace"].__setitem__("ownership_required", False),
    ],
)
def test_policy_loader_rejects_incomplete_or_broadening_policy(tmp_path: Path, mutate) -> None:  # type: ignore[no-untyped-def]
    document = json.loads(POLICY_PATH.read_text())
    mutate(document)
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(document))

    with pytest.raises(InstitutionalPolicyError):
        load_private_data_policy(path)
