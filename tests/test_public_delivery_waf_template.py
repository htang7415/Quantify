from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
DEPLOY = ROOT / "deploy" / "aws"


def test_global_waf_template_requires_an_explicit_rate_and_safe_aggregation_choice() -> None:
    template = (DEPLOY / "public_delivery_waf_template.yaml").read_text()

    assert "Scope: CLOUDFRONT" in template
    assert "RateLimit:" in template and "MinValue: 100" in template
    assert "Default:" not in template.split("RateLimit:", 1)[1].split("AggregateKeyType:", 1)[0]
    assert "AllowedValues: [IP, FORWARDED_IP]" in template
    assert "FallbackBehavior: MATCH" in template
    assert "Action: {Block: {}}" in template
    assert "SampledRequestsEnabled: false" in template
    assert "PublicDeliveryWebAclArn" in template


def test_web_preview_template_accepts_only_an_optional_waf_association() -> None:
    template = (DEPLOY / "web_preview_template.yaml").read_text()
    deploy = (DEPLOY / "deploy_web_preview.sh").read_text()

    assert "PublicDeliveryWebAclArn:" in template
    assert "HasPublicDeliveryWebAcl" in template
    assert "WebACLId: !If [HasPublicDeliveryWebAcl" in template
    assert "PUBLIC_DELIVERY_WEB_ACL_ARN" in deploy


def test_primary_region_and_cloudfront_waf_exception_are_explicit() -> None:
    specification = (ROOT / "quantify_spec.md").read_text()
    environment = (DEPLOY / "production.env.example").read_text()

    assert "`us-east-2` is the sole V1 operating region" in specification
    assert "managed in `us-east-1`" in specification
    assert "AWS_REGION=us-east-2" in environment
    assert "CLOUDFRONT_WAF_REGION=us-east-1" in environment


def test_waf_deploy_script_requires_authorization_and_explicit_policy_inputs(tmp_path: Path) -> None:
    script = DEPLOY / "deploy_public_delivery_waf.sh"
    unauthorized = subprocess.run(["bash", str(script)], capture_output=True, text=True, check=False)
    assert unauthorized.returncode == 2
    assert "QUANTIFY_AUTHORIZE_AWS_PUBLIC_DELIVERY_WAF_DEPLOY" in unauthorized.stderr

    calls = tmp_path / "calls"
    fake_aws = tmp_path / "aws"
    fake_aws.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$CALLS\"\n")
    fake_aws.chmod(0o755)
    environment = os.environ | {
        "QUANTIFY_AUTHORIZE_AWS_PUBLIC_DELIVERY_WAF_DEPLOY": "1",
        "AWS_REGION": "us-east-2",
        "CLOUDFRONT_WAF_REGION": "us-east-1",
        "WAF_STACK_NAME": "quantify-public-delivery-waf",
        "WAF_RATE_LIMIT": "100",
        "WAF_AGGREGATE_KEY_TYPE": "IP",
        "AWS_BIN": str(fake_aws),
        "CALLS": str(calls),
    }
    deployed = subprocess.run(["bash", str(script)], env=environment, capture_output=True, text=True, check=False)
    assert deployed.returncode == 0
    invocation = calls.read_text()
    assert "cloudformation deploy" in invocation
    assert "RateLimit=100" in invocation
    assert "AggregateKeyType=IP" in invocation
    assert "us-east-1" in invocation
    assert "AWS_REGION must be us-east-2" in script.read_text()
    assert "CLOUDFRONT_WAF_REGION must be us-east-1" in script.read_text()


def test_waf_deploy_script_requires_and_passes_a_forwarded_ip_header(tmp_path: Path) -> None:
    script = DEPLOY / "deploy_public_delivery_waf.sh"
    calls = tmp_path / "calls"
    fake_aws = tmp_path / "aws"
    fake_aws.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$CALLS\"\n")
    fake_aws.chmod(0o755)
    environment = os.environ | {
        "QUANTIFY_AUTHORIZE_AWS_PUBLIC_DELIVERY_WAF_DEPLOY": "1",
        "AWS_REGION": "us-east-2",
        "CLOUDFRONT_WAF_REGION": "us-east-1",
        "WAF_STACK_NAME": "quantify-public-delivery-waf",
        "WAF_RATE_LIMIT": "100",
        "WAF_AGGREGATE_KEY_TYPE": "FORWARDED_IP",
        "AWS_BIN": str(fake_aws),
        "CALLS": str(calls),
    }

    missing_header = subprocess.run(["bash", str(script)], env=environment, capture_output=True, text=True, check=False)
    assert missing_header.returncode != 0
    assert "WAF_FORWARDED_IP_HEADER" in missing_header.stderr

    deployed = subprocess.run(
        ["bash", str(script)],
        env=environment | {"WAF_FORWARDED_IP_HEADER": "X-Trusted-Client-IP"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert deployed.returncode == 0
    assert "ForwardedIpHeader=X-Trusted-Client-IP" in calls.read_text()
