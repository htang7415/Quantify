"""Validation contracts for external extraction and disclosure components."""

from .grounding import validate_claim_references, validate_report_span

__all__ = ["validate_claim_references", "validate_report_span"]
