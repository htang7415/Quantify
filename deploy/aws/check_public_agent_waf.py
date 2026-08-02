"""Read-only proof that the public delivery distribution has its WAF rate rule."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Mapping, Sequence


_WAF_ARN = re.compile(
    r"^arn:aws(?:-[a-z]+)?:wafv2:us-east-1:\d{12}:global/webacl/([^/]+)/([0-9a-f-]+)$"
)


def _aws(*arguments: str) -> Mapping[str, object]:
    completed = subprocess.run(
        [os.environ.get("AWS_BIN", "aws"), *arguments, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, Mapping):
        raise ValueError("AWS CLI returned an invalid WAF check response")
    return payload


class _AwsCliCloudFrontClient:
    def get_distribution_config(self, *, Id: str) -> Mapping[str, object]:
        return _aws("cloudfront", "get-distribution-config", "--id", Id)


class _AwsCliWafClient:
    def get_web_acl(self, *, Name: str, Scope: str, Id: str) -> Mapping[str, object]:
        return _aws(
            "wafv2", "get-web-acl", "--name", Name, "--scope", Scope, "--id", Id,
            "--region", "us-east-1",
        )


def check(
    *,
    distribution_id: str,
    web_acl_arn: str,
    expected_rate_limit: int,
    expected_aggregate_key_type: str,
    expected_forwarded_ip_header: str | None,
    cloudfront_client: object,
    waf_client: object,
) -> dict[str, object]:
    """Verify a CloudFront association and its approved blocking rate rule."""

    if (
        not distribution_id
        or expected_rate_limit <= 0
        or expected_aggregate_key_type not in {"IP", "FORWARDED_IP"}
        or (expected_aggregate_key_type == "FORWARDED_IP" and not expected_forwarded_ip_header)
        or (expected_aggregate_key_type == "IP" and expected_forwarded_ip_header is not None)
    ):
        raise ValueError("WAF check arguments are invalid")
    match = _WAF_ARN.fullmatch(web_acl_arn)
    if match is None:
        raise ValueError("WAF ARN must name a global CloudFront Web ACL in us-east-1")
    name, acl_id = match.group(1), match.group(2)
    try:
        association = cloudfront_client.get_distribution_config(Id=distribution_id)
        config = association.get("DistributionConfig") if isinstance(association, Mapping) else None
        if not isinstance(config, Mapping) or config.get("WebACLId") != web_acl_arn:
            raise RuntimeError("public delivery distribution is not associated with the approved Web ACL")
        response = waf_client.get_web_acl(Name=name, Scope="CLOUDFRONT", Id=acl_id)
        web_acl = response.get("WebACL") if isinstance(response, Mapping) else None
        rules = web_acl.get("Rules") if isinstance(web_acl, Mapping) else None
        if not isinstance(rules, list):
            raise RuntimeError("approved Web ACL has no rules")
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError("public-delivery WAF state is unavailable") from error

    for rule in rules:
        if not isinstance(rule, Mapping):
            continue
        statement = rule.get("Statement")
        rate = statement.get("RateBasedStatement") if isinstance(statement, Mapping) else None
        action = rule.get("Action")
        forwarded_ip_config = rate.get("ForwardedIPConfig") if isinstance(rate, Mapping) else None
        matches_forwarded_ip_config = (
            expected_aggregate_key_type == "IP"
            and forwarded_ip_config is None
        ) or (
            expected_aggregate_key_type == "FORWARDED_IP"
            and isinstance(forwarded_ip_config, Mapping)
            and forwarded_ip_config.get("HeaderName") == expected_forwarded_ip_header
            and forwarded_ip_config.get("FallbackBehavior") == "MATCH"
        )
        if (
            isinstance(rate, Mapping)
            and rate.get("Limit") == expected_rate_limit
            and rate.get("AggregateKeyType") == expected_aggregate_key_type
            and matches_forwarded_ip_config
            and isinstance(action, Mapping)
            and isinstance(action.get("Block"), Mapping)
            and isinstance(rule.get("Name"), str)
        ):
            return {
                "distribution_id": distribution_id,
                "aggregate_key_type": expected_aggregate_key_type,
                "rate_limit": expected_rate_limit,
                "rule_name": rule["Name"],
                "web_acl_arn": web_acl_arn,
            }
    raise RuntimeError("approved Web ACL has no matching blocking rate rule")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distribution-id", required=True)
    parser.add_argument("--web-acl-arn", required=True)
    parser.add_argument("--expected-rate-limit", type=int, required=True)
    parser.add_argument("--expected-aggregate-key-type", choices=("IP", "FORWARDED_IP"), required=True)
    parser.add_argument("--expected-forwarded-ip-header")
    args = parser.parse_args(argv)
    print(json.dumps(check(
        distribution_id=args.distribution_id,
        web_acl_arn=args.web_acl_arn,
        expected_rate_limit=args.expected_rate_limit,
        expected_aggregate_key_type=args.expected_aggregate_key_type,
        expected_forwarded_ip_header=args.expected_forwarded_ip_header,
        cloudfront_client=_AwsCliCloudFrontClient(),
        waf_client=_AwsCliWafClient(),
    ), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify public-agent WAF check failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
