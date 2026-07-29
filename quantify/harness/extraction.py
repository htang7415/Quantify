"""Structured extraction contracts and deterministic validation."""

from __future__ import annotations

from dataclasses import dataclass

from quantify.engine.schemas import (
    EvidenceSnapshot,
    MetricBaselineClaim,
    MetricComparisonClaim,
    MetricThresholdClaim,
    ReportSpan,
    ReviewItem,
    ReviewReason,
    StatementClassification,
)

from .grounding import validate_claim_references, validate_report_span

TypedClaim = MetricThresholdClaim | MetricComparisonClaim | MetricBaselineClaim


@dataclass(frozen=True, slots=True)
class ExtractedStatement:
    statement_id: str
    classification: StatementClassification
    report_span: ReportSpan
    claims: tuple[TypedClaim, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Provider-neutral structured output supplied to the harness."""

    statements: tuple[ExtractedStatement, ...]
    extractor_version: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0


@dataclass(frozen=True, slots=True)
class ValidatedExtraction:
    claims: tuple[TypedClaim, ...]
    review_items: tuple[ReviewItem, ...]
    unclassified_statement_ids: tuple[str, ...]
    non_factual_statement_ids: tuple[str, ...]


def validate_extraction(
    *, report_text: str, snapshot: EvidenceSnapshot, extraction: ExtractionResult
) -> ValidatedExtraction:
    """Fail closed: invalid extraction is routed to review, never an accusation."""

    ids = [statement.statement_id for statement in extraction.statements]
    if len(ids) != len(set(ids)):
        raise ValueError("extraction statement IDs must be unique")

    claims: list[TypedClaim] = []
    reviews: list[ReviewItem] = []
    unclassified: list[str] = []
    non_factual: list[str] = []
    for statement in sorted(extraction.statements, key=lambda item: item.statement_id):
        grounding_review = validate_report_span(
            report_text=report_text, span=statement.report_span
        )
        if grounding_review is not None:
            reviews.append(grounding_review)
            continue
        if statement.classification is StatementClassification.UNCLASSIFIED:
            unclassified.append(statement.statement_id)
            continue
        if statement.classification is StatementClassification.NON_FACTUAL:
            non_factual.append(statement.statement_id)
            continue
        if statement.classification is StatementClassification.REQUIRES_HUMAN_REVIEW:
            reviews.append(
                ReviewItem(
                    statement_id=statement.statement_id,
                    reason=ReviewReason.EXTRACTION_SCHEMA_FAILURE,
                    message="Extraction routed this statement to human review.",
                    report_span_ids=(statement.report_span.span_id,),
                )
            )
            continue
        if not statement.claims:
            reviews.append(
                ReviewItem(
                    statement_id=statement.statement_id,
                    reason=ReviewReason.EXTRACTION_SCHEMA_FAILURE,
                    message="A classified statement did not include a typed claim.",
                    report_span_ids=(statement.report_span.span_id,),
                )
            )
            continue
        for claim in statement.claims:
            reference_review = validate_claim_references(snapshot=snapshot, claim=claim)
            if reference_review is None:
                claims.append(claim)
            else:
                reviews.append(reference_review)

    claim_ids = [claim.claim_id for claim in claims]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("validated claim IDs must be unique")
    return ValidatedExtraction(
        claims=tuple(sorted(claims, key=lambda claim: claim.claim_id)),
        review_items=tuple(sorted(reviews, key=lambda item: item.statement_id)),
        unclassified_statement_ids=tuple(unclassified),
        non_factual_statement_ids=tuple(non_factual),
    )
