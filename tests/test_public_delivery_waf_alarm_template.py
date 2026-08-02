from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
DEPLOY = ROOT / "deploy" / "aws"


def test_waf_alarm_template_requires_explicit_recipient_and_threshold() -> None:
    template = (DEPLOY / "public_delivery_waf_alarm_template.yaml").read_text()

    assert "Namespace: AWS/WAFV2" in template
    assert "MetricName: BlockedRequests" in template
    assert "Period: 300" in template
    assert "Name: WebACL" in template
    assert "Name: Rule" in template
    assert "AlarmEmail:" in template
    assert "Default:" not in template.split("BlockedRequestsThreshold:", 1)[1].split("AlarmEmail:", 1)[0]
    assert "AWS::SNS::Subscription" in template


def test_waf_alarm_deploy_script_requires_explicit_authorization_and_inputs(tmp_path: Path) -> None:
    script = DEPLOY / "deploy_public_delivery_waf_alarm.sh"
    unauthorized = subprocess.run(["bash", str(script)], capture_output=True, text=True, check=False)
    assert unauthorized.returncode == 2
    assert "QUANTIFY_AUTHORIZE_AWS_PUBLIC_DELIVERY_WAF_ALARM_DEPLOY" in unauthorized.stderr

    calls = tmp_path / "calls"
    fake_aws = tmp_path / "aws"
    fake_aws.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$CALLS\"\n")
    fake_aws.chmod(0o755)
    environment = os.environ | {
        "QUANTIFY_AUTHORIZE_AWS_PUBLIC_DELIVERY_WAF_ALARM_DEPLOY": "1",
        "AWS_REGION": "us-east-2",
        "CLOUDFRONT_WAF_REGION": "us-east-1",
        "WAF_ALARM_STACK_NAME": "quantify-public-delivery-waf-alarm",
        "WAF_METRIC_NAME": "quantify-public-delivery-waf-cloudfront",
        "WAF_RULE_METRIC_NAME": "block-rate-limit",
        "WAF_BLOCKED_REQUESTS_ALARM_THRESHOLD": "10",
        "WAF_ALARM_EMAIL": "ops@example.test",
        "AWS_BIN": str(fake_aws),
        "CALLS": str(calls),
    }

    deployed = subprocess.run(["bash", str(script)], env=environment, capture_output=True, text=True, check=False)
    assert deployed.returncode == 0
    invocation = calls.read_text()
    assert "cloudformation deploy" in invocation
    assert "BlockedRequestsThreshold=10" in invocation
    assert "AlarmEmail=ops@example.test" in invocation
    assert "us-east-1" in invocation
    assert "AWS_REGION must be us-east-2" in script.read_text()
    assert "CLOUDFRONT_WAF_REGION must be us-east-1" in script.read_text()
