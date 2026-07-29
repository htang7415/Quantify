"""Application service that composes SEC evidence, extraction, and verification."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date
from time import perf_counter
from typing import Callable, Protocol

from quantify.api import VerifyRequest
from quantify.engine import ClaimVerdict, EvidenceSnapshot
from quantify.harness import (
    DisclosureDetector,
    RequestMetrics,
    SnapshotBuild,
    StructuredExtractor,
    VerificationCache,
    VerificationReport,
    verify_report,
)


class SnapshotProvider(Protocol):
    def build(
        self, *, cik: str, as_of_date: date, forms: tuple[str, ...]
    ) -> SnapshotBuild: ...


class _TimedDisclosureDetector:
    def __init__(
        self, detector: DisclosureDetector, clock: Callable[[], float]
    ) -> None:
        self._detector = detector
        self._clock = clock
        self.elapsed_seconds = 0.0

    def assess(self, **kwargs):  # type: ignore[no-untyped-def]
        started_at = self._clock()
        try:
            return self._detector.assess(**kwargs)
        finally:
            self.elapsed_seconds += self._clock() - started_at


class ApplicationService:
    """The minimal V1 service; adapters are injected and engine policy is fixed."""

    def __init__(
        self,
        verify: Callable[..., dict] | None = None,
        *,
        snapshot_provider: SnapshotProvider | None = None,
        extractor: StructuredExtractor | None = None,
        disclosure_detector: DisclosureDetector | None = None,
        verification_cache: VerificationCache[dict] | None = None,
        metrics_sink: Callable[[RequestMetrics], None] | None = None,
        extraction_model: str = "unconfigured",
        prompt_hash: str | None = None,
        temperature: float | None = None,
        disclosure_detector_version: str = "unconfigured",
        clock: Callable[[], float] = perf_counter,
        sec_network_call_count: Callable[[], int] | None = None,
    ) -> None:
        if verify is not None and (snapshot_provider is not None or extractor is not None):
            raise ValueError("legacy verify callback cannot be combined with V1 adapters")
        if verify is None and (snapshot_provider is None or extractor is None):
            raise ValueError("V1 service requires a snapshot provider and extractor")
        self._legacy_verify = verify
        self._snapshot_provider = snapshot_provider
        self._extractor = extractor
        self._disclosure_detector = disclosure_detector
        self._cache = verification_cache or VerificationCache()
        self._metrics_sink = metrics_sink
        self._extraction_model = extraction_model
        self._prompt_hash = prompt_hash
        self._temperature = temperature
        self._disclosure_detector_version = disclosure_detector_version
        self._clock = clock
        self._sec_network_call_count = sec_network_call_count

    def verify(self, *, cik: str, request: VerifyRequest) -> dict:
        if self._legacy_verify is not None:
            return self._legacy_verify(
                cik=cik,
                analysis=request.analysis,
                as_of_date=request.as_of_date,
                forms=request.forms,
            )

        assert self._snapshot_provider is not None
        assert self._extractor is not None
        started_at = self._clock()
        network_calls_before = self._network_call_count()
        build = self._snapshot_provider.build(
            cik=cik, as_of_date=request.as_of_date, forms=request.forms
        )
        network_calls = self._network_call_count() - network_calls_before
        audit_manifest = replace(
            build.audit_manifest,
            extraction_model=self._extraction_model,
            prompt_hash=self._prompt_hash,
            temperature=self._temperature,
            disclosure_detector_version=self._disclosure_detector_version,
        )
        cache_key = self._cache.key(
            report_text=request.analysis,
            snapshot_manifest_hash=build.snapshot.manifest_hash,
            replay_manifest_hash=audit_manifest.manifest_hash,
        )
        extraction_elapsed = 0.0
        disclosure_elapsed = 0.0
        input_tokens = 0
        output_tokens = 0
        total_cost = 0.0

        def compute() -> dict:
            nonlocal extraction_elapsed, disclosure_elapsed
            nonlocal input_tokens, output_tokens, total_cost
            extraction_started_at = self._clock()
            extraction = self._extractor.extract(
                report_text=request.analysis, snapshot=build.snapshot
            )
            extraction_elapsed = self._clock() - extraction_started_at
            input_tokens = extraction.input_tokens
            output_tokens = extraction.output_tokens
            total_cost = extraction.total_cost
            timed_detector = (
                _TimedDisclosureDetector(self._disclosure_detector, self._clock)
                if self._disclosure_detector is not None
                else None
            )
            report = verify_report(
                report_text=request.analysis,
                snapshot=build.snapshot,
                extraction=extraction,
                disclosure_detector=timed_detector,
            )
            disclosure_elapsed = timed_detector.elapsed_seconds if timed_detector else 0.0
            return self._response(
                report=report,
                snapshot=build.snapshot,
                audit_manifest=audit_manifest,
                forms=request.forms,
            )

        response, verification_cache_hit = self._cache.get_or_compute(
            key=cache_key, compute=compute
        )
        response = {**response, "verification_cache_hit": verification_cache_hit}
        self._emit_metrics(
            response=response,
            build=build,
            network_calls=network_calls,
            verification_cache_hit=verification_cache_hit,
            extraction_elapsed=extraction_elapsed,
            disclosure_elapsed=disclosure_elapsed,
            verification_elapsed=self._clock() - started_at,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_cost=total_cost,
        )
        return response

    def _network_call_count(self) -> int:
        return self._sec_network_call_count() if self._sec_network_call_count else 0

    def _emit_metrics(
        self,
        *,
        response: dict,
        build: SnapshotBuild,
        network_calls: int,
        verification_cache_hit: bool,
        extraction_elapsed: float,
        disclosure_elapsed: float,
        verification_elapsed: float,
        input_tokens: int,
        output_tokens: int,
        total_cost: float,
    ) -> None:
        if self._metrics_sink is None:
            return
        verdicts = [item["verdict"] for item in response["claim_results"]]
        self._metrics_sink(
            RequestMetrics(
                cache_hit=build.audit_manifest.cache_hit,
                sec_network_calls=network_calls,
                filings_selected=len(build.audit_manifest.resolved_filing_accessions),
                evidence_count=len(build.snapshot.evidence),
                eligible_evidence_count=sum(
                    item.eligible for item in build.snapshot.evidence
                ),
                rejected_evidence_count=sum(
                    not item.eligible for item in build.snapshot.evidence
                ),
                verified_count=verdicts.count(ClaimVerdict.VERIFIED.value),
                unsupported_count=verdicts.count(ClaimVerdict.UNSUPPORTED.value),
                defeated_count=verdicts.count(ClaimVerdict.DEFEATED.value),
                qualified_count=verdicts.count(ClaimVerdict.QUALIFIED.value),
                human_review_count=(
                    verdicts.count(ClaimVerdict.REQUIRES_HUMAN_REVIEW.value)
                    + len(response["review_items"])
                ),
                empty_result=not response["claim_results"],
                total_cost=total_cost,
                llm_input_tokens=input_tokens,
                llm_output_tokens=output_tokens,
                extraction_latency_seconds=extraction_elapsed,
                disclosure_latency_seconds=disclosure_elapsed,
                verification_latency_seconds=verification_elapsed,
                verification_cache_hit=verification_cache_hit,
            )
        )

    @staticmethod
    def _response(
        *,
        report: VerificationReport,
        snapshot: EvidenceSnapshot,
        audit_manifest,
        forms: tuple[str, ...],
    ) -> dict:
        audit = asdict(audit_manifest)
        audit["analysis_as_of_date"] = audit_manifest.analysis_as_of_date.isoformat()
        audit["manifest_hash"] = audit_manifest.manifest_hash
        claim_results = [
            {
                "claim_id": verdict.claim_id,
                "verdict": verdict.verdict.value,
                "counterevidence_detail": [
                    {
                        "evidence_id": detail.evidence_id,
                        "disclosure_status": detail.disclosure_status.value,
                        "report_span_ids": list(detail.report_span_ids),
                    }
                    for detail in verdict.counterevidence_detail
                ],
            }
            for verdict in report.claim_verdicts
        ]
        return {
            "claim_results": claim_results,
            "unclassified_statements": list(report.unclassified_statement_ids),
            "non_factual_statements": list(report.non_factual_statement_ids),
            "review_items": [
                {
                    "statement_id": item.statement_id,
                    "reason": item.reason.value,
                    "message": item.message,
                    "report_span_ids": list(item.report_span_ids),
                    "claim_id": item.claim_id,
                    "evidence_ids": list(item.evidence_ids),
                }
                for item in report.review_items
            ],
            "counterevidence_detail": [
                {"claim_id": verdict["claim_id"], **detail}
                for verdict in claim_results
                for detail in verdict["counterevidence_detail"]
            ],
            "material_omissions": [
                {"claim_id": omission.claim_id, "evidence_id": omission.evidence_id}
                for omission in report.material_omissions
            ],
            "temporal_persistence": [],
            "evidence_scope": {
                "source": "SEC EDGAR",
                "forms": list(forms),
                "entity_level_only": True,
                "snapshot_manifest_hash": snapshot.manifest_hash,
            },
            "audit_manifest": audit,
        }
