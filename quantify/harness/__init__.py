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
from .disclosure import DisclosureContext, DisclosureDetector
from .snapshots import SnapshotBuild, build_revenue_snapshot, build_sec_snapshot
from .verification_cache import VerificationCache
from .observability import (
    OBSERVABILITY_SCHEMA_VERSION,
    RequestMetrics,
    append_jsonl,
    export_jsonl_to_parquet,
)
from .coverage import EvidenceRequestType, assess_coverage
from .acquisition import EvidenceAcquisitionRecord, approve_acquisition_requests
from .resolution import (
    AgentResolutionAction,
    AgentResolutionOutcome,
    AgentResolutionRecord,
    AutonomousResolutionLoop,
)
from .gemini import (
    GeminiDisclosureConfig,
    GeminiDisclosureDetector,
    GeminiExtractionConfig,
    GeminiStructuredExtractor,
)

__all__ = [
    "ExtractedStatement",
    "ExtractionResult",
    "DisclosureDetector",
    "DisclosureContext",
    "MaterialOmission",
    "ValidatedExtraction",
    "VerificationReport",
    "VerificationCache",
    "RequestMetrics",
    "OBSERVABILITY_SCHEMA_VERSION",
    "append_jsonl",
    "export_jsonl_to_parquet",
    "EvidenceRequestType",
    "assess_coverage",
    "SnapshotBuild",
    "EvidenceAcquisitionRecord",
    "StructuredExtractor",
    "build_revenue_snapshot",
    "build_sec_snapshot",
    "approve_acquisition_requests",
    "AgentResolutionAction",
    "AgentResolutionOutcome",
    "AgentResolutionRecord",
    "AutonomousResolutionLoop",
    "GeminiExtractionConfig",
    "GeminiStructuredExtractor",
    "GeminiDisclosureConfig",
    "GeminiDisclosureDetector",
    "validate_claim_references",
    "validate_extraction",
    "validate_report_span",
    "verify_report",
]
