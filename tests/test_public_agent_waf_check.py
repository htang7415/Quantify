from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "deploy" / "aws" / "check_public_agent_waf.py"
spec = importlib.util.spec_from_file_location("check_public_agent_waf", SCRIPT)
check_public_agent_waf = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(check_public_agent_waf)

ARN = "arn:aws:wafv2:us-east-1:123456789012:global/webacl/quantify-public/12345678-1234-1234-1234-123456789abc"


class _Waf:
    def __init__(
        self,
        *,
        associated: bool = True,
        limit: int = 100,
        aggregate_key_type: str = "IP",
        forwarded_ip_config: dict[str, str] | None = None,
    ) -> None:
        self.associated = associated
        self.limit = limit
        self.aggregate_key_type = aggregate_key_type
        self.forwarded_ip_config = forwarded_ip_config
        self.calls: list[dict[str, object]] = []

    def get_distribution_config(self, **kwargs):
        self.calls.append(kwargs)
        return {"DistributionConfig": {"WebACLId": ARN if self.associated else "arn:aws:wafv2:us-east-1:123456789012:global/webacl/other/12345678-1234-1234-1234-123456789abc"}}

    def get_web_acl(self, **kwargs):
        self.calls.append(kwargs)
        return {"WebACL": {"Rules": [{
            "Name": "rate-limit", "Action": {"Block": {}},
            "Statement": {"RateBasedStatement": {
                "Limit": self.limit,
                "AggregateKeyType": self.aggregate_key_type,
                **({"ForwardedIPConfig": self.forwarded_ip_config} if self.forwarded_ip_config else {}),
            }},
        }]}}


def test_waf_check_returns_only_safe_association_and_rate_metadata() -> None:
    cloudfront, client = _Waf(), _Waf()
    result = check_public_agent_waf.check(
        distribution_id="E123", web_acl_arn=ARN,
        expected_rate_limit=100, expected_aggregate_key_type="IP", expected_forwarded_ip_header=None,
        cloudfront_client=cloudfront, waf_client=client,
    )

    assert result == {
        "distribution_id": "E123", "aggregate_key_type": "IP", "rate_limit": 100, "rule_name": "rate-limit",
        "web_acl_arn": ARN,
    }
    assert cloudfront.calls[0] == {"Id": "E123"}


@pytest.mark.parametrize("associated,limit", [(False, 100), (True, 101)])
def test_waf_check_fails_closed_for_wrong_association_or_rate(associated: bool, limit: int) -> None:
    with pytest.raises(RuntimeError):
        check_public_agent_waf.check(
            distribution_id="E123", web_acl_arn=ARN,
            expected_rate_limit=100, expected_aggregate_key_type="IP", expected_forwarded_ip_header=None,
            cloudfront_client=_Waf(associated=associated), waf_client=_Waf(limit=limit),
        )


def test_waf_check_fails_closed_for_wrong_aggregation_policy() -> None:
    with pytest.raises(RuntimeError):
        check_public_agent_waf.check(
            distribution_id="E123", web_acl_arn=ARN,
            expected_rate_limit=100, expected_aggregate_key_type="IP", expected_forwarded_ip_header=None,
            cloudfront_client=_Waf(), waf_client=_Waf(aggregate_key_type="FORWARDED_IP"),
        )


def test_waf_check_accepts_the_approved_forwarded_ip_policy() -> None:
    result = check_public_agent_waf.check(
        distribution_id="E123", web_acl_arn=ARN,
        expected_rate_limit=100, expected_aggregate_key_type="FORWARDED_IP",
        expected_forwarded_ip_header="X-Trusted-Client-IP",
        cloudfront_client=_Waf(),
        waf_client=_Waf(
            aggregate_key_type="FORWARDED_IP",
            forwarded_ip_config={"HeaderName": "X-Trusted-Client-IP", "FallbackBehavior": "MATCH"},
        ),
    )

    assert result["aggregate_key_type"] == "FORWARDED_IP"


def test_aws_cli_clients_request_only_the_deployed_distribution_and_acl(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **kwargs) -> SimpleNamespace:
        calls.append(arguments)
        if arguments[1:3] == ["cloudfront", "get-distribution-config"]:
            payload = {"DistributionConfig": {"WebACLId": ARN}}
        else:
            payload = {"WebACL": {"Rules": []}}
        return SimpleNamespace(stdout=json.dumps(payload))

    monkeypatch.setattr(check_public_agent_waf.subprocess, "run", fake_run)

    cloudfront = check_public_agent_waf._AwsCliCloudFrontClient()
    waf = check_public_agent_waf._AwsCliWafClient()
    assert cloudfront.get_distribution_config(Id="E123")["DistributionConfig"] == {"WebACLId": ARN}
    assert waf.get_web_acl(Name="quantify-public", Scope="CLOUDFRONT", Id="acl-id")["WebACL"] == {"Rules": []}
    assert calls == [
        ["aws", "cloudfront", "get-distribution-config", "--id", "E123", "--output", "json"],
        [
            "aws", "wafv2", "get-web-acl", "--name", "quantify-public", "--scope", "CLOUDFRONT",
            "--id", "acl-id", "--region", "us-east-1", "--output", "json",
        ],
    ]


def test_waf_check_wrapper_requires_explicit_authorization() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "deploy" / "aws" / "check_public_agent_waf.sh")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_WAF_CHECK" in result.stderr
