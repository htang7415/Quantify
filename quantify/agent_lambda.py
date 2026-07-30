"""Private AWS Lambda runner for the deterministic Quantify agent tool."""
from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

from quantify.agent_tool import agent_safe_result


def handler(event: dict[str, object], _context: object) -> dict[str, object]:
    try:
        cik = event["cik"]
        analysis = event["analysis"]
        as_of_date = event["as_of_date"]
    except KeyError as error:
        raise ValueError(f"missing {error.args[0]}") from error
    if not isinstance(cik, str) or not isinstance(analysis, str) or not isinstance(as_of_date, str):
        raise ValueError("cik, analysis, and as_of_date must be strings")
    if not analysis.strip() or len(analysis.split()) > 250:
        raise ValueError("analysis must contain one through 250 words")
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    from botocore.session import get_session

    url = f"{os.environ['QUANTIFY_STAGING_URL'].rstrip('/')}/v1/companies/{cik}/verify"
    body = json.dumps({"analysis": analysis, "as_of_date": as_of_date}, separators=(",", ":")).encode()
    request = AWSRequest(method="POST", url=url, data=body, headers={"content-type": "application/json"})
    session = get_session()
    SigV4Auth(session.get_credentials().get_frozen_credentials(), "execute-api", os.environ["AWS_REGION"]).add_auth(request)
    with urlopen(Request(url, data=body, headers=dict(request.headers.items()), method="POST"), timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(f"Quantify verification failed with HTTP {response.status}")
        return agent_safe_result(json.loads(response.read()))
