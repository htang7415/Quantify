"""Provider-neutral boundary for nondeterministic disclosure assessment."""

from __future__ import annotations

from typing import Protocol

from quantify.engine import CounterevidencePair, DisclosureAssessment


class DisclosureDetector(Protocol):
    def assess(
        self, *, report_text: str, counterevidence_pairs: tuple[CounterevidencePair, ...]
    ) -> tuple[DisclosureAssessment, ...]: ...
