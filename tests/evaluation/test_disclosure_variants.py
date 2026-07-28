from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from quantify.engine import (
    DisclosureAssessment,
    DisclosureStatus,
    MetricThresholdClaim,
    Relation,
    ReportSpan,
    StatementClassification,
)
from quantify.harness import ExtractedStatement, ExtractionResult, verify_report
from tests.conftest import load_snapshot


VARIANTS_PATH = Path(__file__).parents[2] / "fixtures" / "cases" / "quantum_disclosure_variants.json"


def test_frozen_disclosure_variants_follow_the_conservative_verdict_table() -> None:
    fixture = json.loads(VARIANTS_PATH.read_text())
    report_text = fixture["report_text"]
    extraction = ExtractionResult(
        extractor_version="gold-v1",
        statements=(
            ExtractedStatement(
                statement_id="s1",
                classification=StatementClassification.CLASSIFIED,
                report_span=ReportSpan(
                    span_id="span-s1", sentence_text=report_text, sentence_start=0,
                    sentence_end=len(report_text), claim_fragment=report_text.rstrip("."),
                    fragment_start=0, fragment_end=len(report_text.rstrip(".")),
                ),
                claims=(MetricThresholdClaim(
                    claim_id="qtm-under-415m", cited_evidence_id="qtm-revenue-fy2023-as-filed",
                    relation=Relation.LESS_THAN, threshold=Decimal("415000000"),
                ),),
            ),
        ),
    )
    snapshot = load_snapshot(fixture["snapshot_fixture"], allow_conflicting_evidence=True)

    for variant in fixture["variants"]:
        status = variant["disclosure_status"]
        assessments = () if status is None else (DisclosureAssessment(
            claim_id="qtm-under-415m", defeating_evidence_id="qtm-revenue-fy2023-restated",
            status=DisclosureStatus(status),
        ),)
        result = verify_report(
            report_text=report_text, snapshot=snapshot, extraction=extraction,
            disclosure_assessments=assessments,
        )

        assert result.claim_verdicts[0].verdict.value == variant["expected_verdict"]
        assert bool(result.material_omissions) is variant["expects_material_omission"]
