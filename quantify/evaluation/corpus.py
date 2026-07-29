"""Strict loader for versioned frozen real-filing regression cases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from quantify.engine import (
    CalibrationMethod,
    ClaimVerdict,
    DisclosureAssessment,
    DisclosureStatus,
    MetricBaselineClaim,
    MetricComparisonClaim,
    MetricThresholdClaim,
    Relation,
    ReportSpan,
    StatementClassification,
    build_upper_baseline_calibration,
)
from quantify.harness import ExtractedStatement, ExtractionResult

from .regression import RegressionCase


SUPPORTED_CASE_SET_VERSIONS = {"1.0.0", "1.1.0"}
REQUIRED_CASE_COUNTS = {"mechanical": 20, "judgment": 10}
JUDGMENT_REVIEW_STATUSES = {"not_required", "finance_reviewed"}


@dataclass(frozen=True, slots=True)
class CorpusCaseSpec:
    case_id: str
    category: str
    reviewer_status: str
    reviewer_rationale: str | None = None
    reviewed_at: date | None = None
    reviewer_role: str | None = None


def load_case_specs(path: Path) -> tuple[CorpusCaseSpec, ...]:
    payload = json.loads(path.read_text())
    if payload["case_set_version"] not in SUPPORTED_CASE_SET_VERSIONS:
        raise ValueError("unsupported case-set version")
    specs: list[CorpusCaseSpec] = []
    for item in payload["cases"]:
        category = item["category"]
        status = item["reviewer_status"]
        rationale = item.get("reviewer_rationale") or payload.get(
            "default_reviewer_rationale"
        )
        reviewed_at = (
            date.fromisoformat(item["reviewed_at"])
            if item.get("reviewed_at")
            else None
        )
        reviewer_role = item.get("reviewer_role")
        if category == "judgment":
            if status not in JUDGMENT_REVIEW_STATUSES:
                raise ValueError("judgment cases have an unsupported review status")
            if not rationale:
                raise ValueError("judgment cases require a review rationale")
            if status == "finance_reviewed" and (reviewed_at is None or not reviewer_role):
                raise ValueError("finance_reviewed cases require date and reviewer role")
            if status == "not_required" and (reviewed_at is not None or reviewer_role):
                raise ValueError("not_required cases cannot claim reviewer provenance")
        specs.append(
            CorpusCaseSpec(
                case_id=item["case_id"],
                category=category,
                reviewer_status=status,
                reviewer_rationale=rationale,
                reviewed_at=reviewed_at,
                reviewer_role=reviewer_role,
            )
        )
    specs = tuple(specs)
    if len({spec.case_id for spec in specs}) != len(specs):
        raise ValueError("case IDs must be unique")
    categories = {spec.category for spec in specs}
    if len(categories) != 1 or not categories.issubset(REQUIRED_CASE_COUNTS):
        raise ValueError("a case-set file must contain one supported category")
    category = next(iter(categories))
    if len(specs) != REQUIRED_CASE_COUNTS[category]:
        raise ValueError(
            f"{category} case-set must contain exactly {REQUIRED_CASE_COUNTS[category]} cases"
        )
    return specs


def case_from_json(*, item: dict, snapshot) -> RegressionCase:
    claim_data = item.get("claim")
    claim = None
    if claim_data is not None:
        relation = Relation(claim_data["relation"])
    if claim_data is not None and claim_data["type"] == "threshold":
        claim = MetricThresholdClaim(
            claim_id=claim_data["claim_id"], cited_evidence_id=claim_data["cited_evidence_id"],
            relation=relation, threshold=Decimal(claim_data["threshold"]),
        )
    elif claim_data is not None and claim_data["type"] == "comparison":
        claim = MetricComparisonClaim(
            claim_id=claim_data["claim_id"], left_evidence_id=claim_data["left_evidence_id"],
            relation=relation, right_evidence_id=claim_data["right_evidence_id"],
        )
    elif claim_data is not None and claim_data["type"] == "baseline":
        calibration = build_upper_baseline_calibration(
            snapshot=snapshot,
            historical_evidence_ids=tuple(claim_data["historical_evidence_ids"]),
            historical_cutoff=date.fromisoformat(claim_data["historical_cutoff"]),
            method=CalibrationMethod(claim_data.get("calibration_method", "historical_range")),
        )
        claim = MetricBaselineClaim(
            claim_id=claim_data["claim_id"],
            cited_evidence_id=claim_data["cited_evidence_id"],
            relation=relation,
            calibration=calibration,
        )
    elif claim_data is not None:
        raise ValueError("unsupported claim type")
    report = item["report_text"]
    fragment = item.get("claim_fragment", report)
    classification = StatementClassification(
        item.get("expected_classification", "classified")
    )
    extraction = ExtractionResult(
        extractor_version="gold-v1",
        statements=(ExtractedStatement(
            statement_id="s1", classification=classification,
            report_span=ReportSpan("span-s1", report, 0, len(report), fragment, 0, len(fragment)),
            claims=(claim,) if claim is not None else (),
        ),),
    )
    if claim is None and item.get("disclosure_assessments"):
        raise ValueError("unclassified cases cannot contain disclosure assessments")
    assessments = tuple(
        DisclosureAssessment(claim_id=claim.claim_id, defeating_evidence_id=value["evidence_id"], status=DisclosureStatus(value["status"]))
        for value in item.get("disclosure_assessments", [])
    )
    return RegressionCase(
        case_id=item["case_id"], category=item["category"], report_text=report,
        snapshot=snapshot, extraction=extraction, disclosure_assessments=assessments,
        expected_verdicts=(
            ((claim.claim_id, ClaimVerdict(item["expected_verdict"])),)
            if claim is not None
            else ()
        ),
        expected_unclassified_statement_ids=(
            ("s1",) if classification is StatementClassification.UNCLASSIFIED else ()
        ),
    )
