from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

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
from quantify.harness import ExtractedStatement, ExtractionResult, SnapshotBuild
from quantify.harness.audit import build_audit_manifest
from quantify.harness.coverage import EvidenceRequestType
from quantify.harness.sec.client import SecCompanyFactsClient, SecPayload
from quantify.harness.sec.provider import SecSnapshotProvider
from quantify.service import ApplicationService
from tests.conftest import load_snapshot


FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures"
MSFT_FACTS = (FIXTURE_ROOT / "sec" / "msft_companyfacts.json").read_bytes()
AAPL_FACTS = (FIXTURE_ROOT / "sec" / "aapl_companyfacts.json").read_bytes()
AAPL_REPORT = json.loads(
    (FIXTURE_ROOT / "reports" / "aapl_revenue_growth_v1.json").read_text()
)


def _submissions_payload(*, accession: str, filing_date: str, report_date: str) -> bytes:
    return json.dumps(
        {
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": [filing_date],
                    "reportDate": [report_date],
                    "accessionNumber": [accession],
                    "primaryDocument": ["annual.htm"],
                },
                "files": [],
            }
        }
    ).encode()


class FiscalRevenueGrowthExtractor:
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, *, report_text: str, snapshot) -> ExtractionResult:
        self.calls += 1
        annual_revenue = sorted(
            (
                item
                for item in snapshot.evidence
                if item.metric == "revenue"
                and (item.period_end - item.period_start).days >= 300
            ),
            key=lambda item: item.period_end,
        )
        previous, current = annual_revenue[-2:]
        fragment = report_text.rstrip(".")
        return ExtractionResult(
            extractor_version="fixture-growth-v1",
            statements=(
                ExtractedStatement(
                    statement_id="revenue-growth",
                    classification=StatementClassification.CLASSIFIED,
                    report_span=ReportSpan(
                        span_id="revenue-growth-span",
                        sentence_text=report_text,
                        sentence_start=0,
                        sentence_end=len(report_text),
                        claim_fragment=fragment,
                        fragment_start=0,
                        fragment_end=len(fragment),
                    ),
                    claims=(
                        MetricComparisonClaim(
                            claim_id="revenue-growth",
                            left_evidence_id=current.evidence_id,
                            relation=Relation.GREATER_THAN,
                            right_evidence_id=previous.evidence_id,
                        ),
                    ),
                ),
            ),
        )


def _multi_company_service(tmp_path, *, metrics=None) -> tuple[ApplicationService, FiscalRevenueGrowthExtractor]:
    submissions = {
        "0000789019": _submissions_payload(
            accession="0000950170-24-087843",
            filing_date="2024-07-30",
            report_date="2024-06-30",
        ),
        "0000320193": _submissions_payload(
            accession="0000320193-24-000123",
            filing_date="2024-11-01",
            report_date="2024-09-28",
        ),
    }

    def transport(url: str, _agent: str) -> bytes:
        if "companyfacts" in url:
            return AAPL_FACTS if "0000320193" in url else MSFT_FACTS
        cik = "0000320193" if "0000320193" in url else "0000789019"
        return submissions[cik]

    client = SecCompanyFactsClient(
        cache_dir=tmp_path / "sec-cache",
        user_agent="Quantify test contact@example.com",
        transport=transport,
    )
    extractor = FiscalRevenueGrowthExtractor()
    return (
        ApplicationService(
            snapshot_provider=SecSnapshotProvider(client=client),
            extractor=extractor,
            metrics_sink=metrics.append if metrics is not None else None,
            extraction_model="fixture-growth-model-2026-07",
            sec_network_call_count=lambda: client.network_call_count,
        ),
        extractor,
    )


def test_frozen_apple_report_replays_through_the_second_company_path(tmp_path) -> None:
    service, extractor = _multi_company_service(tmp_path)
    response = TestClient(create_app(service)).post(
        "/v1/companies/320193/verify",
        json={
            "analysis": AAPL_REPORT["analysis"],
            "as_of_date": AAPL_REPORT["as_of_date"],
            "forms": AAPL_REPORT["forms"],
        },
    )

    assert response.status_code == 200
    assert response.json()["claim_results"][0]["verdict"] == AAPL_REPORT[
        "expected_verdict"
    ]
    assert response.json()["audit_manifest"]["filing_accessions"] == [
        "0000320193-24-000123"
    ]
    assert extractor.calls == 1


def test_acquisition_expands_only_requested_sec_evidence_family(tmp_path) -> None:
    metrics = []
    service, _ = _multi_company_service(tmp_path, metrics=metrics)
    response = service.verify(
        cik="789019",
        request=VerifyRequest(
            analysis="Microsoft revenue increased from fiscal 2023 to fiscal 2024.",
            as_of_date=date(2024, 7, 30),
            forms=("10-K",),
            evidence_requests=(EvidenceRequestType.PROFITABILITY_METRICS,),
        ),
    )

    assert response["claim_results"][0]["verdict"] == "verified"
    assert response["audit_manifest"]["acquisition_records"] == (
        (
            "profitability_metrics",
            "deterministic coverage gap: profitability_metrics",
        ),
    )
    assert metrics[0].acquisition_rounds == 1
    assert metrics[0].acquisition_request_types == ("profitability_metrics",)
    assert metrics[0].evidence_count > 2
    assert metrics[0].company_cik == "789019"


class FixedSnapshotProvider:
    def __init__(self, build: SnapshotBuild) -> None:
        self._build = build

    def build(self, *, cik: str, as_of_date: date, forms: tuple[str, ...]) -> SnapshotBuild:
        if cik == "bad":
            raise ValueError("fixture request is invalid")
        return self._build


class NonImprovingSnapshotProvider(FixedSnapshotProvider):
    def build(
        self,
        *,
        cik: str,
        as_of_date: date,
        forms: tuple[str, ...],
        acquisition_records=(),
    ) -> SnapshotBuild:
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


def _quantum_build() -> SnapshotBuild:
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
    return SnapshotBuild(
        snapshot=snapshot,
        selection=selection,
        audit_manifest=build_audit_manifest(
            snapshot=snapshot,
            selection=selection,
            source=source,
            normalized_evidence=snapshot.evidence,
        ),
    )


def test_review_interface_routes_missing_disclosure_to_actionable_queue() -> None:
    service = ApplicationService(
        snapshot_provider=FixedSnapshotProvider(_quantum_build()),
        extractor=QuantumExtractor(),
    )
    response = TestClient(create_app(service)).post(
        "/v1/companies/709283/review",
        json={
            "analysis": "Quantum revenue was under $415 million.",
            "as_of_date": "2024-06-28",
            "forms": ["10-K"],
        },
    )

    assert response.status_code == 200
    assert response.json()["review_queue"] == [
        {
            "statement_id": "quantum-under-415m",
            "reason": "missing_disclosure_assessment",
            "required_action": "assess_disclosure",
            "message": "No disclosure assessment was supplied for defeating evidence.",
            "claim_id": "quantum-under-415m",
            "report_span_ids": [],
            "evidence_ids": ["qtm-revenue-fy2023-restated"],
            "counterevidence": [],
            "report_spans": [
                {
                    "span_id": "quantum-span",
                    "sentence_text": "Quantum revenue was under $415 million.",
                    "sentence_start": 0,
                    "sentence_end": 39,
                    "claim_fragment": "Quantum revenue was under $415 million",
                    "fragment_start": 0,
                    "fragment_end": 38,
                }
            ],
        }
    ]

    resolved = TestClient(create_app(service)).post(
        "/v1/companies/709283/resolve",
        json={
            "analysis": "Quantum revenue was under $415 million.",
            "as_of_date": "2024-06-28",
            "forms": ["10-K"],
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["agent_resolution_queue"] == response.json()["review_queue"]


def test_acquisition_fails_closed_when_a_provider_does_not_improve_coverage() -> None:
    service = ApplicationService(
        snapshot_provider=NonImprovingSnapshotProvider(_quantum_build()),
        extractor=QuantumExtractor(),
    )

    with pytest.raises(ValueError, match="did not improve"):
        service.verify(
            cik="709283",
            request=VerifyRequest(
                analysis="Quantum revenue was under $415 million.",
                as_of_date=date(2024, 6, 28),
                forms=("10-K",),
                evidence_requests=(EvidenceRequestType.PROFITABILITY_METRICS,),
            ),
        )


def test_batch_endpoint_is_canonical_cached_and_isolates_invalid_items(tmp_path) -> None:
    metrics = []
    service, extractor = _multi_company_service(tmp_path, metrics=metrics)
    request = {
        "items": [
            {
                "cik": "320193",
                "request": {
                    "analysis": AAPL_REPORT["analysis"],
                    "as_of_date": AAPL_REPORT["as_of_date"],
                    "forms": ["10-K"],
                },
            },
            {
                "cik": "789019",
                "request": {
                    "analysis": "Microsoft revenue increased from fiscal 2023 to fiscal 2024.",
                    "as_of_date": "2024-07-30",
                    "forms": ["10-K"],
                },
            },
            {
                "cik": "320193",
                "request": {
                    "analysis": AAPL_REPORT["analysis"],
                    "as_of_date": AAPL_REPORT["as_of_date"],
                    "forms": ["10-K"],
                },
            },
        ]
    }
    response = TestClient(create_app(service)).post("/v1/verify/batch", json=request)

    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["cik"] for item in results] == ["320193", "320193", "789019"]
    assert results[0]["result"]["verification_cache_hit"] is False
    assert results[1]["result"]["verification_cache_hit"] is True
    assert all(item["result"]["claim_results"][0]["verdict"] == "verified" for item in results)
    assert extractor.calls == 2
    assert {item.batch_size for item in metrics} == {3}
    assert {item.company_cik for item in metrics} == {"320193", "789019"}

    invalid_service = ApplicationService(
        snapshot_provider=FixedSnapshotProvider(_quantum_build()),
        extractor=QuantumExtractor(),
    )
    invalid_results = invalid_service.verify_batch(
        items=(
            (
                "bad",
                VerifyRequest(
                    analysis="Quantum revenue was under $415 million.",
                    as_of_date=date(2024, 6, 28),
                    forms=("10-K",),
                ),
            ),
            (
                "709283",
                VerifyRequest(
                    analysis="Quantum revenue was under $415 million.",
                    as_of_date=date(2024, 6, 28),
                    forms=("10-K",),
                ),
            ),
        )
    )

    assert invalid_results[0]["result"]["claim_results"][0]["verdict"] == (
        "requires_agent_resolution"
    )
    assert invalid_results[1]["error"] == {
        "type": "invalid_request",
        "message": "fixture request is invalid",
    }
