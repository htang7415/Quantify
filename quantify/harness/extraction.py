"""Structured extraction contracts and deterministic validation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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
MAX_PROPOSED_CLAIMS = 6


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
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ValidatedExtraction:
    claims: tuple[TypedClaim, ...]
    review_items: tuple[ReviewItem, ...]
    unclassified_statement_ids: tuple[str, ...]
    non_factual_statement_ids: tuple[str, ...]
    canonical_claim_source_spans: tuple[tuple[str, tuple[str, ...]], ...]


def _decimal_identity(value: Decimal) -> str:
    """Render numerically equivalent Decimal inputs as one semantic value."""

    return str(value.normalize())


def canonical_claim_identity(claim: TypedClaim) -> tuple[object, ...]:
    """Derive claim identity from semantics, never from the proposed claim ID."""

    if isinstance(claim, MetricThresholdClaim):
        return (
            "threshold",
            claim.cited_evidence_id,
            claim.relation.value,
            _decimal_identity(claim.threshold),
        )
    if isinstance(claim, MetricComparisonClaim):
        return (
            "comparison",
            claim.left_evidence_id,
            claim.relation.value,
            claim.right_evidence_id,
        )
    calibration = claim.calibration
    return (
        "baseline",
        claim.cited_evidence_id,
        claim.relation.value,
        calibration.method.value,
        tuple(sorted(calibration.historical_evidence_ids)),
        calibration.lookback_periods,
        calibration.historical_cutoff.isoformat(),
        _decimal_identity(calibration.upper_baseline),
        _decimal_identity(calibration.scale_value),
    )


def validate_extraction(
    *, report_text: str, snapshot: EvidenceSnapshot, extraction: ExtractionResult
) -> ValidatedExtraction:
    """Fail closed: invalid extraction is routed to review, never an accusation."""

    ids = [statement.statement_id for statement in extraction.statements]
    if len(ids) != len(set(ids)):
        raise ValueError("extraction statement IDs must be unique")

    candidates: list[tuple[TypedClaim, str]] = []
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
        if statement.classification is StatementClassification.REQUIRES_AGENT_RESOLUTION:
            reviews.append(
                ReviewItem(
                    statement_id=statement.statement_id,
                    reason=ReviewReason.EXTRACTION_SCHEMA_FAILURE,
                    message="Extraction routed this statement to agent resolution.",
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
                candidates.append((claim, statement.report_span.span_id))
            else:
                reviews.append(reference_review)

    identities_by_claim_id: dict[str, tuple[object, ...]] = {}
    for claim, _ in candidates:
        identity = canonical_claim_identity(claim)
        previous_identity = identities_by_claim_id.setdefault(claim.claim_id, identity)
        if previous_identity != identity:
            raise ValueError("one claim ID cannot name distinct claim semantics")
    grouped_candidates: dict[tuple[object, ...], list[tuple[TypedClaim, str]]] = {}
    for claim, span_id in candidates:
        grouped_candidates.setdefault(canonical_claim_identity(claim), []).append(
            (claim, span_id)
        )
    canonical_candidates = [
        min(group, key=lambda item: item[0].claim_id)
        for _, group in sorted(grouped_candidates.items(), key=lambda item: repr(item[0]))
    ]
    if len(canonical_candidates) > MAX_PROPOSED_CLAIMS:
        reviews.append(
            ReviewItem(
                statement_id="extraction-claim-limit",
                reason=ReviewReason.EXTRACTION_SCHEMA_FAILURE,
                message=(
                    f"Extraction proposed more than {MAX_PROPOSED_CLAIMS} "
                    "semantically distinct claims."
                ),
            )
        )
        canonical_candidates = []
        grouped_candidates = {}
    claims = tuple(sorted((claim for claim, _ in canonical_candidates), key=lambda claim: claim.claim_id))
    source_spans_by_claim = {
        min(group, key=lambda item: item[0].claim_id)[0].claim_id: tuple(
            sorted({span_id for _, span_id in group})
        )
        for group in grouped_candidates.values()
    }
    return ValidatedExtraction(
        claims=claims,
        review_items=tuple(sorted(reviews, key=lambda item: item.statement_id)),
        unclassified_statement_ids=tuple(unclassified),
        non_factual_statement_ids=tuple(non_factual),
        canonical_claim_source_spans=tuple(sorted(source_spans_by_claim.items())),
    )
