"""Validation contracts for external extraction and disclosure components."""

from .grounding import validate_claim_references, validate_report_span
from .extraction import (
    ExtractedStatement,
    ExtractionResult,
    ValidatedExtraction,
    validate_extraction,
)
from .orchestrator import MaterialOmission, VerificationReport, verify_report
from .extractor import StructuredExtractor
from .snapshots import SnapshotBuild, build_revenue_snapshot

__all__ = [
    "ExtractedStatement",
    "ExtractionResult",
    "MaterialOmission",
    "ValidatedExtraction",
    "VerificationReport",
    "SnapshotBuild",
    "StructuredExtractor",
    "build_revenue_snapshot",
    "validate_claim_references",
    "validate_extraction",
    "validate_report_span",
    "verify_report",
]
