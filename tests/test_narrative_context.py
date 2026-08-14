from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import json

import pytest

from quantify.indexed_release import IndexedReleaseError, NarrativeDisclosureChunk
from quantify.indexed_release_archive import IndexedReleaseArchive
from quantify.narrative_context import (
    ApprovedNarrativeContextRequest,
    ApprovedNarrativeContextResult,
    FrozenReleaseNarrativeContext,
    NarrativeContextError,
    NarrativeContextStatus,
    NarrativeContextTask,
    UnavailableNarrativeContext,
)
from quantify.research_answers import (
    EntityBinding,
    ReleaseBinding,
    ResearchAnswerValidationContext,
    ResearchAnswerValidationError,
    validate_research_answer,
)
from tests.test_indexed_release import _compiled_msft_release, _v1_release


def chunk(
    *,
    text: str,
    accession: str = "0000950170-24-087843",
    filed_at: date = date(2024, 7, 30),
    start_char: int = 100,
) -> NarrativeDisclosureChunk:
    return NarrativeDisclosureChunk.create(
        evidence_release_manifest_hash=_v1_release().manifest_hash,
        cik="789019",
        filing_accession=accession,
        filed_at=filed_at,
        source_url=f"https://www.sec.gov/Archives/{accession}-index.html",
        source_span=(start_char, start_char + len(text)),
        text=text,
    )


def request_for(
    release,
    *,
    filing_accessions: tuple[str, ...] = (),
    maximum_chunks: int = 8,
    manifest_hash: str | None = None,
) -> ApprovedNarrativeContextRequest:
    return ApprovedNarrativeContextRequest(
        task_type=NarrativeContextTask.ANALYZE,
        cik="789019",
        as_of=date(2024, 7, 30),
        release_id=release.evidence_release.release_id,
        release_manifest_hash=manifest_hash or release.evidence_release.manifest_hash,
        filing_accessions=filing_accessions,
        maximum_chunks=maximum_chunks,
    )


def test_request_is_canonical_capped_and_replay_stable() -> None:
    release, _, _ = _compiled_msft_release()
    accessions = (
        "0001564590-22-026876",
        "0000950170-24-087843",
    )
    request = request_for(release, filing_accessions=accessions, maximum_chunks=4)
    replay = request_for(
        release, filing_accessions=tuple(reversed(accessions)), maximum_chunks=4
    )

    assert request.cik == "0000789019"
    assert request.to_document()["filing_accessions"] == sorted(accessions)
    assert request.request_hash == replay.request_hash
    assert len(request.request_hash) == 64

    with pytest.raises(NarrativeContextError, match="between 1 and 16"):
        request_for(release, maximum_chunks=17)
    with pytest.raises(NarrativeContextError, match="filing_accession"):
        request_for(release, filing_accessions=("not-an-accession",))
    with pytest.raises(NarrativeContextError, match="unique"):
        request_for(
            release,
            filing_accessions=(accessions[0], accessions[0]),
        )
    with pytest.raises(NarrativeContextError, match="filing_accession"):
        request_for(release, filing_accessions=([],))  # type: ignore[arg-type]


def test_compiled_context_requires_exact_source_metadata_and_release_issuer() -> None:
    text = "Bounded narrative text."
    with pytest.raises(IndexedReleaseError, match="HTTPS"):
        NarrativeDisclosureChunk.create(
            evidence_release_manifest_hash=_v1_release().manifest_hash,
            cik="789019",
            filing_accession="0000950170-24-087843",
            filed_at=date(2024, 7, 30),
            source_url="http://example.com/filing",
            source_span=(0, len(text)),
            text=text,
        )
    with pytest.raises(IndexedReleaseError, match="incomplete"):
        NarrativeDisclosureChunk.create(
            evidence_release_manifest_hash=_v1_release().manifest_hash,
            cik="789019",
            filing_accession="0000950170-24-087843",
            filed_at=date(2024, 7, 30),
            source_url="https://www.sec.gov/Archives/filing.htm",
            source_span=(0, len(text) + 1),
            text=text,
        )

    outside = NarrativeDisclosureChunk.create(
        evidence_release_manifest_hash=_v1_release().manifest_hash,
        cik="1",
        filing_accession="0000000001-24-000001",
        filed_at=date(2024, 7, 30),
        source_url="https://www.sec.gov/Archives/outside.htm",
        source_span=(0, len(text)),
        text=text,
    )
    with pytest.raises(IndexedReleaseError, match="issuer is outside"):
        _compiled_msft_release(narrative_chunks=(outside,))


def test_retrieval_returns_replayable_context_only_authorization() -> None:
    disclosure = chunk(
        text="Management discussed demand and capacity constraints in this filing."
    )
    release, _, _ = _compiled_msft_release(narrative_chunks=(disclosure,))
    request = request_for(
        release, filing_accessions=(disclosure.filing_accession,)
    )

    result = FrozenReleaseNarrativeContext(release=release).retrieve(request)
    document = result.to_document()
    context = document["contexts"][0]
    citation = context["citation"]
    authorization = result.authorized_citations()[0]

    assert result.status is NarrativeContextStatus.COMPLETED
    assert document["request_hash"] == request.request_hash
    assert context["kind"] == "narrative_context"
    assert context["statement_text"] == disclosure.text
    assert citation["source_type"] == "narrative_disclosure"
    assert citation["verification_role"] == "context_only"
    assert citation["evidence_id"] is None
    assert citation["source_span"] == {
        "start_char": disclosure.source_span[0],
        "end_char": disclosure.source_span[1],
    }
    assert authorization.statement_text == disclosure.text
    assert authorization.measurement_value is None
    assert len(result.result_hash) == 64


def test_context_is_accepted_by_research_answer_as_context_only() -> None:
    disclosure = chunk(text="The filing describes a material operating dependency.")
    release, _, _ = _compiled_msft_release(narrative_chunks=(disclosure,))
    result = FrozenReleaseNarrativeContext(release=release).retrieve(
        request_for(release)
    )
    item = result.contexts[0]
    citation = item.to_document()["citation"]
    as_of = "2024-07-30T00:00:00+00:00"
    audit_hash = "a" * 64
    document = {
        "schema_version": "research-answer.v1",
        "task_type": "analyze",
        "status": "completed",
        "as_of": as_of,
        "entities": [
            {
                "entity_id": result.request.cik,
                "entity_type": "company",
                "display_name": "Microsoft",
            }
        ],
        "release_scope": {
            "catalogs": ["earnings"],
            "release_ids": [result.request.release_id],
            "manifest_hashes": [result.request.release_manifest_hash],
            "observed_through": as_of,
        },
        "answer": item.statement_text,
        "answer_statement_ids": [item.statement_id],
        "statements": [
            {
                "statement_id": item.statement_id,
                "kind": "narrative_context",
                "text": item.statement_text,
                "citation_ids": [item.citation_id],
                "derived_from_statement_ids": [],
                "measurement": None,
                "calculation": None,
            }
        ],
        "citations": [citation],
        "counterpoint_statement_ids": [],
        "unavailable": [],
        "limitations": [result.to_document()["limitation"]],
        "model_contract": None,
        "verification_results": [],
        "audit_manifest_hash": audit_hash,
    }
    validation_context = ResearchAnswerValidationContext(
        task_type="analyze",
        entities=(EntityBinding(result.request.cik, "company", "Microsoft"),),
        as_of=as_of,
        release_bindings=(
            ReleaseBinding(
                "earnings",
                result.request.release_id,
                result.request.release_manifest_hash,
            ),
        ),
        observed_through=as_of,
        authorized_citations=result.authorized_citations(),
        audit_manifest_hash=audit_hash,
    )

    validated = validate_research_answer(document, context=validation_context)
    assert validated.to_document()["statements"][0]["kind"] == "narrative_context"

    document["statements"][0]["kind"] = "released_fact"
    with pytest.raises(ResearchAnswerValidationError) as captured:
        validate_research_answer(document, context=validation_context)
    assert captured.value.code == "citation_role_invalid"


def test_exact_filing_scope_reports_partial_unavailable_and_truncation() -> None:
    first = chunk(text="First released context.", start_char=10)
    second = chunk(text="Second released context.", start_char=40)
    missing = "0001564590-22-026876"
    release, _, _ = _compiled_msft_release(narrative_chunks=(first, second))

    partial = FrozenReleaseNarrativeContext(release=release).retrieve(
        request_for(
            release,
            filing_accessions=(first.filing_accession, missing),
            maximum_chunks=1,
        )
    )

    assert partial.status is NarrativeContextStatus.PARTIAL
    assert len(partial.contexts) == 1
    assert partial.omitted_chunk_count == 1
    assert partial.unavailable[0].request == missing
    assert partial.unavailable[0].reason == "filing_context_not_released"

    empty = FrozenReleaseNarrativeContext(release=release).retrieve(
        request_for(release, filing_accessions=(missing,))
    )
    assert empty.status is NarrativeContextStatus.UNAVAILABLE
    assert empty.contexts == ()
    assert empty.omitted_chunk_count == 0


def test_context_after_as_of_is_not_returned_or_used_as_fallback() -> None:
    later = chunk(
        text="This disclosure was filed after the admitted date.",
        filed_at=date(2024, 7, 31),
    )
    release, _, _ = _compiled_msft_release(narrative_chunks=(later,))

    result = FrozenReleaseNarrativeContext(release=release).retrieve(
        request_for(release)
    )

    assert result.status is NarrativeContextStatus.UNAVAILABLE
    assert result.contexts == ()
    assert result.unavailable[0].reason == "narrative_context_not_released"
    assert "live retrieval" in result.to_document()["limitation"]


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("release", "release_mismatch"),
        ("entity", "entity_out_of_scope"),
        ("as_of", "as_of_not_compiled"),
    ],
)
def test_retrieval_fails_closed_for_scope_mismatch(mutation: str, code: str) -> None:
    release, _, _ = _compiled_msft_release()
    request = request_for(release)
    if mutation == "release":
        request = request_for(release, manifest_hash="f" * 64)
    elif mutation == "entity":
        request = replace(request, cik="0000000001")
    else:
        request = replace(request, as_of=request.as_of - timedelta(days=1))

    with pytest.raises(NarrativeContextError) as captured:
        FrozenReleaseNarrativeContext(release=release).retrieve(request)
    assert captured.value.code == code


def test_result_rejects_context_detached_from_request() -> None:
    disclosure = chunk(text="Bound context.")
    release, _, _ = _compiled_msft_release(narrative_chunks=(disclosure,))
    result = FrozenReleaseNarrativeContext(release=release).retrieve(
        request_for(release)
    )
    with pytest.raises(NarrativeContextError, match="compiled chunk hash"):
        replace(result.contexts[0], statement_text="Other context.")
    detached = replace(result.contexts[0], release_manifest_hash="f" * 64)

    with pytest.raises(NarrativeContextError, match="request and release binding"):
        ApprovedNarrativeContextResult(
            request=result.request,
            contexts=(detached,),
            unavailable=(),
        )

    with pytest.raises(NarrativeContextError, match="does not match the request"):
        ApprovedNarrativeContextResult(
            request=replace(
                result.request,
                filing_accessions=(disclosure.filing_accession,),
            ),
            contexts=(),
            unavailable=(
                UnavailableNarrativeContext(
                    request="0001564590-22-026876",
                    reason="filing_context_not_released",
                    detail="Not released.",
                ),
            ),
        )


def test_indexed_archive_replays_narrative_source_metadata() -> None:
    disclosure = chunk(text="Archive-bound context.")
    release, _, _ = _compiled_msft_release(narrative_chunks=(disclosure,))

    payload = IndexedReleaseArchive.dump(release)
    archived = IndexedReleaseArchive.load(payload).indexed_release

    assert json.loads(payload)["schema_version"] == "1.2.0"
    assert archived.narrative_context.chunks == (disclosure,)
    assert archived.manifest_hash == release.manifest_hash


def test_legacy_empty_narrative_archive_replays_but_legacy_chunks_fail_closed() -> None:
    empty_release, _, _ = _compiled_msft_release()
    legacy_empty = json.loads(IndexedReleaseArchive.dump(empty_release))
    legacy_empty["schema_version"] = "1.1.0"
    replay = IndexedReleaseArchive.load(
        json.dumps(legacy_empty, sort_keys=True, separators=(",", ":")).encode()
    ).indexed_release
    assert replay.manifest_hash == empty_release.manifest_hash

    disclosure = chunk(text="Legacy context requires new source metadata.")
    release, _, _ = _compiled_msft_release(narrative_chunks=(disclosure,))
    legacy_with_context = json.loads(IndexedReleaseArchive.dump(release))
    legacy_with_context["schema_version"] = "1.1.0"
    with pytest.raises(IndexedReleaseError, match="require archive recompilation"):
        IndexedReleaseArchive.load(
            json.dumps(
                legacy_with_context,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
