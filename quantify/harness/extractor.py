"""Provider-neutral boundary for one structured extraction call."""

from __future__ import annotations

from typing import Protocol

from quantify.engine import EvidenceSnapshot

from .extraction import ExtractionResult


class StructuredExtractor(Protocol):
    """Implementations may call a model, but return only frozen schema data."""

    def extract(self, *, report_text: str, snapshot: EvidenceSnapshot) -> ExtractionResult:
        """Return a schema-conformant candidate extraction for harness validation."""
