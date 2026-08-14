from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from quantify.evidence_search import (
    ApprovedEvidenceFact,
    ApprovedEvidenceQuery,
    ApprovedEvidenceSearchRequest,
    ApprovedEvidenceSearchResult,
    EvidenceSearchError,
    EvidenceSearchStatus,
    EvidenceSearchTask,
    FrozenReleaseEvidenceSearch,
    UnavailableEvidenceQuery,
    canonical_decimal,
)
from quantify.indexed_release import NarrativeDisclosureChunk
from quantify.research_answers import (
    EntityBinding,
    ReleaseBinding,
    ResearchAnswerValidationContext,
    validate_research_answer,
)
from tests.test_indexed_release import _compiled_msft_release, _v1_release


def query_for(record, *, query_id: str = "revenue-current", metric: str | None = None):
    return ApprovedEvidenceQuery(
        query_id=query_id,
        metric=metric or record.key.metric,
        period_start=record.key.fiscal_period_start,
        period_end=record.key.fiscal_period_end,
        unit=record.key.unit,
    )


def request_for(release, record, *, queries=None, manifest_hash: str | None = None):
    return ApprovedEvidenceSearchRequest(
        task_type=EvidenceSearchTask.ANALYZE,
        cik=record.key.cik,
        as_of=date(2024, 7, 30),
        release_id=release.evidence_release.release_id,
        release_manifest_hash=manifest_hash or release.evidence_release.manifest_hash,
        queries=queries or (query_for(record),),
    )


def revenue_records(release):
    records = [
        record
        for record in release.exact_facts.records
        if record.evidence.entity_cik == "0000789019"
        and record.evidence.metric == "revenue"
    ]
    return sorted(records, key=lambda record: record.evidence.period_end)


def test_request_is_canonical_and_hash_is_stable() -> None:
    release, _, _ = _compiled_msft_release()
    previous, current = revenue_records(release)[-2:]
    request = request_for(
        release,
        current,
        queries=(
            query_for(current, query_id="z-current"),
            query_for(previous, query_id="a-previous"),
        ),
    )
    replay = request_for(
        release,
        current,
        queries=(
            query_for(previous, query_id="a-previous"),
            query_for(current, query_id="z-current"),
        ),
    )

    assert request.cik == "0000789019"
    assert [item["query_id"] for item in request.to_document()["queries"]] == [
        "a-previous",
        "z-current",
    ]
    assert request.request_hash == replay.request_hash
    assert len(request.request_hash) == 64


def test_exact_search_returns_replayable_fact_and_research_authorization() -> None:
    release, _, _ = _compiled_msft_release()
    record = revenue_records(release)[-1]
    request = request_for(release, record)

    result = FrozenReleaseEvidenceSearch(release=release).search(request)
    document = result.to_document()
    fact = document["facts"][0]
    authorization = result.authorized_citations()[0]

    assert result.status is EvidenceSearchStatus.COMPLETED
    assert document["request_hash"] == request.request_hash
    assert document["release"]["manifest_hash"] == release.evidence_release.manifest_hash
    assert fact["measurement"] == {
        "value": canonical_decimal(record.evidence.value),
        "unit": record.evidence.unit,
    }
    assert fact["citation"]["source_type"] == "structured_fact"
    assert fact["citation"]["verification_role"] == "verdict_evidence"
    assert authorization.statement_text == fact["statement_text"]
    assert authorization.measurement_value == record.evidence.value
    assert len(result.result_hash) == 64


def test_exact_search_fact_is_accepted_by_research_answer_boundary() -> None:
    release, _, _ = _compiled_msft_release()
    record = revenue_records(release)[-1]
    result = FrozenReleaseEvidenceSearch(release=release).search(
        request_for(release, record)
    )
    fact = result.facts[0]
    fact_document = fact.to_document()
    citation = fact_document["citation"]
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
        "answer": fact.statement_text,
        "answer_statement_ids": [fact.statement_id],
        "statements": [
            {
                "statement_id": fact.statement_id,
                "kind": "released_fact",
                "text": fact.statement_text,
                "citation_ids": [fact.citation_id],
                "derived_from_statement_ids": [],
                "measurement": fact_document["measurement"],
                "calculation": None,
            }
        ],
        "citations": [citation],
        "counterpoint_statement_ids": [],
        "unavailable": [],
        "limitations": [
            "Exact structured facts from the declared frozen release only."
        ],
        "model_contract": None,
        "verification_results": [],
        "audit_manifest_hash": audit_hash,
    }
    context = ResearchAnswerValidationContext(
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

    validated = validate_research_answer(document, context=context)

    assert validated.to_document()["answer"] == fact.statement_text


def test_search_reports_partial_and_empty_scope_without_fallback() -> None:
    release_definition = _v1_release()
    narrative_text = "Revenue discussion exists here, but this text is context only."
    chunk = NarrativeDisclosureChunk.create(
        evidence_release_manifest_hash=release_definition.manifest_hash,
        cik="789019",
        filing_accession="0000950170-24-087843",
        filed_at=date(2024, 7, 30),
        source_url="https://www.sec.gov/Archives/msft-2024.htm",
        source_span=(50, 50 + len(narrative_text)),
        text=narrative_text,
    )
    release, _, _ = _compiled_msft_release(narrative_chunks=(chunk,))
    record = revenue_records(release)[-1]
    missing = query_for(record, query_id="missing", metric="not_released")
    result = FrozenReleaseEvidenceSearch(release=release).search(
        request_for(
            release,
            record,
            queries=(query_for(record, query_id="found"), missing),
        )
    )

    assert result.status is EvidenceSearchStatus.PARTIAL
    assert [fact.query_id for fact in result.facts] == ["found"]
    assert result.unavailable == (UnavailableEvidenceQuery(query_id="missing"),)

    empty = FrozenReleaseEvidenceSearch(release=release).search(
        request_for(release, record, queries=(missing,))
    )
    assert empty.status is EvidenceSearchStatus.UNAVAILABLE
    assert empty.facts == ()
    assert "narrative" in empty.to_document()["limitation"]


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("release", "release_mismatch"),
        ("entity", "entity_out_of_scope"),
        ("as_of", "as_of_not_compiled"),
    ],
)
def test_search_fails_closed_for_scope_mismatch(mutation: str, code: str) -> None:
    release, _, _ = _compiled_msft_release()
    record = revenue_records(release)[-1]
    request = request_for(release, record)
    if mutation == "release":
        request = request_for(release, record, manifest_hash="f" * 64)
    elif mutation == "entity":
        request = replace(request, cik="0000000001")
    else:
        request = replace(request, as_of=request.as_of - timedelta(days=1))

    with pytest.raises(EvidenceSearchError) as captured:
        FrozenReleaseEvidenceSearch(release=release).search(request)
    assert captured.value.code == code


def test_request_rejects_ambiguous_or_unbounded_queries() -> None:
    release, _, _ = _compiled_msft_release()
    record = revenue_records(release)[-1]
    duplicate_key = (
        query_for(record, query_id="one"),
        query_for(record, query_id="two"),
    )
    with pytest.raises(EvidenceSearchError, match="exact query keys"):
        request_for(release, record, queries=duplicate_key)

    with pytest.raises(EvidenceSearchError, match="1 to 32"):
        request_for(
            release,
            record,
            queries=tuple(
                ApprovedEvidenceQuery(
                    query_id=f"q-{index}",
                    metric=f"metric_{index}",
                    period_start=date(2024, 1, 1),
                    period_end=date(2024, 1, 2),
                    unit="USD",
                )
                for index in range(33)
            ),
        )

    with pytest.raises(EvidenceSearchError, match="lowercase SHA-256"):
        request_for(release, record, manifest_hash="A" * 64)


def test_result_rejects_a_fact_detached_from_its_exact_query() -> None:
    release, _, _ = _compiled_msft_release()
    record = revenue_records(release)[-1]
    request = request_for(release, record)
    valid = FrozenReleaseEvidenceSearch(release=release).search(request).facts[0]
    detached = replace(valid, metric="operating_income")

    with pytest.raises(EvidenceSearchError) as captured:
        ApprovedEvidenceSearchResult(
            request=request,
            facts=(detached,),
            unavailable=(),
        )
    assert captured.value.code == "invalid_result"


@pytest.mark.parametrize(
    ("value", "rendered"),
    [
        (Decimal("5.500"), "5.5"),
        (Decimal("1E+3"), "1000"),
        (Decimal("-0.00"), "0"),
    ],
)
def test_decimal_values_have_one_canonical_wire_form(
    value: Decimal, rendered: str
) -> None:
    assert canonical_decimal(value) == rendered


def test_fact_validation_rejects_non_https_provenance() -> None:
    release, _, _ = _compiled_msft_release()
    record = revenue_records(release)[-1]
    fact = FrozenReleaseEvidenceSearch(release=release).search(
        request_for(release, record)
    ).facts[0]

    with pytest.raises(EvidenceSearchError):
        ApprovedEvidenceFact(
            **{
                field: getattr(fact, field)
                for field in fact.__dataclass_fields__
                if field != "source_url"
            },
            source_url="http://example.test/fact",
        )
