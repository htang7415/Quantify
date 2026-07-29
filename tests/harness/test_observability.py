from __future__ import annotations

import json

import pyarrow.parquet as pq
import pytest

from quantify.harness import (
    OBSERVABILITY_SCHEMA_VERSION,
    RequestMetrics,
    append_jsonl,
    export_jsonl_to_parquet,
)


def test_writes_structured_aggregate_metrics_without_report_text(tmp_path) -> None:
    path = tmp_path / "requests.jsonl"
    append_jsonl(path=path, metrics=RequestMetrics(False, 1, 2, 8, 7, 1, 1, 2, 0, 0, 1, False, 0.12))
    record = json.loads(path.read_text())

    assert record["sec_network_calls"] == 1
    assert "report_text" not in record
    assert "analysis" not in record


def test_writes_classification_and_agent_resolution_measurements(tmp_path) -> None:
    path = tmp_path / "requests.jsonl"
    append_jsonl(
        path=path,
        metrics=RequestMetrics(
            False,
            1,
            2,
            8,
            7,
            1,
            1,
            2,
            0,
            0,
            1,
            False,
            0.12,
            rejected_evidence_reasons=(("unit_mismatch", 1),),
            classified_statement_count=2,
            unclassified_statement_count=1,
            classified_fraction=2 / 3,
            unclassified_fraction=1 / 3,
            agent_resolution_action_count=1,
            agent_resolution_resolved_count=1,
        ),
    )

    record = json.loads(path.read_text())

    assert record["rejected_evidence_reasons"] == [
        {"reason": "unit_mismatch", "count": 1}
    ]
    assert record["classified_fraction"] == 2 / 3
    assert record["agent_resolution_resolved_count"] == 1


def test_exports_validated_metrics_to_typed_parquet(tmp_path) -> None:
    jsonl_path = tmp_path / "requests.jsonl"
    parquet_path = tmp_path / "aggregates.parquet"
    append_jsonl(
        path=jsonl_path,
        metrics=RequestMetrics(False, 1, 2, 8, 7, 1, 1, 2, 0, 0, 1, False, 0.12),
    )

    export_jsonl_to_parquet(jsonl_path=jsonl_path, parquet_path=parquet_path)

    table = pq.read_table(parquet_path)
    assert table.schema.field("observability_schema_version").type == "string"
    assert table.to_pylist()[0]["observability_schema_version"] == (
        OBSERVABILITY_SCHEMA_VERSION
    )
    assert table.to_pylist()[0]["sec_network_calls"] == 1


def test_refuses_jsonl_with_unknown_or_sensitive_fields(tmp_path) -> None:
    source = tmp_path / "requests.jsonl"
    source.write_text(
        json.dumps({"observability_schema_version": OBSERVABILITY_SCHEMA_VERSION, "report_text": "secret"})
        + "\n"
    )

    with pytest.raises(ValueError, match="unsupported fields"):
        export_jsonl_to_parquet(jsonl_path=source, parquet_path=tmp_path / "out.parquet")
