from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "deploy" / "aws" / "check_research_task_queue_load.py"
spec = importlib.util.spec_from_file_location("check_research_task_queue_load", SCRIPT)
check_research_task_queue_load = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(check_research_task_queue_load)


class _Sqs:
    def __init__(self, *, queue: tuple[int, int, int], dlq: tuple[int, int, int]) -> None:
        self.queue = queue
        self.dlq = dlq
        self.calls: list[dict[str, object]] = []

    def get_queue_attributes(self, **kwargs):
        self.calls.append(kwargs)
        values = self.dlq if kwargs["QueueUrl"] == "dlq" else self.queue
        return {"Attributes": {
            "ApproximateNumberOfMessages": str(values[0]),
            "ApproximateNumberOfMessagesNotVisible": str(values[1]),
            "ApproximateNumberOfMessagesDelayed": str(values[2]),
        }}


def test_queue_load_check_returns_only_safe_depth_metadata() -> None:
    client = _Sqs(queue=(2, 1, 3), dlq=(0, 0, 0))
    result = check_research_task_queue_load.check(
        queue_url="queue", dlq_url="dlq", region="us-east-2",
        maximum_in_flight=1, maximum_backlog=5, client=client,
    )
    assert result == {
        "backlog": 5, "dlq_depth": 0, "in_flight": 1,
        "maximum_backlog": 5, "maximum_in_flight": 1,
    }
    assert client.calls[0]["AttributeNames"] == [
        "ApproximateNumberOfMessages",
        "ApproximateNumberOfMessagesNotVisible",
        "ApproximateNumberOfMessagesDelayed",
    ]


@pytest.mark.parametrize(
    "queue,dlq,maximum_in_flight,maximum_backlog",
    [((0, 2, 0), (0, 0, 0), 1, 5), ((3, 0, 3), (0, 0, 0), 1, 5), ((0, 0, 0), (1, 0, 0), 1, 5)],
)
def test_queue_load_check_fails_closed_at_each_limit(
    queue: tuple[int, int, int], dlq: tuple[int, int, int], maximum_in_flight: int, maximum_backlog: int,
) -> None:
    with pytest.raises(RuntimeError):
        check_research_task_queue_load.check(
            queue_url="queue", dlq_url="dlq", region="us-east-2",
            maximum_in_flight=maximum_in_flight, maximum_backlog=maximum_backlog,
            client=_Sqs(queue=queue, dlq=dlq),
        )


def test_queue_load_check_wrapper_requires_explicit_authorization() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "deploy" / "aws" / "check_research_task_queue_load.sh")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "QUANTIFY_AUTHORIZE_RESEARCH_TASK_QUEUE_LOAD_CHECK" in result.stderr


def test_queue_load_check_wrapper_uses_the_project_virtual_environment() -> None:
    wrapper = (ROOT / "deploy" / "aws" / "check_research_task_queue_load.sh").read_text()

    assert 'python_bin="${QUANTIFY_PYTHON_BIN:-$repository_root/.venv/bin/python}"' in wrapper
    assert 'exec "$python_bin"' in wrapper
