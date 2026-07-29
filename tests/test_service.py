from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from fastapi.testclient import TestClient

from quantify.api import VerifyRequest, create_app
from quantify.engine import (
    DisclosureAssessment,
    DisclosureStatus,
    MetricComparisonClaim,
    MetricThresholdClaim,
    Relation,
    ReportSpan,
    RestatementPolicy,
    RestatementSelection,
    StatementClassification,
)
from quantify.harness import (
    ExtractedStatement,
    ExtractionResult,
    SnapshotBuild,
)
from quantify.harness.audit import build_audit_manifest
from quantify.harness.sec.client import SecCompanyFactsClient, SecPayload
from quantify.harness.sec.provider import SecSnapshotProvider
from quantify.service import ApplicationService
from tests.conftest import load_snapshot


FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures"
REPORT_FIXTURE = json.loads(
    (FIXTURE_ROOT / "reports" / "msft_revenue_growth_v1.json").read_text()
)
MSFT_FACTS = (FIXTURE_ROOT / "sec" / "msft_companyfacts.json").read_bytes()


class MicrosoftGrowthExtractor:
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, *, report_text: str, snapshot) -> ExtractionResult:
        self.calls += 1
        previous = next(
            item
            for item in snapshot.evidence
            if item.metric == "revenue" and item.period_end == date(2023, 6, 30)
        )
        current = next(
            item
            for item in snapshot.evidence
            if item.metric == "revenue" and item.period_end == date(2024, 6, 30)
        )
        fragment = "Microsoft revenue increased from fiscal 2023 to fiscal 2024"
        return ExtractionResult(
            extractor_version="fixture-msft-v1",
            input_tokens=12,
            output_tokens=5,
            total_cost=0.001,
            statements=(
                ExtractedStatement(
                    statement_id="msft-growth",
                    classification=StatementClassification.CLASSIFIED,
                    report_span=ReportSpan(
                        span_id="msft-growth-span",
                        sentence_text=report_text,
                        sentence_start=0,
                        sentence_end=len(report_text),
                        claim_fragment=fragment,
                        fragment_start=0,
                        fragment_end=len(fragment),
                    ),
                    claims=(
                        MetricComparisonClaim(
                            claim_id="msft-revenue-growth",
                            left_evidence_id=current.evidence_id,
                            relation=Relation.GREATER_THAN,
                            right_evidence_id=previous.evidence_id,
                        ),
                    ),
                ),
            ),
        )


def _submission_payload() -> bytes:
    return json.dumps(
        {
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2024-07-30"],
                    "reportDate": ["2024-06-30"],
                    "accessionNumber": ["0000950170-24-087843"],
                    "primaryDocument": ["msft-20240630.htm"],
                },
                "files": [],
            }
        }
    ).encode()


def test_frozen_microsoft_report_runs_through_sec_service_api_and_replay_cache(tmp_path) -> None:
    submissions = _submission_payload()
    client = SecCompanyFactsClient(
        cache_dir=tmp_path / "sec-cache",
        user_agent="Quantify test contact@example.com",
        transport=lambda url, _agent: (
            MSFT_FACTS if "companyfacts" in url else submissions
        ),
    )
    metrics = []
    extractor = MicrosoftGrowthExtractor()
    service = ApplicationService(
        snapshot_provider=SecSnapshotProvider(client=client),
        extractor=extractor,
        metrics_sink=metrics.append,
        extraction_model="fixture-msft-model-2026-07",
        prompt_hash="fixture-msft-prompt-v1",
        disclosure_detector_version="not-invoked-v1",
        sec_network_call_count=lambda: client.network_call_count,
    )
    request = {
        "analysis": REPORT_FIXTURE["analysis"],
        "as_of_date": REPORT_FIXTURE["as_of_date"],
        "forms": REPORT_FIXTURE["forms"],
    }
    api = TestClient(create_app(service))

    first = api.post("/v1/companies/789019/verify", json=request)
    second = api.post("/v1/companies/789019/verify", json=request)

    assert first.status_code == second.status_code == 200
    first_payload = first.json()
    assert first_payload["claim_results"] == [
        {
            "claim_id": "msft-revenue-growth",
            "verdict": REPORT_FIXTURE["expected_verdict"],
            "counterevidence_detail": [],
        }
    ]
    assert first_payload["evidence_scope"]["forms"] == ["10-K"]
    assert first_payload["temporal_persistence"] == [
        {
            "metric_name": "revenue",
            "consecutive_periods": 3,
            "direction": "positive",
            "period_ids": [
                "0000789019-revenue-2021-07-01-2022-06-30-000095017024087843",
                "0000789019-revenue-2022-07-01-2023-06-30-000095017024087843",
                "0000789019-revenue-2023-07-01-2024-06-30-000095017024087843",
            ],
        }
    ]
    assert first_payload["audit_manifest"]["extraction_model"] == (
        "fixture-msft-model-2026-07"
    )
    assert first_payload["audit_manifest"]["prompt_hash"] == "fixture-msft-prompt-v1"
    assert first_payload["verification_cache_hit"] is False
    assert second.json()["verification_cache_hit"] is True
    assert extractor.calls == 1
    assert client.network_call_count == 2
    assert metrics[0].sec_network_calls == 2
    assert metrics[1].sec_network_calls == 0
    assert metrics[1].verification_cache_hit is True
    assert metrics[0].total_cost == 0.001
    assert metrics[0].llm_input_tokens == 12
    assert metrics[0].llm_output_tokens == 5
    assert metrics[1].total_cost == 0.0
    assert metrics[0].extraction_latency_seconds >= 0.0
    assert metrics[0].verification_latency_seconds >= 0.0
    assert metrics[0].classified_statement_count == 1
    assert metrics[0].classified_fraction == 1.0
    assert metrics[0].unclassified_fraction == 0.0

    uncached = ApplicationService(
        snapshot_provider=SecSnapshotProvider(client=client),
        extractor=MicrosoftGrowthExtractor(),
        extraction_model="fixture-msft-model-2026-07",
        prompt_hash="fixture-msft-prompt-v1",
        disclosure_detector_version="not-invoked-v1",
        sec_network_call_count=lambda: client.network_call_count,
    ).verify(
        cik="789019",
        request=VerifyRequest(
            analysis=REPORT_FIXTURE["analysis"],
            as_of_date=date.fromisoformat(REPORT_FIXTURE["as_of_date"]),
            forms=("10-K",),
        ),
    )

    assert uncached["verification_cache_hit"] is False
    assert uncached["claim_results"] == first_payload["claim_results"]
    assert uncached["audit_manifest"]["manifest_hash"] == first_payload[
        "audit_manifest"
    ]["manifest_hash"]


class FixedSnapshotProvider:
    def __init__(self, build: SnapshotBuild) -> None:
        self._build = build

    def build(self, *, cik: str, as_of_date: date, forms: tuple[str, ...]) -> SnapshotBuild:
        return self._build


class QuantumExtractor:
    def extract(self, *, report_text: str, snapshot) -> ExtractionResult:
        fragment = "Quantum revenue was under $415 million"
        return ExtractionResult(
            extractor_version="fixture-quantum-v1",
            statements=(
                ExtractedStatement(
                    statement_id="quantum-under-415m",
                    classification=StatementClassification.CLASSIFIED,
                    report_span=ReportSpan(
                        span_id="quantum-span",
                        sentence_text=report_text,
                        sentence_start=0,
                        sentence_end=len(report_text),
                        claim_fragment=fragment,
                        fragment_start=0,
                        fragment_end=len(fragment),
                    ),
                    claims=(
                        MetricThresholdClaim(
                            claim_id="quantum-under-415m",
                            cited_evidence_id="qtm-revenue-fy2023-as-filed",
                            relation=Relation.LESS_THAN,
                            threshold=Decimal("415000000"),
                        ),
                    ),
                ),
            ),
        )


class OmissionDetector:
    def __init__(self) -> None:
        self.pairs = ()

    def assess(self, *, report_text: str, counterevidence_pairs, contexts):
        self.pairs = counterevidence_pairs
        return tuple(
            DisclosureAssessment(
                claim_id=pair.claim_id,
                defeating_evidence_id=pair.evidence_id,
                status=DisclosureStatus.NOT_DISCLOSED,
                detector_version="fixture-disclosure-v1",
            )
            for pair in counterevidence_pairs
        )


def test_service_runs_ce1_disclosure_and_final_verdict_composition() -> None:
    snapshot = load_snapshot(
        "quantum_revenue_restatement.json", allow_conflicting_evidence=True
    )
    selection = RestatementSelection(
        policy=RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
        as_of_date=date(2024, 6, 28),
        selected_evidence_ids=tuple(item.evidence_id for item in snapshot.evidence),
        superseded_evidence_ids=(),
        eligibility_decisions=(),
    )
    source = SecPayload(
        cik="0000709283",
        source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000709283.json",
        payload=b"{}",
        payload_sha256="fixture-quantum-payload",
        retrieved_at="2026-07-28T00:00:00+00:00",
        cache_hit=True,
    )
    build = SnapshotBuild(
        snapshot=snapshot,
        selection=selection,
        audit_manifest=build_audit_manifest(
            snapshot=snapshot,
            selection=selection,
            source=source,
            normalized_evidence=snapshot.evidence,
        ),
    )
    metrics = []
    detector = OmissionDetector()
    service = ApplicationService(
        snapshot_provider=FixedSnapshotProvider(build),
        extractor=QuantumExtractor(),
        disclosure_detector=detector,
        disclosure_detector_version="fixture-disclosure-v1",
        metrics_sink=metrics.append,
    )

    response = service.verify(
        cik="709283",
        request=VerifyRequest(
            analysis="Quantum revenue was under $415 million.",
            as_of_date=date(2024, 6, 28),
            forms=("10-K",),
        ),
    )

    assert len(detector.pairs) == 1
    assert response["claim_results"][0]["verdict"] == "defeated"
    assert response["material_omissions"] == [
        {
            "claim_id": "quantum-under-415m",
            "evidence_id": "qtm-revenue-fy2023-restated",
        }
    ]
    assert response["audit_manifest"]["disclosure_detector_version"] == (
        "fixture-disclosure-v1"
    )
    assert response["audit_manifest"]["agent_resolution_records"] == (
        ("assess_disclosure", "missing_disclosure_assessment:resolved"),
    )
    assert metrics[0].defeated_count == 1
    assert metrics[0].agent_resolution_count == 0
    assert metrics[0].disclosure_latency_seconds >= 0.0
    assert metrics[0].agent_resolution_action_count == 1
    assert metrics[0].agent_resolution_resolved_count == 1
