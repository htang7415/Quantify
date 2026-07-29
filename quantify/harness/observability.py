"""Privacy-safe structured JSONL request observability."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


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


def append_jsonl(*, path: Path, metrics: RequestMetrics) -> None:
    """Append aggregate metrics only; report text and secrets have no field here."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(asdict(metrics), sort_keys=True, separators=(",", ":")) + "\n")
