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
from .disclosure import DisclosureDetector
from .snapshots import SnapshotBuild, build_revenue_snapshot
from .verification_cache import VerificationCache
from .observability import RequestMetrics, append_jsonl
from .coverage import EvidenceRequestType, assess_coverage

__all__ = [
    "ExtractedStatement",
    "ExtractionResult",
    "DisclosureDetector",
    "MaterialOmission",
    "ValidatedExtraction",
    "VerificationReport",
    "VerificationCache",
    "RequestMetrics",
    "append_jsonl",
    "EvidenceRequestType",
    "assess_coverage",
    "SnapshotBuild",
    "StructuredExtractor",
    "build_revenue_snapshot",
    "validate_claim_references",
    "validate_extraction",
    "validate_report_span",
    "verify_report",
]
