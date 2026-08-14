from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from quantify.calculations import (
    ApprovedCalculationInstruction,
    ApprovedCalculationRequest,
    ApprovedCalculationResult,
    CalculationError,
    CalculationOperation,
    DeterministicCalculationAdapter,
)
from quantify.evidence_search import (
    ApprovedEvidenceFact,
    ApprovedEvidenceQuery,
    ApprovedEvidenceSearchRequest,
    ApprovedEvidenceSearchResult,
    EvidenceSearchTask,
    FrozenReleaseEvidenceSearch,
)
from quantify.research_answers import (
    EntityBinding,
    ReleaseBinding,
    ResearchAnswerValidationContext,
    validate_research_answer,
)
from tests.test_indexed_release import _compiled_msft_release


def microsoft_records(release, *, metrics: tuple[str, ...], period_end: date):
    return tuple(
        next(
            record
            for record in release.exact_facts.records
            if record.evidence.entity_cik == "0000789019"
            and record.evidence.metric == metric
            and record.evidence.period_end == period_end
        )
        for metric in metrics
    )


def search_records(release, records):
    request = ApprovedEvidenceSearchRequest(
        task_type=EvidenceSearchTask.ANALYZE,
        cik="0000789019",
        as_of=date(2024, 7, 30),
        release_id=release.evidence_release.release_id,
        release_manifest_hash=release.evidence_release.manifest_hash,
        queries=tuple(
            ApprovedEvidenceQuery(
                query_id=f"q-{index}",
                metric=record.key.metric,
                period_start=record.key.fiscal_period_start,
                period_end=record.key.fiscal_period_end,
                unit=record.key.unit,
            )
            for index, record in enumerate(records)
        ),
    )
    return FrozenReleaseEvidenceSearch(release=release).search(request)


def calculation_request(search_result, *, operation, inputs, decimal_places=2):
    return ApprovedCalculationRequest(
        evidence_search_result_hash=search_result.result_hash,
        release_manifest_hash=search_result.request.release_manifest_hash,
        calculations=(
            ApprovedCalculationInstruction(
                result_statement_id="calc-primary",
                operation=operation,
                input_statement_ids=tuple(item.statement_id for item in inputs),
                decimal_places=decimal_places,
            ),
        ),
    )


def revenue_comparison():
    release, _, _ = _compiled_msft_release()
    baseline = microsoft_records(
        release,
        metrics=("revenue",),
        period_end=date(2023, 6, 30),
    )[0]
    current = microsoft_records(
        release,
        metrics=("revenue",),
        period_end=date(2024, 6, 30),
    )[0]
    result = search_records(release, (current, baseline))
    facts = {fact.period_end: fact for fact in result.facts}
    return release, result, facts[date(2024, 6, 30)], facts[date(2023, 6, 30)]


def test_percent_change_is_release_bound_replayable_and_canonical() -> None:
    _, search_result, current, baseline = revenue_comparison()
    request = calculation_request(
        search_result,
        operation=CalculationOperation.PERCENT_CHANGE,
        inputs=(current, baseline),
    )

    result = DeterministicCalculationAdapter().calculate(
        request=request,
        evidence_search_result=search_result,
    )
    document = result.to_document()

    assert request.request_hash == ApprovedCalculationRequest(
        evidence_search_result_hash=search_result.result_hash,
        release_manifest_hash=search_result.request.release_manifest_hash,
        calculations=request.calculations,
    ).request_hash
    assert document["status"] == "completed"
    assert document["evidence_search_result_hash"] == search_result.result_hash
    assert document["calculations"][0]["text"] == (
        "Calculated percent change: 15.67%."
    )
    assert document["calculations"][0]["calculation"]["value"] == "15.67"
    assert len(result.result_hash) == 64


@pytest.mark.parametrize(
    ("operation", "value", "unit", "text"),
    [
        (
            CalculationOperation.DIFFERENCE,
            "33207000000",
            "USD",
            "Calculated difference: 33207000000 USD.",
        ),
        (
            CalculationOperation.PERCENT_CHANGE,
            "16",
            "percent",
            "Calculated percent change: 16%.",
        ),
    ],
)
def test_comparison_operations_use_current_then_baseline(
    operation: CalculationOperation, value: str, unit: str, text: str
) -> None:
    release, search_result, current, baseline = revenue_comparison()
    request = calculation_request(
        search_result,
        operation=operation,
        inputs=(current, baseline),
        decimal_places=0,
    )

    calculation = DeterministicCalculationAdapter().calculate(
        request=request, evidence_search_result=search_result
    ).calculations[0]

    assert calculation.value == Decimal(value)
    assert calculation.unit == unit
    assert calculation.statement_text == text


def test_sum_requires_one_exact_period_and_unit() -> None:
    release, _, _ = _compiled_msft_release()
    records = microsoft_records(
        release,
        metrics=("revenue", "net_income"),
        period_end=date(2024, 6, 30),
    )
    search_result = search_records(release, records)
    request = calculation_request(
        search_result,
        operation=CalculationOperation.SUM,
        inputs=search_result.facts,
        decimal_places=0,
    )

    calculation = DeterministicCalculationAdapter().calculate(
        request=request, evidence_search_result=search_result
    ).calculations[0]

    assert calculation.value == Decimal("333258000000")
    assert calculation.statement_text == "Calculated sum: 333258000000 USD."


def synthetic_percent_search(*, current_value: str, baseline_value: str):
    release, _, _ = _compiled_msft_release()
    manifest_hash = release.evidence_release.manifest_hash
    request = ApprovedEvidenceSearchRequest(
        task_type=EvidenceSearchTask.COMPARE,
        cik="0000789019",
        as_of=date(2024, 7, 30),
        release_id=release.evidence_release.release_id,
        release_manifest_hash=manifest_hash,
        queries=(
            ApprovedEvidenceQuery(
                "current", "policy_rate", date(2024, 1, 1), date(2024, 3, 31), "percent"
            ),
            ApprovedEvidenceQuery(
                "baseline", "policy_rate", date(2023, 10, 1), date(2023, 12, 31), "percent"
            ),
        ),
    )

    def fact(*, query_id, fact_id, value, start, end):
        return ApprovedEvidenceFact(
            query_id=query_id,
            fact_id=fact_id,
            statement_text=f"Released policy rate was {value} percent.",
            entity_cik="0000789019",
            metric="policy_rate",
            value=Decimal(value),
            unit="percent",
            period_start=start,
            period_end=end,
            filing_accession=f"record-{query_id}",
            filed_at=date(2024, 7, 1),
            source_url=f"https://example.test/{query_id}",
            evidence_id=f"evidence-{query_id}",
            release_manifest_hash=manifest_hash,
            derived_from_evidence_ids=(),
        )

    current = fact(
        query_id="current",
        fact_id="1" * 64,
        value=current_value,
        start=date(2024, 1, 1),
        end=date(2024, 3, 31),
    )
    baseline = fact(
        query_id="baseline",
        fact_id="2" * 64,
        value=baseline_value,
        start=date(2023, 10, 1),
        end=date(2023, 12, 31),
    )
    return ApprovedEvidenceSearchResult(
        request=request,
        facts=(current, baseline),
        unavailable=(),
    ), current, baseline


def test_percentage_point_change_and_round_half_even() -> None:
    search_result, current, baseline = synthetic_percent_search(
        current_value="7.845", baseline_value="5.5"
    )
    request = calculation_request(
        search_result,
        operation=CalculationOperation.PERCENTAGE_POINT_CHANGE,
        inputs=(current, baseline),
        decimal_places=2,
    )

    calculation = DeterministicCalculationAdapter().calculate(
        request=request, evidence_search_result=search_result
    ).calculations[0]

    assert calculation.value == Decimal("2.34")
    assert calculation.unit == "percentage_points"
    assert calculation.statement_text == (
        "Calculated percentage-point change: 2.34 percentage points."
    )


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("wrong_search_hash", "input_binding_mismatch"),
        ("wrong_release_hash", "input_binding_mismatch"),
        ("unknown_input", "input_unavailable"),
        ("reversed_periods", "incompatible_inputs"),
        ("different_metric", "incompatible_inputs"),
    ],
)
def test_adapter_fails_closed_for_unbound_or_incompatible_inputs(
    mutation: str, code: str
) -> None:
    release, search_result, current, baseline = revenue_comparison()
    inputs = (current, baseline)
    request = calculation_request(
        search_result,
        operation=CalculationOperation.PERCENT_CHANGE,
        inputs=inputs,
    )
    if mutation == "wrong_search_hash":
        request = replace(request, evidence_search_result_hash="f" * 64)
    elif mutation == "wrong_release_hash":
        request = replace(request, release_manifest_hash="f" * 64)
    elif mutation == "unknown_input":
        instruction = replace(
            request.calculations[0],
            input_statement_ids=(current.statement_id, f"fact-{'f' * 64}"),
        )
        request = replace(request, calculations=(instruction,))
    elif mutation == "reversed_periods":
        instruction = replace(
            request.calculations[0],
            input_statement_ids=(baseline.statement_id, current.statement_id),
        )
        request = replace(request, calculations=(instruction,))
    else:
        different_records = (
            microsoft_records(
                release,
                metrics=("revenue",),
                period_end=date(2024, 6, 30),
            )[0],
            microsoft_records(
                release,
                metrics=("net_income",),
                period_end=date(2023, 6, 30),
            )[0],
        )
        search_result = search_records(release, different_records)
        current = next(
            fact for fact in search_result.facts if fact.metric == "revenue"
        )
        altered = next(
            fact for fact in search_result.facts if fact.metric == "net_income"
        )
        request = calculation_request(
            search_result,
            operation=CalculationOperation.PERCENT_CHANGE,
            inputs=(current, altered),
        )

    with pytest.raises(CalculationError) as captured:
        DeterministicCalculationAdapter().calculate(
            request=request, evidence_search_result=search_result
        )
    assert captured.value.code == code


def test_zero_percent_change_baseline_fails_closed() -> None:
    search_result, current, baseline = synthetic_percent_search(
        current_value="1", baseline_value="0"
    )
    request = calculation_request(
        search_result,
        operation=CalculationOperation.PERCENT_CHANGE,
        inputs=(current, baseline),
    )

    with pytest.raises(CalculationError) as captured:
        DeterministicCalculationAdapter().calculate(
            request=request, evidence_search_result=search_result
        )
    assert captured.value.code == "incompatible_inputs"


def test_request_rejects_non_fact_inputs_duplicates_and_unbounded_precision() -> None:
    with pytest.raises(CalculationError, match="released-fact"):
        ApprovedCalculationInstruction(
            "calc-bad",
            CalculationOperation.SUM,
            ("calc-one", "calc-two"),
            2,
        )
    with pytest.raises(CalculationError, match="unique"):
        ApprovedCalculationInstruction(
            "calc-bad",
            CalculationOperation.SUM,
            (f"fact-{'1' * 64}", f"fact-{'1' * 64}"),
            2,
        )
    with pytest.raises(CalculationError, match="0 to 12"):
        ApprovedCalculationInstruction(
            "calc-bad",
            CalculationOperation.DIFFERENCE,
            (f"fact-{'1' * 64}", f"fact-{'2' * 64}"),
            13,
        )


def test_result_rejects_tampered_calculation() -> None:
    _, search_result, current, baseline = revenue_comparison()
    request = calculation_request(
        search_result,
        operation=CalculationOperation.PERCENT_CHANGE,
        inputs=(current, baseline),
    )
    result = DeterministicCalculationAdapter().calculate(
        request=request, evidence_search_result=search_result
    )
    tampered = replace(
        result.calculations[0],
        value=Decimal("99.99"),
        statement_text="Calculated percent change: 99.99%.",
    )

    with pytest.raises(CalculationError) as captured:
        ApprovedCalculationResult(
            request=request,
            evidence_search_result=search_result,
            calculations=(tampered,),
        )
    assert captured.value.code == "invalid_result"


def test_calculation_result_is_accepted_by_research_answer_boundary() -> None:
    release, search_result, current, baseline = revenue_comparison()
    calculation_result = DeterministicCalculationAdapter().calculate(
        request=calculation_request(
            search_result,
            operation=CalculationOperation.PERCENT_CHANGE,
            inputs=(current, baseline),
        ),
        evidence_search_result=search_result,
    )
    calculation = calculation_result.calculations[0]
    as_of = "2024-07-30T00:00:00+00:00"
    audit_hash = "a" * 64
    fact_documents = [fact.to_document() for fact in (current, baseline)]
    document = {
        "schema_version": "research-answer.v1",
        "task_type": "analyze",
        "status": "completed",
        "as_of": as_of,
        "entities": [
            {
                "entity_id": "0000789019",
                "entity_type": "company",
                "display_name": "Microsoft",
            }
        ],
        "release_scope": {
            "catalogs": ["earnings"],
            "release_ids": [release.evidence_release.release_id],
            "manifest_hashes": [release.evidence_release.manifest_hash],
            "observed_through": as_of,
        },
        "answer": calculation.statement_text,
        "answer_statement_ids": [calculation.statement_id],
        "statements": [
            *[
                {
                    "statement_id": fact.statement_id,
                    "kind": "released_fact",
                    "text": fact.statement_text,
                    "citation_ids": [fact.citation_id],
                    "derived_from_statement_ids": [],
                    "measurement": fact_document["measurement"],
                    "calculation": None,
                }
                for fact, fact_document in zip((current, baseline), fact_documents)
            ],
            calculation.to_document(),
        ],
        "citations": [fact_document["citation"] for fact_document in fact_documents],
        "counterpoint_statement_ids": [],
        "unavailable": [],
        "limitations": ["Exact released facts and deterministic arithmetic only."],
        "model_contract": None,
        "verification_results": [],
        "audit_manifest_hash": audit_hash,
    }
    context = ResearchAnswerValidationContext(
        task_type="analyze",
        entities=(EntityBinding("0000789019", "company", "Microsoft"),),
        as_of=as_of,
        release_bindings=(
            ReleaseBinding(
                "earnings",
                release.evidence_release.release_id,
                release.evidence_release.manifest_hash,
            ),
        ),
        observed_through=as_of,
        authorized_citations=search_result.authorized_citations(),
        audit_manifest_hash=audit_hash,
    )

    validated = validate_research_answer(document, context=context)

    assert validated.to_document()["answer"] == "Calculated percent change: 15.67%."
