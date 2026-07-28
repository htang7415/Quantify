"""Fail-safe grounding validation for externally extracted claims."""

from __future__ import annotations

import re

from quantify.engine.schemas import (
    EvidenceSnapshot,
    MetricComparisonClaim,
    MetricThresholdClaim,
    ReportSpan,
    ReviewItem,
    ReviewReason,
)


CONTRASTIVE_MARKERS = (
    "but",
    "however",
    "although",
    "though",
    "while",
    "despite",
    "nevertheless",
    "yet",
)


def validate_report_span(*, report_text: str, span: ReportSpan) -> ReviewItem | None:
    """Return a review item unless sentence and fragment offsets exactly match."""

    sentence_matches = (
        0 <= span.sentence_start <= span.sentence_end <= len(report_text)
        and report_text[span.sentence_start : span.sentence_end] == span.sentence_text
    )
    fragment_matches = (
        0 <= span.fragment_start <= span.fragment_end <= len(report_text)
        and report_text[span.fragment_start : span.fragment_end] == span.claim_fragment
        and span.sentence_start <= span.fragment_start
        and span.fragment_end <= span.sentence_end
        and span.claim_fragment in span.sentence_text
    )
    if not sentence_matches or not fragment_matches:
        return ReviewItem(
            statement_id=span.span_id,
            reason=ReviewReason.REPORT_SPAN_NOT_GROUNDED,
            message="Extracted sentence or claim fragment does not match report offsets.",
            report_span_ids=(span.span_id,),
        )

    markers = span.contrastive_markers or tuple(
        marker
        for marker in CONTRASTIVE_MARKERS
        if re.search(rf"\b{re.escape(marker)}\b", span.sentence_text, re.IGNORECASE)
    )
    if markers and span.claim_fragment != span.sentence_text:
        return ReviewItem(
            statement_id=span.span_id,
            reason=ReviewReason.PARTIAL_CONTRASTIVE_EXTRACTION,
            message="A partial claim was extracted from a contrastive sentence.",
            report_span_ids=(span.span_id,),
        )
    return None


def validate_claim_references(
    *,
    snapshot: EvidenceSnapshot,
    claim: MetricThresholdClaim | MetricComparisonClaim,
) -> ReviewItem | None:
    """Route missing cited evidence IDs to review before engine analysis."""

    missing = tuple(
        evidence_id
        for evidence_id in claim.cited_evidence_ids
        if snapshot.evidence_by_id(evidence_id) is None
    )
    if not missing:
        return None
    return ReviewItem(
        statement_id=claim.claim_id,
        reason=ReviewReason.INVALID_EVIDENCE_REFERENCE,
        message="Claim cites evidence that is absent from the frozen snapshot.",
        claim_id=claim.claim_id,
        evidence_ids=missing,
    )
