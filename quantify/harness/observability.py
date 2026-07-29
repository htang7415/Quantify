"""Privacy-safe structured JSONL request observability."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


OBSERVABILITY_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class RequestMetrics:
    cache_hit: bool
    sec_network_calls: int
    filings_selected: int
    evidence_count: int
    eligible_evidence_count: int
    rejected_evidence_count: int
    verified_count: int
    unsupported_count: int
    defeated_count: int
    qualified_count: int
    agent_resolution_count: int
    empty_result: bool
    total_cost: float
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    extraction_latency_seconds: float = 0.0
    disclosure_latency_seconds: float = 0.0
    verification_latency_seconds: float = 0.0
    verification_cache_hit: bool = False
    acquisition_rounds: int = 0
    acquisition_request_types: tuple[str, ...] = ()
    agent_resolution_queue_count: int = 0
    batch_size: int = 1
    company_cik: str = "unconfigured"
    rejected_evidence_reasons: tuple[tuple[str, int], ...] = ()
    classified_statement_count: int = 0
    unclassified_statement_count: int = 0
    non_factual_statement_count: int = 0
    classified_fraction: float = 0.0
    unclassified_fraction: float = 0.0
    agent_resolution_action_count: int = 0
    agent_resolution_resolved_count: int = 0
    agent_resolution_unresolved_count: int = 0


def append_jsonl(*, path: Path, metrics: RequestMetrics) -> None:
    """Append aggregate metrics only; report text and secrets have no field here."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                request_metrics_as_dict(metrics=metrics),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )


def request_metrics_as_dict(*, metrics: RequestMetrics) -> dict[str, Any]:
    """Return the versioned, privacy-safe interchange record for one request."""

    record = asdict(metrics)
    record["acquisition_request_types"] = list(metrics.acquisition_request_types)
    record["rejected_evidence_reasons"] = [
        {"reason": reason, "count": count}
        for reason, count in metrics.rejected_evidence_reasons
    ]
    return {"observability_schema_version": OBSERVABILITY_SCHEMA_VERSION, **record}


def export_jsonl_to_parquet(*, jsonl_path: Path, parquet_path: Path) -> None:
    """Convert validated aggregate JSONL records into a typed Parquet dataset."""

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:  # pragma: no cover - package dependency is explicit
        raise RuntimeError("Parquet export requires the pyarrow package") from error

    records = []
    for line_number, line in enumerate(
        jsonl_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid observability JSONL at line {line_number}") from error
        _validate_record(record=record, line_number=line_number)
        records.append(record)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(records, schema=_parquet_schema(pa))
    pq.write_table(table, parquet_path, compression="zstd")


def _validate_record(*, record: object, line_number: int) -> None:
    if not isinstance(record, dict):
        raise ValueError(f"observability record {line_number} must be an object")
    expected = {"observability_schema_version", *RequestMetrics.__dataclass_fields__}
    if set(record) != expected:
        raise ValueError(f"observability record {line_number} has unsupported fields")
    if record["observability_schema_version"] != OBSERVABILITY_SCHEMA_VERSION:
        raise ValueError(f"observability record {line_number} has an unsupported version")


def _parquet_schema(pa):
    return pa.schema(
        [
            pa.field("observability_schema_version", pa.string()),
            pa.field("cache_hit", pa.bool_()),
            pa.field("sec_network_calls", pa.int64()),
            pa.field("filings_selected", pa.int64()),
            pa.field("evidence_count", pa.int64()),
            pa.field("eligible_evidence_count", pa.int64()),
            pa.field("rejected_evidence_count", pa.int64()),
            pa.field("verified_count", pa.int64()),
            pa.field("unsupported_count", pa.int64()),
            pa.field("defeated_count", pa.int64()),
            pa.field("qualified_count", pa.int64()),
            pa.field("agent_resolution_count", pa.int64()),
            pa.field("empty_result", pa.bool_()),
            pa.field("total_cost", pa.float64()),
            pa.field("llm_input_tokens", pa.int64()),
            pa.field("llm_output_tokens", pa.int64()),
            pa.field("extraction_latency_seconds", pa.float64()),
            pa.field("disclosure_latency_seconds", pa.float64()),
            pa.field("verification_latency_seconds", pa.float64()),
            pa.field("verification_cache_hit", pa.bool_()),
            pa.field("acquisition_rounds", pa.int64()),
            pa.field("acquisition_request_types", pa.list_(pa.string())),
            pa.field("agent_resolution_queue_count", pa.int64()),
            pa.field("batch_size", pa.int64()),
            pa.field("company_cik", pa.string()),
            pa.field(
                "rejected_evidence_reasons",
                pa.list_(
                    pa.struct(
                        [pa.field("reason", pa.string()), pa.field("count", pa.int64())]
                    )
                ),
            ),
            pa.field("classified_statement_count", pa.int64()),
            pa.field("unclassified_statement_count", pa.int64()),
            pa.field("non_factual_statement_count", pa.int64()),
            pa.field("classified_fraction", pa.float64()),
            pa.field("unclassified_fraction", pa.float64()),
            pa.field("agent_resolution_action_count", pa.int64()),
            pa.field("agent_resolution_resolved_count", pa.int64()),
            pa.field("agent_resolution_unresolved_count", pa.int64()),
        ]
    )
