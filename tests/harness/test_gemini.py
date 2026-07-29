from __future__ import annotations

import json
from dataclasses import replace

import pytest

from decimal import Decimal

from quantify.engine import (
    ClaimVerdict,
    CounterevidencePair,
    MetricThresholdClaim,
    Relation,
    ReportSpan,
    ReviewReason,
    StatementClassification,
)
from quantify.harness import (
    DisclosureContext,
    ExtractedStatement,
    ExtractionResult,
    GeminiDisclosureConfig,
    GeminiDisclosureDetector,
    GeminiExtractionConfig,
    GeminiStructuredExtractor,
    verify_report,
)
from tests.conftest import load_snapshot


REPORT = "Microsoft revenue increased from fiscal 2023 to fiscal 2024."


class _Transport:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.url = ""
        self.headers: dict[str, str] = {}
        self.body: dict = {}
        self.timeout_seconds = 0.0

    def post_json(
        self, *, url: str, headers: dict[str, str], body: dict, timeout_seconds: float
    ) -> dict:
        self.url = url
        self.headers = headers
        self.body = body
        self.timeout_seconds = timeout_seconds
        return self.response


def test_gemini_extractor_proposes_a_grounded_claim_for_deterministic_verification() -> None:
    transport = _Transport(
        _response(
            {
                "statements": [
                    {
                        "classification": "classified",
                        "report_span_id": "report-s1",
                        "claim_type": "comparison",
                        "relation": "greater_than",
                        "left_evidence_id": "msft-revenue-fy2024",
                        "right_evidence_id": "msft-revenue-fy2023",
                    }
                ]
            }
        )
    )
    config = GeminiExtractionConfig(
        input_price_per_million_usd=0.25,
        output_price_per_million_usd=1.5,
    )
    snapshot = load_snapshot("msft_revenue_regression.json")

    extraction = GeminiStructuredExtractor(
        api_key="test-key", config=config, transport=transport
    ).extract(report_text=REPORT, snapshot=snapshot)
    result = verify_report(
        report_text=REPORT, snapshot=snapshot, extraction=extraction
    )

    serialized = json.dumps(transport.body, sort_keys=True)
    facts = json.loads(transport.body["contents"][0]["parts"][0]["text"])[
        "frozen_facts"
    ]
    assert transport.url.endswith("models/gemini-3.1-flash-lite:generateContent")
    assert transport.headers["x-goog-api-key"] == "test-key"
    assert len(config.prompt_hash) == 64
    assert transport.timeout_seconds == 4.0
    assert len(facts) == 2
    assert "expected_verdict" not in serialized
    assert "case_id" not in serialized
    assert extraction.input_tokens == 100
    assert extraction.output_tokens == 20
    assert extraction.total_cost == pytest.approx(0.000055)
    assert extraction.failure_reason is None
    assert result.claim_verdicts[0].verdict is ClaimVerdict.VERIFIED


def test_malformed_gemini_output_fails_closed_to_agent_resolution() -> None:
    snapshot = load_snapshot("msft_revenue_regression.json")
    extraction = GeminiStructuredExtractor(
        api_key="test-key",
        transport=_Transport(_response({"statements": "not-a-list"})),
    ).extract(report_text=REPORT, snapshot=snapshot)
    result = verify_report(
        report_text=REPORT, snapshot=snapshot, extraction=extraction
    )

    assert extraction.statements[0].statement_id == "gemini-schema-failure"
    assert extraction.failure_reason == "model_output_invalid"
    assert result.claim_verdicts == ()
    assert result.review_items[0].reason is ReviewReason.EXTRACTION_SCHEMA_FAILURE


def test_hidden_facts_do_not_enter_the_model_visible_payload() -> None:
    snapshot = replace(
        load_snapshot("msft_revenue_regression.json"),
        visible_evidence_ids=("msft-revenue-fy2024",),
    )
    transport = _Transport(_response({"statements": []}))

    GeminiStructuredExtractor(api_key="test-key", transport=transport).extract(
        report_text=REPORT, snapshot=snapshot
    )

    facts = json.loads(transport.body["contents"][0]["parts"][0]["text"])[
        "frozen_facts"
    ]
    assert facts == [
        {
            "evidence_id": "msft-revenue-fy2024",
            "metric": "revenue",
            "value": "245122000000",
            "unit": "USD",
            "period_start": "2023-07-01",
            "period_end": "2024-06-30",
            "filed_at": "2024-07-30",
        }
    ]


def test_gemini_disclosure_detector_receives_fact_context_and_composes_defeat() -> None:
    report = "Quantum revenue was under $415 million."
    transport = _Transport(
        _response(
            {
                "assessments": [
                    {
                        "claim_id": "qtm-under-415m",
                        "defeating_evidence_id": "qtm-revenue-fy2023-restated",
                        "status": "not_disclosed",
                    }
                ]
            }
        )
    )
    detector = GeminiDisclosureDetector(
        api_key="test-key", config=GeminiDisclosureConfig(), transport=transport
    )
    extraction = ExtractionResult(
        extractor_version="fixture-v1",
        statements=(
            ExtractedStatement(
                statement_id="s1",
                classification=StatementClassification.CLASSIFIED,
                report_span=ReportSpan(
                    "span-s1", report, 0, len(report), report[:-1], 0, len(report) - 1
                ),
                claims=(
                    MetricThresholdClaim(
                        claim_id="qtm-under-415m",
                        cited_evidence_id="qtm-revenue-fy2023-as-filed",
                        relation=Relation.LESS_THAN,
                        threshold=Decimal("415000000"),
                    ),
                ),
            ),
        ),
    )

    result = verify_report(
        report_text=report,
        snapshot=load_snapshot(
            "quantum_revenue_restatement.json", allow_conflicting_evidence=True
        ),
        extraction=extraction,
        disclosure_detector=detector,
    )

    body = json.dumps(transport.body, sort_keys=True)
    assert result.claim_verdicts[0].verdict is ClaimVerdict.DEFEATED
    assert "qtm-revenue-fy2023-restated" in body
    assert "expected_verdict" not in body
    assert "case_id" not in body
    assert len(detector.config.prompt_hash) == 64


def test_invalid_gemini_disclosure_result_stays_agent_resolvable() -> None:
    report = "Quantum revenue was under $415 million."
    detector = GeminiDisclosureDetector(
        api_key="test-key",
        transport=_Transport(_response({"assessments": []})),
    )
    extraction = ExtractionResult(
        extractor_version="fixture-v1",
        statements=(
            ExtractedStatement(
                statement_id="s1",
                classification=StatementClassification.CLASSIFIED,
                report_span=ReportSpan(
                    "span-s1", report, 0, len(report), report[:-1], 0, len(report) - 1
                ),
                claims=(
                    MetricThresholdClaim(
                        claim_id="qtm-under-415m",
                        cited_evidence_id="qtm-revenue-fy2023-as-filed",
                        relation=Relation.LESS_THAN,
                        threshold=Decimal("415000000"),
                    ),
                ),
            ),
        ),
    )

    result = verify_report(
        report_text=report,
        snapshot=load_snapshot(
            "quantum_revenue_restatement.json", allow_conflicting_evidence=True
        ),
        extraction=extraction,
        disclosure_detector=detector,
    )

    assert result.claim_verdicts[0].verdict is ClaimVerdict.REQUIRES_AGENT_RESOLUTION


def test_gemini_timeout_fails_closed_without_retrying_or_publishing() -> None:
    class _TimeoutTransport:
        def post_json(self, **kwargs):
            raise RuntimeError("Gemini extraction request exceeded its latency budget")

    extraction = GeminiStructuredExtractor(
        api_key="test-key", transport=_TimeoutTransport()
    ).extract(report_text=REPORT, snapshot=load_snapshot("msft_revenue_regression.json"))

    assert extraction.statements[0].classification is StatementClassification.REQUIRES_AGENT_RESOLUTION
    assert extraction.input_tokens == 0
    assert extraction.total_cost == 0.0
    assert extraction.failure_reason == "transport_failure"


def test_disclosure_timeout_becomes_ambiguous_instead_of_an_omission() -> None:
    class _TimeoutTransport:
        def post_json(self, **kwargs):
            raise RuntimeError("Gemini extraction request exceeded its latency budget")

    detector = GeminiDisclosureDetector(api_key="test-key", transport=_TimeoutTransport())
    snapshot = load_snapshot(
        "quantum_revenue_restatement.json", allow_conflicting_evidence=True
    )
    claim = MetricThresholdClaim(
        claim_id="claim",
        cited_evidence_id="qtm-revenue-fy2023-as-filed",
        relation=Relation.LESS_THAN,
        threshold=Decimal("415000000"),
    )
    assessment = detector.assess(
        report_text="report",
        counterevidence_pairs=(
            CounterevidencePair(
                claim_id="claim", evidence_id="qtm-revenue-fy2023-restated"
            ),
        ),
        contexts=(
            DisclosureContext(
                claim=claim,
                defeating_evidence=snapshot.evidence_by_id(
                    "qtm-revenue-fy2023-restated"
                ),
            ),
        ),
    )

    assert assessment[0].status.value == "ambiguous"


def _response(payload: dict) -> dict:
    return {
        "candidates": [
            {"content": {"parts": [{"text": json.dumps(payload)}]}}
        ],
        "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20},
    }
