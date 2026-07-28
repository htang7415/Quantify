from __future__ import annotations

import json

from quantify.harness import RequestMetrics, append_jsonl


def test_writes_structured_aggregate_metrics_without_report_text(tmp_path) -> None:
    path = tmp_path / "requests.jsonl"
    append_jsonl(path=path, metrics=RequestMetrics(False, 1, 2, 8, 7, 1, 1, 2, 0, 0, 1, False, 0.12))
    record = json.loads(path.read_text())

    assert record["sec_network_calls"] == 1
    assert "report_text" not in record
    assert "analysis" not in record
