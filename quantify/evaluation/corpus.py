"""Strict loader for versioned frozen real-filing regression cases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from quantify.engine import ClaimVerdict, DisclosureAssessment, DisclosureStatus, MetricComparisonClaim, MetricThresholdClaim, Relation, ReportSpan, StatementClassification
from quantify.harness import ExtractedStatement, ExtractionResult

from .regression import RegressionCase


@dataclass(frozen=True, slots=True)
class CorpusCaseSpec:
    case_id: str
    category: str
    reviewer_status: str


def load_case_specs(path: Path) -> tuple[CorpusCaseSpec, ...]:
    payload = json.loads(path.read_text())
    if payload["case_set_version"] != "1.0.0":
        raise ValueError("unsupported case-set version")
    specs = tuple(
        CorpusCaseSpec(
            case_id=item["case_id"],
            category=item["category"],
            reviewer_status=item["reviewer_status"],
        )
        for item in payload["cases"]
    )
    if len({spec.case_id for spec in specs}) != len(specs):
        raise ValueError("case IDs must be unique")
    if any(spec.category == "judgment" and spec.reviewer_status != "finance_reviewed" for spec in specs):
        raise ValueError("judgment cases require finance_reviewed status")
    return specs


def case_from_json(*, item: dict, snapshot) -> RegressionCase:
    claim_data = item["claim"]
    relation = Relation(claim_data["relation"])
    if claim_data["type"] == "threshold":
        claim = MetricThresholdClaim(
            claim_id=claim_data["claim_id"], cited_evidence_id=claim_data["cited_evidence_id"],
            relation=relation, threshold=Decimal(claim_data["threshold"]),
        )
    elif claim_data["type"] == "comparison":
        claim = MetricComparisonClaim(
            claim_id=claim_data["claim_id"], left_evidence_id=claim_data["left_evidence_id"],
            relation=relation, right_evidence_id=claim_data["right_evidence_id"],
        )
    else:
        raise ValueError("unsupported claim type")
    report = item["report_text"]
    fragment = item.get("claim_fragment", report.rstrip("."))
    extraction = ExtractionResult(
        extractor_version="gold-v1",
        statements=(ExtractedStatement(
            statement_id="s1", classification=StatementClassification.CLASSIFIED,
            report_span=ReportSpan("span-s1", report, 0, len(report), fragment, 0, len(fragment)),
            claims=(claim,),
        ),),
    )
    assessments = tuple(
        DisclosureAssessment(claim_id=claim.claim_id, defeating_evidence_id=value["evidence_id"], status=DisclosureStatus(value["status"]))
        for value in item.get("disclosure_assessments", [])
    )
    return RegressionCase(
        case_id=item["case_id"], category=item["category"], report_text=report,
        snapshot=snapshot, extraction=extraction, disclosure_assessments=assessments,
        expected_verdicts=((claim.claim_id, ClaimVerdict(item["expected_verdict"])),),
    )
