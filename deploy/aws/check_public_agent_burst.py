"""Bounded unauthenticated public-edge burst check; it never invokes a model."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def _one(url: str) -> int:
    request = Request(url, data=b'{"cik":"0000789019","analysis":"x","as_of_date":"2024-07-30"}', headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=15) as response:
            return response.status
    except HTTPError as error:
        return error.code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--requests", type=int, default=10)
    args = parser.parse_args()
    if not args.url.startswith("https://") or not 1 <= args.requests <= 20:
        raise ValueError("burst check inputs are invalid")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.requests) as pool:
        statuses = list(pool.map(_one, [args.url] * args.requests))
    if any(status < 400 or status >= 500 for status in statuses):
        raise RuntimeError("unauthenticated burst reached an unsafe public edge state")
    print(json.dumps({"requests": args.requests, "statuses": sorted(statuses)}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify public-agent burst check failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
