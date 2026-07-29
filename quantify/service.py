"""Application service that composes SEC evidence, extraction, and verification."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date
from collections import Counter
from time import perf_counter
from typing import Callable, Protocol

from quantify.api import VerifyRequest
from quantify.engine import ClaimVerdict, EvidenceSnapshot
from quantify.harness import (
    DisclosureDetector,
    AutonomousResolutionLoop,
    RequestMetrics,
    SnapshotBuild,
    StructuredExtractor,
    VerificationCache,
    VerificationReport,
    approve_acquisition_requests,
    assess_coverage,
)
from quantify.runtime import ModelUnavailableError


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
        agent_resolution_loop: AutonomousResolutionLoop | None = None,
        clock: Callable[[], float] = perf_counter,
        sec_network_call_count: Callable[[], int] | None = None,
        evidence_fixture_manifest_hash: str | None = None,
        deployment_image_digest: str | None = None,
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
        self._agent_resolution_loop = agent_resolution_loop or AutonomousResolutionLoop()
        self._clock = clock
        self._sec_network_call_count = sec_network_call_count
        self._evidence_fixture_manifest_hash = evidence_fixture_manifest_hash
        self._deployment_image_digest = deployment_image_digest

    def verify(self, *, cik: str, request: VerifyRequest) -> dict:
        return self._verify(cik=cik, request=request, batch_size=1)

    def verify_batch(
        self, *, items: tuple[tuple[str, VerifyRequest], ...]
    ) -> tuple[dict, ...]:
        """Verify independent requests in canonical order with isolated errors."""

        batch_size = len(items)
        results: list[dict] = []
        for cik, request in sorted(
            items,
            key=lambda item: (
                item[0],
                item[1].analysis,
                item[1].as_of_date,
                item[1].forms,
                item[1].evidence_requests,
            ),
        ):
            try:
                results.append(
                    {
                        "cik": cik,
                        "result": self._verify(
                            cik=cik, request=request, batch_size=batch_size
                        ),
                    }
                )
            except ValueError as error:
                results.append(
                    {
                        "cik": cik,
                        "error": {"type": "invalid_request", "message": str(error)},
                    }
                )
        return tuple(results)

    def review(self, *, cik: str, request: VerifyRequest) -> dict:
        """Compatibility alias for the former review endpoint."""

        return self.resolve(cik=cik, request=request)

    def resolve(self, *, cik: str, request: VerifyRequest) -> dict:
        """Return a deterministic agent-resolution queue without changing verification."""

        response = self.verify(cik=cik, request=request)
        return {
            "agent_resolution_queue": response["agent_resolution_queue"],
            "review_queue": response["review_queue"],
            "audit_manifest": response["audit_manifest"],
            "verification_cache_hit": response["verification_cache_hit"],
        }

    def _verify(
        self, *, cik: str, request: VerifyRequest, batch_size: int
    ) -> dict:
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
        acquisition_records = approve_acquisition_requests(
            snapshot=build.snapshot, requested=request.evidence_requests
        )
        if acquisition_records:
            build = self._snapshot_provider.build(
                cik=cik,
                as_of_date=request.as_of_date,
                forms=request.forms,
                acquisition_records=acquisition_records,
            )
            still_uncovered = set(assess_coverage(snapshot=build.snapshot))
            if any(
                record.request_type in still_uncovered
                for record in acquisition_records
            ):
                raise ValueError("evidence acquisition did not improve the requested coverage")
        network_calls = self._network_call_count() - network_calls_before
        audit_manifest = replace(
            build.audit_manifest,
            extraction_model=self._extraction_model,
            prompt_hash=self._prompt_hash,
            temperature=self._temperature,
            disclosure_detector_version=self._disclosure_detector_version,
            evidence_fixture_manifest_hash=self._evidence_fixture_manifest_hash,
            deployment_image_digest=self._deployment_image_digest,
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
            if extraction.failure_reason == "transport_failure":
                raise ModelUnavailableError(
                    "The pinned Gemini extraction contract is unavailable."
                )
            input_tokens = extraction.input_tokens
            output_tokens = extraction.output_tokens
            total_cost = extraction.total_cost
            timed_detector = (
                _TimedDisclosureDetector(self._disclosure_detector, self._clock)
                if self._disclosure_detector is not None
                else None
            )
            resolution = self._agent_resolution_loop.resolve(
                report_text=request.analysis,
                snapshot=build.snapshot,
                extraction=extraction,
                disclosure_detector=timed_detector,
            )
            disclosure_elapsed = timed_detector.elapsed_seconds if timed_detector else 0.0
            resolved_audit_manifest = replace(
                audit_manifest,
                agent_resolution_policy_version=self._agent_resolution_loop.policy_version,
                agent_resolution_records=tuple(
                    record.manifest_entry() for record in resolution.records
                ),
                canonical_claim_source_spans=resolution.report.canonical_claim_source_spans,
            )
            return self._response(
                report=resolution.report,
                snapshot=build.snapshot,
                audit_manifest=resolved_audit_manifest,
                forms=build.audit_manifest.requested_forms,
                extraction=extraction,
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
            batch_size=batch_size,
            cik=cik,
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
        batch_size: int,
        cik: str,
    ) -> None:
        if self._metrics_sink is None:
            return
        verdicts = [item["verdict"] for item in response["claim_results"]]
        statement_counts = response["statement_counts"]
        total_statements = sum(statement_counts.values())
        reason_counts = Counter(
            decision.reason.value
            for decision in build.selection.eligibility_decisions
            if decision.reason.value != "eligible"
        )
        action_outcomes = [
            outcome
            for _, outcome in response["audit_manifest"]["agent_resolution_records"]
        ]
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
                agent_resolution_count=(
                    verdicts.count(ClaimVerdict.REQUIRES_AGENT_RESOLUTION.value)
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
                acquisition_rounds=len(build.audit_manifest.acquisition_records),
                acquisition_request_types=tuple(
                    request_type
                    for request_type, _ in build.audit_manifest.acquisition_records
                ),
                agent_resolution_queue_count=len(response["agent_resolution_queue"]),
                batch_size=batch_size,
                company_cik=cik,
                rejected_evidence_reasons=tuple(sorted(reason_counts.items())),
                classified_statement_count=statement_counts["classified"],
                unclassified_statement_count=statement_counts["unclassified"],
                non_factual_statement_count=statement_counts["non_factual"],
                classified_fraction=(
                    statement_counts["classified"] / total_statements
                    if total_statements
                    else 0.0
                ),
                unclassified_fraction=(
                    statement_counts["unclassified"] / total_statements
                    if total_statements
                    else 0.0
                ),
                agent_resolution_action_count=len(action_outcomes),
                agent_resolution_resolved_count=sum(
                    outcome.endswith(":resolved") for outcome in action_outcomes
                ),
                agent_resolution_unresolved_count=sum(
                    outcome.endswith(":unresolved") for outcome in action_outcomes
                ),
            )
        )

    @staticmethod
    def _response(
        *,
        report: VerificationReport,
        snapshot: EvidenceSnapshot,
        audit_manifest,
        forms: tuple[str, ...],
        extraction,
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
        response = {
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
            "temporal_persistence": [
                {
                    "metric_name": item.metric_name,
                    "consecutive_periods": item.consecutive_periods,
                    "direction": item.direction.value,
                    "period_ids": list(item.period_ids),
                }
                for item in report.temporal_persistence
            ],
            "evidence_scope": {
                "source": "SEC EDGAR",
                "forms": list(forms),
                "entity_level_only": True,
                "snapshot_manifest_hash": snapshot.manifest_hash,
            },
            "audit_manifest": audit,
            "statement_counts": {
                "classified": sum(
                    item.classification.value == "classified"
                    for item in extraction.statements
                ),
                "unclassified": sum(
                    item.classification.value == "unclassified"
                    for item in extraction.statements
                ),
                "non_factual": sum(
                    item.classification.value == "non_factual"
                    for item in extraction.statements
                ),
                "requires_agent_resolution": sum(
                    item.classification.value == "requires_agent_resolution"
                    for item in extraction.statements
                ),
            },
        }
        response["agent_resolution_queue"] = ApplicationService._agent_resolution_queue(
            response
        )
        # Retain the V1 field until clients move to agent_resolution_queue.
        response["review_queue"] = response["agent_resolution_queue"]
        span_by_owner = {}
        for statement in extraction.statements:
            span = statement.report_span
            serialized_span = {
                "span_id": span.span_id,
                "sentence_text": span.sentence_text,
                "sentence_start": span.sentence_start,
                "sentence_end": span.sentence_end,
                "claim_fragment": span.claim_fragment,
                "fragment_start": span.fragment_start,
                "fragment_end": span.fragment_end,
            }
            span_by_owner[statement.statement_id] = serialized_span
            span_by_owner[span.span_id] = serialized_span
            for claim in statement.claims:
                span_by_owner[claim.claim_id] = serialized_span
        for queue_item in response["agent_resolution_queue"]:
            owner = queue_item["claim_id"] or queue_item["statement_id"]
            span = span_by_owner.get(owner)
            queue_item["report_spans"] = [span] if span is not None else []
        return response

    @staticmethod
    def _agent_resolution_queue(response: dict) -> list[dict]:
        """Project review items into agent actions and linked evidence details."""

        counterevidence_by_claim: dict[str, list[dict]] = {}
        for detail in response["counterevidence_detail"]:
            counterevidence_by_claim.setdefault(detail["claim_id"], []).append(detail)
        actions = {
            "disclosure_ambiguous": "assess_disclosure",
            "missing_disclosure_assessment": "assess_disclosure",
            "report_span_not_grounded": "correct_grounding",
            "partial_contrastive_extraction": "extract_full_contrastive_sentence",
            "invalid_evidence_reference": "correct_evidence_reference",
            "extraction_schema_failure": "repair_extraction",
        }
        return [
            {
                "statement_id": item["statement_id"],
                "reason": item["reason"],
                "required_action": actions.get(item["reason"], "review"),
                "message": item["message"],
                "claim_id": item["claim_id"],
                "report_span_ids": item["report_span_ids"],
                "evidence_ids": item["evidence_ids"],
                "counterevidence": counterevidence_by_claim.get(
                    item["claim_id"], []
                ),
            }
            for item in response["review_items"]
        ]
