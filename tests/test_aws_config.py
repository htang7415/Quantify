from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
DEPLOYMENT = ROOT / "deploy" / "aws"


def _read(name: str) -> str:
    return (DEPLOYMENT / name).read_text()


def test_aws_template_pins_image_secret_version_capacity_and_iam_routes() -> None:
    template = _read("template.yaml")
    example = _read("staging.env.example")

    assert "AWS::Serverless::HttpApi" in template
    assert "EnableIamAuthorizer: true" in template
    assert "DefaultAuthorizer: AWS_IAM" in template
    assert "DefaultRouteSettings:" in template
    assert "ThrottlingRateLimit: !Ref ApiThrottleRateLimit" in template
    assert "ThrottlingBurstLimit: !Ref ApiThrottleBurstLimit" in template
    assert "Path: /healthz" in template
    assert "Path: /v1/companies/{cik}/verify" in template
    assert "UseReservedConcurrency" in template
    assert "ReservedConcurrentExecutions: !If" in template
    assert "Default: 0" in template
    assert "MaxValue: 900" in template
    assert "Timeout: 10" in template
    assert "MemorySize: 512" in template
    assert "ReleaseAlias:" in template
    assert "AutoPublishAlias: !Ref ReleaseAlias" in template
    assert "AutoPublishAliasAllProperties: true" in template
    assert "@sha256:[0-9a-f]{64}" in template
    assert "QUANTIFY_GEMINI_SECRET_VERSION_ID" in template
    assert "QUANTIFY_RUNTIME_POLICY_VERSION" in template
    assert "Type: AWS::S3::Bucket" in template
    assert "SSEAlgorithm: aws:kms" in template
    assert "PublicAccessBlockConfiguration:" in template
    assert "DeletionPolicy: Retain" in template
    assert "AuditRetentionDays:" in template
    assert "QUANTIFY_AUDIT_BUCKET_NAME" in template
    assert "s3:PutObject" in template
    assert "audit-manifests/*" in template
    assert "Type: AWS::DynamoDB::Table" in template
    assert "dynamodb:UpdateItem" in template
    assert "MonthlyCostLimitMicroUsd:" in template
    assert "secretsmanager:GetSecretValue" in template
    assert "execute-api:Invoke" in template
    assert "CallerPrincipalArn:" in template
    assert "QuantifyCallerRole:" in template
    assert "MaxSessionDuration: 3600" in template
    assert "QuantifyCallerRoleArn:" in template
    assert "DestinationArn: !Sub arn:${AWS::Partition}:logs:" in template
    assert "${ApiAccessLogGroup}:log-stream:*" in template
    assert "- logs:CreateLogGroup" in template
    assert "Type: AWS::Logs::ResourcePolicy" in template
    assert "Service: delivery.logs.amazonaws.com" in template
    assert "LogFormat: JSON" in template
    assert "ApplicationLogLevel: INFO" in template
    assert "SystemLogLevel: INFO" in template
    assert "Type: AWS::Logs::MetricFilter" in template
    assert "MetricName: PinnedModelUnavailable" in template
    assert "MetricName: VerificationRequests" in template
    assert "Type: AWS::CloudWatch::Alarm" in template
    assert "MetricName: Throttles" in template
    assert "MetricName: 5xx" in template
    assert "verification-request-volume" in template
    assert "TreatMissingData: notBreaching" in template
    assert "Type: AWS::SNS::Topic" in template
    assert "Protocol: email" in template
    assert "AlarmActions:" in template
    assert "review" not in template
    assert "resolve" not in template
    assert "batch" not in template
    assert "IMAGE_URI=" in example
    assert "GEMINI_SECRET_VERSION_ID=" in example
    assert "SMOKE_ROLE_ARN=" in example
    assert "latest" not in template.lower()


def test_public_agent_template_keeps_the_authenticated_route_and_bounds_the_trial() -> None:
    template = _read("public_agent_template.yaml")
    example = _read("production.env.example")

    assert "AWS::Cognito::UserPool" in template
    assert "AWS::Cognito::UserPoolResourceServer" in template
    assert "client_credentials" in template
    assert "GenerateSecret: true" in template
    assert "BrowserClientId:" in template
    assert "HasBrowserClient:" in template
    assert "PublicAgentApiId:" in template
    assert "AWS::Serverless::HttpApi" in template
    assert "DefaultAuthorizer: CognitoJwt" in template
    assert "AuthorizationScopes:" in template
    assert "CognitoJwt" in template
    assert "Path: /v1/agent/verify" in template
    assert "Path: /v1/trial/verify" in template
    assert "Authorizer: NONE" in template
    assert "TrialEnabled:" in template
    assert "TrialExpiresAt:" in template
    assert "TrialIpHashKey:" in template
    assert "TrialOriginKey:" in template
    assert "AWS::DynamoDB::Table" in template
    assert "dynamodb:UpdateItem" in template
    assert "dynamodb:EnclosingOperation: TransactWriteItems" in template
    assert "QUANTIFY_TRIAL_ORIGIN_KEY" in template
    assert "quantify.agent_lambda.handler" in template
    assert "QUANTIFY_CORE_URL" in template
    assert "execute-api:Invoke" in template
    assert "POST/v1/companies/*/verify" in template
    assert "Path: /v1/companies/{cik}/verify" not in template
    assert "AWS_IAM" not in template
    assert "COGNITO_MACHINE_CLIENT_SECRET_FILE" in example
    assert "quantify-production-core" in example
    assert "WEB_PREVIEW_STACK_NAME=" in example


def test_web_preview_uses_a_no_secret_pkce_client_and_proxies_only_the_safe_route() -> None:
    template = _read("web_preview_template.yaml")
    deploy = _read("deploy_web_preview.sh")
    assets = _read("deploy_web_preview_assets.sh")
    invite = _read("invite_web_preview_user.sh")
    trial_smoke = _read("smoke_anonymous_trial.sh")
    trial_monitor = _read("monitor_anonymous_trial.sh")

    assert "AWS::CloudFront::Distribution" in template
    assert "AWS::CloudFront::OriginAccessControl" in template
    assert "AWS::CloudFront::ResponseHeadersPolicy" in template
    assert "ContentSecurityPolicy:" in template
    assert "AWS::S3::BucketPolicy" in template
    assert "GenerateSecret: false" in template
    assert "- code" in template
    assert "- openid" in template
    assert "LocalRedirectUri:" in template
    assert "http://127.0.0.1:5173/" in template
    assert "/verify" in template
    assert "PathPattern: /v1/agent/verify" in template
    assert "PathPattern: /v1/trial/verify" in template
    assert "X-Quantify-Trial-Origin" in template
    assert "- POST" in template
    assert "- PUT" in template
    assert "Authorization" in template
    assert "OriginPath: /production" in template
    assert "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" in template
    assert "POST/v1/companies" not in template
    assert "QUANTIFY_AUTHORIZE_AWS_WEB_PREVIEW_DEPLOY" in deploy
    assert "QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_DEPLOY" in deploy
    assert "s3 sync web/dist" in deploy
    assert "BROWSER_CLIENT_ID" in deploy
    assert "PUBLIC_AGENT_IMAGE_URI" in deploy
    assert "QUANTIFY_AUTHORIZE_AWS_WEB_PREVIEW_ASSET_DEPLOY" in assets
    assert 'VITE_QUANTIFY_AGENT_URL="/v1/agent/verify"' in assets
    assert 'VITE_QUANTIFY_TRIAL_URL="$trial_url"' in assets
    assert "s3 sync web/dist" in assets
    assert "QUANTIFY_AUTHORIZE_AWS_WEB_PREVIEW_INVITE" in invite
    assert "admin-create-user" in invite
    assert "--desired-delivery-mediums EMAIL" in invite
    assert "QUANTIFY_AUTHORIZE_AWS_ANONYMOUS_TRIAL_SMOKE" in trial_smoke
    assert "WEB_PREVIEW_URL" in trial_smoke
    assert "QUANTIFY_AUTHORIZE_AWS_ANONYMOUS_TRIAL_MONITOR" in trial_monitor
    assert "PUBLIC_AGENT_STACK_NAME" in trial_monitor


def test_aws_lambda_dockerfile_uses_lambda_handler_and_embedded_fixtures() -> None:
    dockerfile = (ROOT / "Dockerfile.lambda").read_text()

    assert "public.ecr.aws/lambda/python:3.12" in dockerfile
    assert "fixtures/sec" in dockerfile
    assert '"quantify.aws_lambda.handler"' in dockerfile
    assert "boto3" in dockerfile
    assert "find ${LAMBDA_TASK_ROOT}" not in dockerfile
    assert "chmod -R a=rX ${LAMBDA_TASK_ROOT}" in dockerfile


def test_aws_runtime_dependencies_pin_boto3_and_its_transitive_requirements() -> None:
    production_lock = (ROOT / "requirements.production.lock").read_text()

    for dependency in (
        "boto3==1.42.37",
        "botocore==1.42.97",
        "jmespath==1.1.0",
        "python-dateutil==2.9.0.post0",
        "s3transfer==0.16.1",
        "six==1.17.0",
        "urllib3==2.7.0",
    ):
        assert dependency in production_lock


def test_aws_image_build_uses_lambda_compatible_buildx_provenance_settings() -> None:
    build = _read("build_image.sh")

    assert "docker buildx build" in build
    assert "--platform linux/amd64" in build
    assert "--provenance=false" in build


def test_aws_smoke_requires_auditable_embedded_evidence_response() -> None:
    smoke = _read("smoke_staging.py")

    assert 'evidence_scope.get("source") != "SEC EDGAR"' in smoke
    assert 'evidence_scope.get("entity_level_only") is not True' in smoke
    assert 'response.get("verification_cache_hit"), bool' in smoke
    assert 'audit.get("manifest_hash")' in smoke


def test_aws_scripts_refuse_external_actions_without_explicit_authorization() -> None:
    for script, authorization in (
        ("provision_staging.sh", "QUANTIFY_AUTHORIZE_AWS_BOOTSTRAP"),
        ("build_image.sh", "QUANTIFY_AUTHORIZE_AWS_IMAGE_BUILD"),
        ("deploy_staging.sh", "QUANTIFY_AUTHORIZE_AWS_STAGING_DEPLOY"),
        ("deploy_production_core.sh", "QUANTIFY_AUTHORIZE_AWS_PRODUCTION_CORE_DEPLOY"),
        ("deploy_public_agent.sh", "QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_DEPLOY"),
        ("deploy_web_preview.sh", "QUANTIFY_AUTHORIZE_AWS_WEB_PREVIEW_DEPLOY"),
        ("deploy_web_preview_assets.sh", "QUANTIFY_AUTHORIZE_AWS_WEB_PREVIEW_ASSET_DEPLOY"),
        ("invite_web_preview_user.sh", "QUANTIFY_AUTHORIZE_AWS_WEB_PREVIEW_INVITE"),
        ("smoke_public_agent.sh", "QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_SMOKE"),
        ("smoke_anonymous_trial.sh", "QUANTIFY_AUTHORIZE_AWS_ANONYMOUS_TRIAL_SMOKE"),
        ("monitor_anonymous_trial.sh", "QUANTIFY_AUTHORIZE_AWS_ANONYMOUS_TRIAL_MONITOR"),
        ("smoke_staging.sh", "QUANTIFY_AUTHORIZE_AWS_STAGING_SMOKE"),
        ("validate_observability.sh", "QUANTIFY_AUTHORIZE_AWS_OBSERVABILITY_CHECK"),
        ("check_production_beta.sh", "QUANTIFY_AUTHORIZE_AWS_PRODUCTION_BETA_CHECK"),
    ):
        result = subprocess.run(
            ["bash", str(DEPLOYMENT / script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2
        assert authorization in result.stderr


def test_aws_deploy_rejects_non_digest_image_and_never_uses_latest(tmp_path: Path) -> None:
    fake_aws = tmp_path / "aws"
    fake_aws.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" > \"$CALLS\"\n")
    fake_aws.chmod(0o755)
    environment = os.environ | {
        "QUANTIFY_AUTHORIZE_AWS_STAGING_DEPLOY": "1",
        "AWS_REGION": "us-east-2",
        "AWS_STACK_NAME": "quantify-private-staging",
        "IMAGE_URI": "example/image:latest",
        "IMAGE_DIGEST": "sha256:" + "0" * 64,
        "GEMINI_SECRET_ARN": "arn:aws:secretsmanager:us-east-2:123456789012:secret:gemini",
        "GEMINI_SECRET_VERSION_ID": "a" * 32,
        "SMOKE_PRINCIPAL_ARN": "arn:aws:iam::123456789012:role/smoke",
        "CALLER_PRINCIPAL_ARN": "arn:aws:iam::123456789012:role/caller",
        "RESERVED_CONCURRENCY": "2",
        "ALARM_EMAIL": "operator@example.com",
        "AWS_BIN": str(fake_aws),
        "CALLS": str(tmp_path / "calls"),
    }

    result = subprocess.run(
        ["bash", str(DEPLOYMENT / "deploy_staging.sh")],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "immutable @sha256" in result.stderr


def test_aws_deploy_passes_the_exact_digest_and_pinned_secret_version(tmp_path: Path) -> None:
    calls = tmp_path / "aws-calls.txt"
    fake_aws = tmp_path / "aws"
    fake_aws.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" > \"$CALLS\"\n")
    fake_aws.chmod(0o755)
    digest = "sha256:" + "1" * 64
    environment = os.environ | {
        "QUANTIFY_AUTHORIZE_AWS_STAGING_DEPLOY": "1",
        "AWS_REGION": "us-east-2",
        "AWS_STACK_NAME": "quantify-private-staging",
        "IMAGE_URI": f"123.dkr.ecr.us-east-2.amazonaws.com/quantify@{digest}",
        "IMAGE_DIGEST": digest,
        "GEMINI_SECRET_ARN": "arn:aws:secretsmanager:us-east-2:123456789012:secret:gemini",
        "GEMINI_SECRET_VERSION_ID": "b" * 32,
        "SMOKE_PRINCIPAL_ARN": "arn:aws:iam::123456789012:role/smoke",
        "CALLER_PRINCIPAL_ARN": "arn:aws:iam::123456789012:role/caller",
        "RESERVED_CONCURRENCY": "2",
        "ALARM_EMAIL": "operator@example.com",
        "AWS_BIN": str(fake_aws),
        "CALLS": str(calls),
    }

    result = subprocess.run(
        ["bash", str(DEPLOYMENT / "deploy_staging.sh")],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    invocation = calls.read_text()
    assert f"ImageUri=123.dkr.ecr.us-east-2.amazonaws.com/quantify@{digest}" in invocation
    assert f"ImageDigest={digest}" in invocation
    assert "GeminiSecretVersionId=" + "b" * 32 in invocation
    assert "cloudformation deploy" in invocation
    assert "CAPABILITY_AUTO_EXPAND" in invocation
    assert "ReservedConcurrency=2" in invocation
    assert "AlarmEmail=operator@example.com" in invocation
    assert "AuditRetentionDays=90" in invocation
    assert "CallerPrincipalArn=arn:aws:iam::123456789012:role/caller" in invocation
    assert "ApiThrottleRateLimit=2" in invocation
    assert "ApiThrottleBurstLimit=2" in invocation
    assert "latest" not in invocation


def test_public_agent_deploy_adds_only_a_validated_browser_client_audience(tmp_path: Path) -> None:
    calls = tmp_path / "aws-calls.txt"
    fake_aws = tmp_path / "aws"
    fake_aws.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" > \"$CALLS\"\n")
    fake_aws.chmod(0o755)
    browser_client_id = "1browser_client-id"
    environment = os.environ | {
        "QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_DEPLOY": "1",
        "AWS_REGION": "us-east-2",
        "PUBLIC_AGENT_STACK_NAME": "quantify-public-agent",
        "IMAGE_URI": "123.dkr.ecr.us-east-2.amazonaws.com/quantify@sha256:" + "1" * 64,
        "CORE_API_ID": "abc123",
        "COGNITO_DOMAIN_PREFIX": "quantify-preview",
        "OAUTH_RESOURCE_SERVER_IDENTIFIER": "https://api.example.com/quantify",
        "ALARM_EMAIL": "operator@example.com",
        "BROWSER_CLIENT_ID": browser_client_id,
        "AWS_BIN": str(fake_aws),
        "CALLS": str(calls),
    }

    result = subprocess.run(
        ["bash", str(DEPLOYMENT / "deploy_public_agent.sh")],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    invocation = calls.read_text()
    assert f"BrowserClientId={browser_client_id}" in invocation
    assert "CAPABILITY_AUTO_EXPAND" in invocation


def test_public_agent_deploy_requires_secrets_and_passes_bounded_trial_settings(tmp_path: Path) -> None:
    calls = tmp_path / "aws-calls.txt"
    fake_aws = tmp_path / "aws"
    fake_aws.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" > \"$CALLS\"\n")
    fake_aws.chmod(0o755)
    environment = os.environ | {
        "QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_DEPLOY": "1",
        "AWS_REGION": "us-east-2",
        "PUBLIC_AGENT_STACK_NAME": "quantify-public-agent",
        "IMAGE_URI": "123.dkr.ecr.us-east-2.amazonaws.com/quantify@sha256:" + "1" * 64,
        "CORE_API_ID": "abc123",
        "COGNITO_DOMAIN_PREFIX": "quantify-preview",
        "OAUTH_RESOURCE_SERVER_IDENTIFIER": "https://api.example.com/quantify",
        "ALARM_EMAIL": "operator@example.com",
        "TRIAL_ENABLED": "true",
        "TRIAL_EXPIRES_AT": "2026-08-14T23:59:59Z",
        "TRIAL_IP_HASH_KEY": "a" * 32,
        "TRIAL_ORIGIN_KEY": "b" * 32,
        "TRIAL_PER_IP_DAILY_LIMIT": "2",
        "TRIAL_DAILY_REQUEST_LIMIT": "100",
        "TRIAL_DAILY_COST_LIMIT_MICRO_USD": "250000",
        "TRIAL_REQUEST_COST_RESERVATION_MICRO_USD": "2500",
        "AWS_BIN": str(fake_aws),
        "CALLS": str(calls),
    }

    result = subprocess.run(
        ["bash", str(DEPLOYMENT / "deploy_public_agent.sh")],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    invocation = calls.read_text()
    assert "TrialEnabled=true" in invocation
    assert "TrialOriginKey=" + "b" * 32 in invocation
