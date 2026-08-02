"""Read-only bounded-backlog check for the private research-task queue."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Mapping, Sequence


_ATTRIBUTES = (
    "ApproximateNumberOfMessages",
    "ApproximateNumberOfMessagesNotVisible",
    "ApproximateNumberOfMessagesDelayed",
)


def _depth(*, queue_url: str, region: str, client: object) -> dict[str, int]:
    try:
        response = client.get_queue_attributes(
            QueueUrl=queue_url, AttributeNames=list(_ATTRIBUTES)
        )
        values = response.get("Attributes") if isinstance(response, Mapping) else None
        if not isinstance(values, Mapping):
            raise ValueError
        depth = {name: int(values[name]) for name in _ATTRIBUTES}
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("queue depth is unavailable") from error
    except Exception as error:
        raise RuntimeError("queue depth is unavailable") from error
    if any(value < 0 for value in depth.values()):
        raise RuntimeError("queue depth is invalid")
    return depth


def check(
    *, queue_url: str, dlq_url: str, region: str, maximum_in_flight: int,
    maximum_backlog: int, client: object,
) -> dict[str, object]:
    """Fail when a private queue exceeds its approved operational bounds."""

    if not queue_url or not dlq_url or not region or maximum_in_flight < 0 or maximum_backlog < 0:
        raise ValueError("queue load check arguments are invalid")
    queue = _depth(queue_url=queue_url, region=region, client=client)
    dlq = _depth(queue_url=dlq_url, region=region, client=client)
    in_flight = queue["ApproximateNumberOfMessagesNotVisible"]
    backlog = queue["ApproximateNumberOfMessages"] + queue["ApproximateNumberOfMessagesDelayed"]
    dlq_depth = sum(dlq.values())
    if in_flight > maximum_in_flight:
        raise RuntimeError("private task queue exceeds its approved in-flight bound")
    if backlog > maximum_backlog:
        raise RuntimeError("private task queue exceeds its approved backlog bound")
    if dlq_depth != 0:
        raise RuntimeError("private task DLQ is not empty")
    return {
        "backlog": backlog,
        "dlq_depth": dlq_depth,
        "in_flight": in_flight,
        "maximum_backlog": maximum_backlog,
        "maximum_in_flight": maximum_in_flight,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-url", required=True)
    parser.add_argument("--dlq-url", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--maximum-in-flight", type=int, required=True)
    parser.add_argument("--maximum-backlog", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        import boto3
    except ImportError as error:  # pragma: no cover - production dependency.
        raise RuntimeError("boto3 is required for the queue load check") from error
    print(json.dumps(check(
        queue_url=args.queue_url, dlq_url=args.dlq_url, region=args.region,
        maximum_in_flight=args.maximum_in_flight, maximum_backlog=args.maximum_backlog,
        client=boto3.client("sqs", region_name=args.region),
    ), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Quantify research-task queue load check failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
