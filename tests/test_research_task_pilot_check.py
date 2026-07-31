from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "deploy" / "aws" / "check_research_task_pilot.py"
spec = importlib.util.spec_from_file_location("check_research_task_pilot", SCRIPT)
check_research_task_pilot = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(check_research_task_pilot)


def _environment_file(path: Path) -> Path:
    path.write_text("AWS_REGION=us-east-2\nAWS_STACK_NAME=quantify-private-pilot\nAUDIT_BUCKET_NAME=quantify-audits\n")
    return path


def test_inactive_pilot_check_reports_only_aggregate_readiness(tmp_path: Path, monkeypatch, capsys) -> None:
    def fake_aws(*arguments: str, environment: dict[str, str]) -> str:
        command = " ".join(arguments)
        if "describe-stacks" in command:
            return "UPDATE_COMPLETE"
        if "describe-stack-resources" in command:
            return json.dumps({"StackResources": [
                {"LogicalResourceId": "TaskTable", "PhysicalResourceId": "tasks"},
                {"LogicalResourceId": "PolicyControlTable", "PhysicalResourceId": "controls"},
                {"LogicalResourceId": "TaskQueue", "PhysicalResourceId": "queue-url"},
                {"LogicalResourceId": "TaskDlq", "PhysicalResourceId": "dlq-url"},
                {"LogicalResourceId": "Worker", "PhysicalResourceId": "worker"},
                {"LogicalResourceId": "PolicyArtifactBucket", "PhysicalResourceId": "artifacts"},
            ]})
        if "describe-continuous-backups" in command:
            return json.dumps({"ContinuousBackupsDescription": {"PointInTimeRecoveryDescription": {"PointInTimeRecoveryStatus": "ENABLED"}}})
        if "get-queue-attributes" in command:
            attributes = {"KmsMasterKeyId": "alias/aws/sqs"}
            if "queue-url" in command:
                attributes["RedrivePolicy"] = "{\"maxReceiveCount\":\"3\"}"
            return json.dumps({"Attributes": attributes})
        if "get-bucket-encryption" in command:
            return json.dumps({"ServerSideEncryptionConfiguration": {"Rules": [{}]}})
        if "get-bucket-versioning" in command:
            return json.dumps({"Status": "Enabled"})
        if "get-public-access-block" in command:
            return json.dumps({"PublicAccessBlockConfiguration": {"BlockPublicAcls": True, "BlockPublicPolicy": True, "IgnorePublicAcls": True, "RestrictPublicBuckets": True}})
        if "get-function-concurrency" in command:
            return json.dumps({"ReservedConcurrentExecutions": 0})
        if "get-function-configuration" in command:
            return json.dumps({"Environment": {"Variables": {"QUANTIFY_IMAGE_DIGEST": "sha256:" + "a" * 64}}})
        if "list-event-source-mappings" in command:
            return json.dumps({"EventSourceMappings": []})
        if "describe-alarms" in command:
            return json.dumps(["OK", "OK", "OK", "OK"])
        raise AssertionError(command)

    monkeypatch.setattr(check_research_task_pilot, "_aws", fake_aws)
    check_research_task_pilot.main(["--env-file", str(_environment_file(tmp_path / "pilot.env"))])
    assert json.loads(capsys.readouterr().out) == {
        "alarm_count": 4,
        "image_digest": "sha256:" + "a" * 64,
        "mode": "inactive",
        "stack": "quantify-private-pilot",
    }


def test_inactive_pilot_check_rejects_enabled_worker(tmp_path: Path, monkeypatch) -> None:
    def fake_aws(*arguments: str, environment: dict[str, str]) -> str:
        command = " ".join(arguments)
        if "describe-stacks" in command:
            return "UPDATE_COMPLETE"
        if "describe-stack-resources" in command:
            return json.dumps({"StackResources": [
                {"LogicalResourceId": name, "PhysicalResourceId": name}
                for name in ("TaskTable", "PolicyControlTable", "TaskQueue", "TaskDlq", "Worker", "PolicyArtifactBucket")
            ]})
        if "describe-continuous-backups" in command:
            return json.dumps({"ContinuousBackupsDescription": {"PointInTimeRecoveryDescription": {"PointInTimeRecoveryStatus": "ENABLED"}}})
        if "get-queue-attributes" in command:
            return json.dumps({"Attributes": {"KmsMasterKeyId": "alias/aws/sqs", "RedrivePolicy": "present"}})
        if "get-bucket-encryption" in command:
            return json.dumps({"ServerSideEncryptionConfiguration": {"Rules": [{}]}})
        if "get-bucket-versioning" in command:
            return json.dumps({"Status": "Enabled"})
        if "get-public-access-block" in command:
            return json.dumps({"PublicAccessBlockConfiguration": {"BlockPublicAcls": True, "BlockPublicPolicy": True, "IgnorePublicAcls": True, "RestrictPublicBuckets": True}})
        if "get-function-concurrency" in command:
            return json.dumps({"ReservedConcurrentExecutions": 1})
        raise AssertionError(command)

    monkeypatch.setattr(check_research_task_pilot, "_aws", fake_aws)
    with pytest.raises(RuntimeError, match="reserved concurrency 0"):
        check_research_task_pilot.main(["--env-file", str(_environment_file(tmp_path / "pilot.env"))])


def test_active_pilot_check_requires_one_enabled_bounded_mapping(tmp_path: Path, monkeypatch, capsys) -> None:
    def fake_aws(*arguments: str, environment: dict[str, str]) -> str:
        command = " ".join(arguments)
        if "describe-stacks" in command: return "UPDATE_COMPLETE"
        if "describe-stack-resources" in command: return json.dumps({"StackResources": [
            {"LogicalResourceId": name, "PhysicalResourceId": name}
            for name in ("TaskTable", "PolicyControlTable", "TaskQueue", "TaskDlq", "Worker", "PolicyArtifactBucket")
        ]})
        if "describe-continuous-backups" in command: return json.dumps({"ContinuousBackupsDescription": {"PointInTimeRecoveryDescription": {"PointInTimeRecoveryStatus": "ENABLED"}}})
        if "get-queue-attributes" in command: return json.dumps({"Attributes": {"KmsMasterKeyId": "alias/aws/sqs", "RedrivePolicy": "present"}})
        if "get-bucket-encryption" in command: return json.dumps({"ServerSideEncryptionConfiguration": {"Rules": [{}]}})
        if "get-bucket-versioning" in command: return json.dumps({"Status": "Enabled"})
        if "get-public-access-block" in command: return json.dumps({"PublicAccessBlockConfiguration": {"BlockPublicAcls": True, "BlockPublicPolicy": True, "IgnorePublicAcls": True, "RestrictPublicBuckets": True}})
        if "get-function-concurrency" in command: return json.dumps({"ReservedConcurrentExecutions": 2})
        if "get-function-configuration" in command: return json.dumps({"Environment": {"Variables": {"QUANTIFY_IMAGE_DIGEST": "sha256:" + "a" * 64}}})
        if "list-event-source-mappings" in command: return json.dumps({"EventSourceMappings": [{"State": "Enabled", "ScalingConfig": {"MaximumConcurrency": 2}}]})
        if "describe-alarms" in command: return json.dumps(["OK", "OK", "OK", "OK"])
        raise AssertionError(command)

    monkeypatch.setattr(check_research_task_pilot, "_aws", fake_aws)
    check_research_task_pilot.main(["--env-file", str(_environment_file(tmp_path / "pilot.env")), "--mode", "active"])
    assert json.loads(capsys.readouterr().out)["mode"] == "active"


def test_pilot_check_allows_explicit_nonsecret_operational_arguments(monkeypatch, capsys) -> None:
    monkeypatch.setattr(check_research_task_pilot, "_require_stack_complete", lambda **kwargs: None)
    monkeypatch.setattr(check_research_task_pilot, "_resources", lambda **kwargs: {
        "TaskTable": "tasks", "PolicyControlTable": "controls", "TaskQueue": "queue",
        "TaskDlq": "dlq", "Worker": "worker", "PolicyArtifactBucket": "artifacts",
    })
    monkeypatch.setattr(check_research_task_pilot, "_require_pitr", lambda **kwargs: None)
    monkeypatch.setattr(check_research_task_pilot, "_require_queue", lambda **kwargs: None)
    monkeypatch.setattr(check_research_task_pilot, "_require_bucket", lambda **kwargs: None)
    monkeypatch.setattr(check_research_task_pilot, "_require_worker", lambda **kwargs: "sha256:" + "a" * 64)
    monkeypatch.setattr(check_research_task_pilot, "_require_alarms_ok", lambda **kwargs: 4)

    check_research_task_pilot.main([
        "--stack-name", "pilot", "--region", "us-east-2", "--audit-bucket", "audits", "--mode", "active",
    ])

    assert json.loads(capsys.readouterr().out) == {
        "alarm_count": 4, "image_digest": "sha256:" + "a" * 64,
        "mode": "active", "stack": "pilot",
    }
