from __future__ import annotations

from decimal import Decimal

from quantify.engine import (
    ClaimVerdict,
    DisclosureAssessment,
    DisclosureStatus,
    MetricThresholdClaim,
    Relation,
    ReportSpan,
    StatementClassification,
)
from quantify.harness import (
    AutonomousResolutionLoop,
    ExtractedStatement,
    ExtractionResult,
)
from tests.conftest import load_snapshot


REPORT_TEXT = "Quantum revenue was under $415 million."


def _extraction() -> ExtractionResult:
    fragment = "Quantum revenue was under $415 million"
    return ExtractionResult(
        extractor_version="fixture-resolution-v1",
        statements=(
            ExtractedStatement(
                statement_id="quantum-under-415m",
                classification=StatementClassification.CLASSIFIED,
                report_span=ReportSpan(
                    span_id="quantum-span",
                    sentence_text=REPORT_TEXT,
                    sentence_start=0,
                    sentence_end=len(REPORT_TEXT),
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


class _NotDisclosedDetector:
    def assess(self, *, report_text: str, counterevidence_pairs):
        return tuple(
            DisclosureAssessment(
                claim_id=pair.claim_id,
                defeating_evidence_id=pair.evidence_id,
                status=DisclosureStatus.NOT_DISCLOSED,
                detector_version="fixture-resolution-detector-v1",
            )
            for pair in counterevidence_pairs
        )


def _snapshot():
    return load_snapshot("quantum_revenue_restatement.json", allow_conflicting_evidence=True)


def test_resolver_autonomously_assesses_missing_disclosure() -> None:
    outcome = AutonomousResolutionLoop().resolve(
        report_text=REPORT_TEXT,
        snapshot=_snapshot(),
        extraction=_extraction(),
        disclosure_detector=_NotDisclosedDetector(),
    )

    assert outcome.report.claim_verdicts[0].verdict is ClaimVerdict.DEFEATED
    assert outcome.records[0].manifest_entry() == (
        "assess_disclosure",
        "missing_disclosure_assessment:resolved",
    )


def test_resolver_fails_closed_without_an_available_action() -> None:
    outcome = AutonomousResolutionLoop().resolve(
        report_text=REPORT_TEXT, snapshot=_snapshot(), extraction=_extraction()
    )

    assert outcome.report.claim_verdicts[0].verdict is ClaimVerdict.REQUIRES_AGENT_RESOLUTION
    assert outcome.records == ()


def test_resolver_can_be_disabled_without_changing_the_verdict() -> None:
    outcome = AutonomousResolutionLoop(max_actions=0).resolve(
        report_text=REPORT_TEXT,
        snapshot=_snapshot(),
        extraction=_extraction(),
        disclosure_detector=_NotDisclosedDetector(),
    )

    assert outcome.report.claim_verdicts[0].verdict is ClaimVerdict.REQUIRES_AGENT_RESOLUTION
    assert outcome.records == ()
