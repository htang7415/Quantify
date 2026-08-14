from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import json
from pathlib import Path

import pytest

from quantify.api import VerifyRequest
from quantify.engine import (
    MetricComparisonClaim,
    Relation,
    ReportSpan,
    StatementClassification,
)
from quantify.harness import ExtractedStatement, ExtractionResult
from quantify.harness.acquisition import approve_acquisition_requests
from quantify.harness.coverage import EvidenceRequestType
from quantify.indexed_release import (
    ExactFactKey,
    IndexedReleaseError,
    IndexedSnapshot,
    IndexedSnapshotProvider,
    IndexedSnapshotRequest,
    NarrativeContextRetriever,
    NarrativeDisclosureChunk,
    compile_indexed_release,
)
from quantify.indexed_release_archive import IndexedReleaseArchive, S3IndexedReleaseArchiveStore
from quantify.production import EmbeddedSecSnapshotProvider, validate_embedded_sec_fixtures
from quantify.release_factory import build_evidence_release
from quantify.service import ApplicationService


FIXTURES_DIRECTORY = Path(__file__).parents[1] / "fixtures" / "sec"


def _v1_release():
    declaration = json.loads((FIXTURES_DIRECTORY / "release_v1.json").read_text())
    return build_evidence_release(
        fixtures_directory=FIXTURES_DIRECTORY,
        release_id=declaration["release_id"],
        issuer_ciks=tuple(declaration["issuer_ciks"]),
        evaluation_corpus=FIXTURES_DIRECTORY / declaration["evaluation_corpus"],
        source_policy_version=declaration["source_policy_version"],
        eligibility_policy_version=declaration["eligibility_policy_version"],
        restatement_policy_version=declaration["restatement_policy_version"],
    )


def _compiled_msft_release(*, narrative_chunks=()):
    request = IndexedSnapshotRequest(
        cik="789019", as_of_date=date(2024, 7, 30), forms=("10-K",)
    )
    apple_request = IndexedSnapshotRequest(
        cik="320193", as_of_date=date(2024, 7, 30), forms=("10-K",)
    )
    embedded = EmbeddedSecSnapshotProvider(
        fixtures=validate_embedded_sec_fixtures(FIXTURES_DIRECTORY)
    )
    build = embedded.build(
        cik=request.cik, as_of_date=request.as_of_date, forms=request.forms
    )
    acquisition_records = approve_acquisition_requests(
        snapshot=build.snapshot,
        requested=(EvidenceRequestType.PROFITABILITY_METRICS,),
    )
    expanded_request = IndexedSnapshotRequest(
        cik=request.cik,
        as_of_date=request.as_of_date,
        forms=request.forms,
        acquisition_records=tuple(
            (record.request_type.value, record.reason) for record in acquisition_records
        ),
    )
    expanded_build = embedded.build(
        cik=expanded_request.cik,
        as_of_date=expanded_request.as_of_date,
        forms=expanded_request.forms,
        acquisition_records=acquisition_records,
    )
    apple_build = embedded.build(
        cik=apple_request.cik,
        as_of_date=apple_request.as_of_date,
        forms=apple_request.forms,
    )
    return compile_indexed_release(
        evidence_release=_v1_release(),
        snapshots=(
            IndexedSnapshot(request=request, build=build),
            IndexedSnapshot(request=expanded_request, build=expanded_build),
            IndexedSnapshot(request=apple_request, build=apple_build),
        ),
        narrative_chunks=narrative_chunks,
    ), embedded, request


class _MicrosoftGrowthExtractor:
    def extract(self, *, report_text: str, snapshot) -> ExtractionResult:
        previous = next(
            item
            for item in snapshot.evidence
            if item.metric == "revenue" and item.period_end == date(2023, 6, 30)
        )
        current = next(
            item
            for item in snapshot.evidence
            if item.metric == "revenue" and item.period_end == date(2024, 6, 30)
        )
        return ExtractionResult(
            extractor_version="indexed-release-replay-v1",
            statements=(
                ExtractedStatement(
                    statement_id="msft-growth",
                    classification=StatementClassification.CLASSIFIED,
                    report_span=ReportSpan(
                        span_id="msft-growth-span",
                        sentence_text=report_text,
                        sentence_start=0,
                        sentence_end=len(report_text),
                        claim_fragment=report_text,
                        fragment_start=0,
                        fragment_end=len(report_text),
                    ),
                    claims=(
                        MetricComparisonClaim(
                            claim_id="msft-revenue-growth",
                            left_evidence_id=current.evidence_id,
                            relation=Relation.GREATER_THAN,
                            right_evidence_id=previous.evidence_id,
                        ),
                    ),
                ),
            ),
        )


def test_compiler_builds_a_release_scoped_exact_fact_index_for_the_v1_release() -> None:
    indexed, _, _ = _compiled_msft_release()

    assert indexed.evidence_release.release_id == "sec-us-large-cap-v1"
    assert indexed.narrative_context.chunks == ()
    assert indexed.exact_facts.records
    assert {record.evidence.entity_cik for record in indexed.exact_facts.records} == {
        "0000320193",
        "0000789019",
    }
    record = next(
        item
        for item in indexed.exact_facts.records
        if item.evidence.metric == "revenue" and item.evidence.period_end == date(2024, 6, 30)
    )

    assert indexed.exact_facts.lookup(key=record.key) == record
    assert record.fact_id != record.evidence.evidence_id
    assert len(record.fact_id) == 64
    assert indexed.manifest_hash


def test_indexed_release_archive_replays_exact_snapshot_and_rejects_tampering() -> None:
    indexed, _, request = _compiled_msft_release()
    archive = IndexedReleaseArchive.dump(indexed)
    provider = IndexedReleaseArchive.load(archive)
    assert provider.build(cik=request.cik, as_of_date=request.as_of_date, forms=request.forms).snapshot.manifest_hash == indexed.snapshot_for(request=request).snapshot.manifest_hash
    tampered = archive.replace(b'"snapshot_manifest_hash":"', b'"snapshot_manifest_hash":"0', 1)
    with pytest.raises(IndexedReleaseError, match="archived"):
        IndexedReleaseArchive.load(tampered)
    malformed_index = json.loads(archive)
    malformed_index["exact_fact_index_hash"] = "0" * 64
    with pytest.raises(IndexedReleaseError, match="index hashes"):
        IndexedReleaseArchive.load(json.dumps(malformed_index).encode())


def test_s3_indexed_release_archive_store_is_encrypted_content_addressed_and_reloads() -> None:
    class _Body:
        def __init__(self, value): self.value=value
        def read(self): return self.value
    class _S3:
        def __init__(self): self.calls=[]; self.objects={}
        def put_object(self, **kwargs): self.calls.append(kwargs); self.objects[kwargs["Key"]]=kwargs["Body"]; return {}
        def get_object(self, **kwargs): return {"Body":_Body(self.objects[kwargs["Key"]])}
    indexed, _, request = _compiled_msft_release(); client=_S3(); store=S3IndexedReleaseArchiveStore(bucket_name="releases",client=client)
    manifest=store.persist(indexed)
    assert client.calls[0]["ServerSideEncryption"] == "aws:kms"
    assert store.load(evidence_release_manifest_hash=manifest).build(cik=request.cik,as_of_date=request.as_of_date,forms=request.forms).snapshot.manifest_hash == indexed.snapshot_for(request=request).snapshot.manifest_hash


def test_indexed_archive_rejects_an_existing_object_that_does_not_replay() -> None:
    class _Body:
        def __init__(self, value): self.value=value
        def read(self): return self.value
    class _S3:
        def __init__(self): self.objects={}
        def put_object(self, **kwargs):
            if kwargs["Key"] in self.objects:
                error = RuntimeError("already exists")
                error.response = {"Error": {"Code": "PreconditionFailed"}}  # type: ignore[attr-defined]
                raise error
            self.objects[kwargs["Key"]]=kwargs["Body"]
            return {}
        def get_object(self, **kwargs): return {"Body":_Body(self.objects[kwargs["Key"]])}
    indexed, _, _ = _compiled_msft_release()
    client = _S3()
    store = S3IndexedReleaseArchiveStore(bucket_name="releases", client=client)
    manifest = store.persist(indexed)
    key = f"evidence-releases/v1/{manifest}/indexed-release.json"
    client.objects[key] = b"{}"
    with pytest.raises(IndexedReleaseError, match="unavailable"):
        store.persist(indexed)


def test_exact_fact_lookup_fails_closed_for_any_non_exact_key_or_release() -> None:
    indexed, _, _ = _compiled_msft_release()
    record = indexed.exact_facts.records[0]

    assert indexed.exact_facts.lookup(key=replace(record.key, metric="not_a_metric")) is None
    assert indexed.exact_facts.lookup(key=replace(record.key, cik="0000000001")) is None
    assert indexed.exact_facts.lookup(
        key=replace(
            record.key,
            fiscal_period_end=record.key.fiscal_period_end + timedelta(days=1),
        )
    ) is None
    assert indexed.exact_facts.lookup(key=replace(record.key, unit="not_a_unit")) is None
    assert indexed.exact_facts.lookup(
        key=ExactFactKey(
            evidence_release_manifest_hash="f" * 64,
            cik=record.key.cik,
            metric=record.key.metric,
            fiscal_period_start=record.key.fiscal_period_start,
            fiscal_period_end=record.key.fiscal_period_end,
            unit=record.key.unit,
        )
    ) is None


def test_indexed_snapshot_adapter_has_embedded_provider_replay_parity() -> None:
    indexed, embedded, request = _compiled_msft_release()
    analysis = "Microsoft revenue increased from fiscal 2023 to fiscal 2024"
    verify_request = VerifyRequest(
        analysis=analysis, as_of_date=request.as_of_date, forms=request.forms
    )
    rebuilt = IndexedSnapshotProvider(indexed_release=indexed).build(
        cik=request.cik, as_of_date=request.as_of_date, forms=request.forms
    )
    embedded_build = embedded.build(
        cik=request.cik, as_of_date=request.as_of_date, forms=request.forms
    )
    assert rebuilt.snapshot is not embedded_build.snapshot
    assert rebuilt.snapshot.manifest_hash == embedded_build.snapshot.manifest_hash
    assert rebuilt.snapshot.evidence == embedded_build.snapshot.evidence

    embedded_response = ApplicationService(
        snapshot_provider=embedded,
        extractor=_MicrosoftGrowthExtractor(),
    ).verify(cik=request.cik, request=verify_request)
    indexed_response = ApplicationService(
        snapshot_provider=IndexedSnapshotProvider(indexed_release=indexed),
        extractor=_MicrosoftGrowthExtractor(),
    ).verify(cik=request.cik, request=verify_request)

    assert indexed_response == embedded_response
    assert indexed_response["claim_results"] == [
        {
            "claim_id": "msft-revenue-growth",
            "verdict": "verified",
            "counterevidence_detail": [],
        }
    ]


def test_indexed_snapshot_adapter_replays_the_existing_evidence_acquisition_path() -> None:
    indexed, embedded, request = _compiled_msft_release()
    analysis = "Microsoft revenue increased from fiscal 2023 to fiscal 2024"
    verify_request = VerifyRequest(
        analysis=analysis,
        as_of_date=request.as_of_date,
        forms=request.forms,
        evidence_requests=(EvidenceRequestType.PROFITABILITY_METRICS,),
    )

    embedded_response = ApplicationService(
        snapshot_provider=embedded,
        extractor=_MicrosoftGrowthExtractor(),
    ).verify(cik=request.cik, request=verify_request)
    indexed_response = ApplicationService(
        snapshot_provider=IndexedSnapshotProvider(indexed_release=indexed),
        extractor=_MicrosoftGrowthExtractor(),
    ).verify(cik=request.cik, request=verify_request)

    assert indexed_response == embedded_response
    assert indexed_response["audit_manifest"]["acquisition_records"] == (
        ("profitability_metrics", "deterministic coverage gap: profitability_metrics"),
    )


def test_narrative_context_is_manifest_filtered_and_cannot_change_a_verdict() -> None:
    release = _v1_release()
    narrative_text = (
        "This issuer disclosure is context only and does not establish a fact."
    )
    chunk = NarrativeDisclosureChunk.create(
        evidence_release_manifest_hash=release.manifest_hash,
        cik="789019",
        filing_accession="0000950170-24-087843",
        filed_at=date(2024, 7, 30),
        source_url="https://www.sec.gov/Archives/msft-2024.htm",
        source_span=(120, 120 + len(narrative_text)),
        text=narrative_text,
    )
    indexed, embedded, request = _compiled_msft_release(narrative_chunks=(chunk,))
    retriever = NarrativeContextRetriever(narrative_index=indexed.narrative_context)
    archived = IndexedReleaseArchive.load(IndexedReleaseArchive.dump(indexed))

    assert archived.indexed_release.narrative_context.context(
        evidence_release_manifest_hash=release.manifest_hash,
        cik=request.cik,
    ) == (chunk,)

    assert retriever.context(
        evidence_release_manifest_hash=release.manifest_hash, cik=request.cik
    ) == (chunk,)
    assert retriever.context(
        evidence_release_manifest_hash="f" * 64, cik=request.cik
    ) == ()
    assert retriever.context(
        evidence_release_manifest_hash=release.manifest_hash, cik="320193"
    ) == ()

    analysis = "Microsoft revenue increased from fiscal 2023 to fiscal 2024"
    verify_request = VerifyRequest(
        analysis=analysis, as_of_date=request.as_of_date, forms=request.forms
    )
    assert ApplicationService(
        snapshot_provider=IndexedSnapshotProvider(indexed_release=indexed),
        extractor=_MicrosoftGrowthExtractor(),
    ).verify(cik=request.cik, request=verify_request) == ApplicationService(
        snapshot_provider=embedded,
        extractor=_MicrosoftGrowthExtractor(),
    ).verify(cik=request.cik, request=verify_request)


def test_indexed_snapshot_adapter_rejects_requests_not_compiled_into_the_release() -> None:
    indexed, _, request = _compiled_msft_release()
    provider = IndexedSnapshotProvider(indexed_release=indexed)

    with pytest.raises(IndexedReleaseError, match="not compiled"):
        provider.build(
            cik=request.cik,
            as_of_date=date(2024, 7, 31),
            forms=request.forms,
        )
