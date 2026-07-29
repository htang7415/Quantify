"""Provider-neutral boundary for nondeterministic disclosure assessment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quantify.engine import CounterevidencePair, DisclosureAssessment, EvidenceValue

from .extraction import TypedClaim


@dataclass(frozen=True, slots=True)
class DisclosureContext:
    """Evaluator-side context needed for a semantic disclosure decision."""

    claim: TypedClaim
    defeating_evidence: EvidenceValue


class DisclosureDetector(Protocol):
    def assess(
        self,
        *,
        report_text: str,
        counterevidence_pairs: tuple[CounterevidencePair, ...],
        contexts: tuple[DisclosureContext, ...],
    ) -> tuple[DisclosureAssessment, ...]: ...
