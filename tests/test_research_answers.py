from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from quantify.research_answers import (
    AuthorizedCitation,
    EntityBinding,
    InterpretationWarrant,
    ModelContract,
    ReleaseBinding,
    ResearchAnswerValidationContext,
    ResearchAnswerValidationError,
    VerificationResultBinding,
    validate_research_answer,
)


RELEASE_HASH = "a" * 64
AUDIT_HASH = "b" * 64
VERIFIER_AUDIT_HASH = "c" * 64
PROMPT_HASH = "d" * 64
TOOL_HASH = "e" * 64
AS_OF = "2024-07-30T00:00:00+00:00"
CURRENT_TEXT = "Microsoft fiscal 2024 revenue was 245122000000 USD."
PRIOR_TEXT = "Microsoft fiscal 2023 revenue was 211915000000 USD."
CALCULATION_TEXT = "Calculated percent change: 15.67%."
INTERPRETATION_TEXT = "Revenue increased year over year within the declared filing scope."


def current_authorization() -> AuthorizedCitation:
    return AuthorizedCitation(
        source_type="structured_fact",
        verification_role="verdict_evidence",
        release_manifest_hash=RELEASE_HASH,
        source_record_id="msft-2024-10k-revenue",
        source_url="https://www.sec.gov/Archives/msft-2024.htm",
        statement_text=CURRENT_TEXT,
        evidence_id="msft-revenue-fy2024",
        measurement_value=Decimal("245122000000"),
        measurement_unit="USD",
    )


def prior_authorization() -> AuthorizedCitation:
    return AuthorizedCitation(
        source_type="structured_fact",
        verification_role="verdict_evidence",
        release_manifest_hash=RELEASE_HASH,
        source_record_id="msft-2023-10k-revenue",
        source_url="https://www.sec.gov/Archives/msft-2023.htm",
        statement_text=PRIOR_TEXT,
        evidence_id="msft-revenue-fy2023",
        measurement_value=Decimal("211915000000"),
        measurement_unit="USD",
    )


def narrative_authorization() -> AuthorizedCitation:
    return AuthorizedCitation(
        source_type="narrative_disclosure",
        verification_role="context_only",
        release_manifest_hash=RELEASE_HASH,
        source_record_id="msft-2024-mdna",
        source_url="https://www.sec.gov/Archives/msft-2024.htm",
        statement_text="Microsoft attributed revenue growth partly to its cloud businesses.",
        chunk_hash="f" * 64,
        source_span=(120, 198),
    )


def context() -> ResearchAnswerValidationContext:
    return ResearchAnswerValidationContext(
        task_type="analyze",
        entities=(EntityBinding("0000789019", "company", "Microsoft"),),
        as_of=AS_OF,
        release_bindings=(ReleaseBinding("earnings", "earnings-release-2024", RELEASE_HASH),),
        observed_through=AS_OF,
        authorized_citations=(current_authorization(), prior_authorization()),
        audit_manifest_hash=AUDIT_HASH,
        model_contract=ModelContract(
            provider="approved-provider",
            model_id="pinned-model-v1",
            prompt_contract_hash=PROMPT_HASH,
            tool_contract_hash=TOOL_HASH,
            provider_attempt_id="attempt-001",
        ),
        interpretation_warrants=(
            InterpretationWarrant(
                statement_id="s-analysis",
                text=INTERPRETATION_TEXT,
                derived_from_statement_ids=("s-current", "s-prior", "s-change"),
            ),
        ),
    )


def document() -> dict[str, object]:
    return {
        "schema_version": "research-answer.v1",
        "task_type": "analyze",
        "status": "completed",
        "as_of": AS_OF,
        "entities": [
            {
                "entity_id": "0000789019",
                "entity_type": "company",
                "display_name": "Microsoft",
            }
        ],
        "release_scope": {
            "catalogs": ["earnings"],
            "release_ids": ["earnings-release-2024"],
            "manifest_hashes": [RELEASE_HASH],
            "observed_through": AS_OF,
        },
        "answer": f"{CALCULATION_TEXT}\n\n{INTERPRETATION_TEXT}",
        "answer_statement_ids": ["s-change", "s-analysis"],
        "statements": [
            {
                "statement_id": "s-current",
                "kind": "released_fact",
                "text": CURRENT_TEXT,
                "citation_ids": ["c-current"],
                "derived_from_statement_ids": [],
                "measurement": {"value": "245122000000", "unit": "USD"},
                "calculation": None,
            },
            {
                "statement_id": "s-prior",
                "kind": "released_fact",
                "text": PRIOR_TEXT,
                "citation_ids": ["c-prior"],
                "derived_from_statement_ids": [],
                "measurement": {"value": "211915000000", "unit": "USD"},
                "calculation": None,
            },
            {
                "statement_id": "s-change",
                "kind": "deterministic_calculation",
                "text": CALCULATION_TEXT,
                "citation_ids": [],
                "derived_from_statement_ids": ["s-current", "s-prior"],
                "measurement": None,
                "calculation": {
                    "operation": "percent_change",
                    "inputs": [
                        {"statement_id": "s-current"},
                        {"statement_id": "s-prior"},
                    ],
                    "value": "15.67",
                    "unit": "percent",
                    "decimal_places": 2,
                },
            },
            {
                "statement_id": "s-analysis",
                "kind": "agent_interpretation",
                "text": INTERPRETATION_TEXT,
                "citation_ids": [],
                "derived_from_statement_ids": ["s-current", "s-prior", "s-change"],
                "measurement": None,
                "calculation": None,
            },
        ],
        "citations": [
            {
                "citation_id": "c-current",
                "source_type": "structured_fact",
                "verification_role": "verdict_evidence",
                "release_manifest_hash": RELEASE_HASH,
                "source_record_id": "msft-2024-10k-revenue",
                "source_url": "https://www.sec.gov/Archives/msft-2024.htm",
                "evidence_id": "msft-revenue-fy2024",
                "chunk_hash": None,
                "source_span": None,
            },
            {
                "citation_id": "c-prior",
                "source_type": "structured_fact",
                "verification_role": "verdict_evidence",
                "release_manifest_hash": RELEASE_HASH,
                "source_record_id": "msft-2023-10k-revenue",
                "source_url": "https://www.sec.gov/Archives/msft-2023.htm",
                "evidence_id": "msft-revenue-fy2023",
                "chunk_hash": None,
                "source_span": None,
            },
        ],
        "counterpoint_statement_ids": [],
        "unavailable": [],
        "limitations": [
            "Limited to the declared frozen release; this is not investment advice."
        ],
        "model_contract": {
            "provider": "approved-provider",
            "model_id": "pinned-model-v1",
            "prompt_contract_hash": PROMPT_HASH,
            "tool_contract_hash": TOOL_HASH,
            "provider_attempt_id": "attempt-001",
        },
        "verification_results": [],
        "audit_manifest_hash": AUDIT_HASH,
    }


def assert_failure(
    proposed: dict[str, object],
    expected_code: str,
    *,
    validation_context: ResearchAnswerValidationContext | None = None,
) -> None:
    with pytest.raises(ResearchAnswerValidationError) as captured:
        validate_research_answer(proposed, context=validation_context or context())
    assert captured.value.code == expected_code


def statement(proposed: dict[str, object], statement_id: str) -> dict[str, object]:
    statements = proposed["statements"]
    assert isinstance(statements, list)
    return next(
        item
        for item in statements
        if isinstance(item, dict) and item.get("statement_id") == statement_id
    )


def test_valid_answer_replays_to_a_detached_canonical_snapshot() -> None:
    proposed = document()
    validated = validate_research_answer(proposed, context=context())
    reordered = dict(reversed(list(document().items())))
    replay = validate_research_answer(reordered, context=context())

    proposed["answer"] = "mutated after validation"

    assert validated.content_hash == replay.content_hash
    assert len(validated.content_hash) == 64
    assert validated.to_document()["answer"] == f"{CALCULATION_TEXT}\n\n{INTERPRETATION_TEXT}"


def test_deterministic_only_answer_requires_no_model_or_interpretation_warrant() -> None:
    proposed = document()
    proposed["statements"] = [
        item
        for item in proposed["statements"]  # type: ignore[union-attr]
        if item["statement_id"] != "s-analysis"
    ]
    proposed["answer"] = CALCULATION_TEXT
    proposed["answer_statement_ids"] = ["s-change"]
    proposed["model_contract"] = None
    deterministic_context = replace(
        context(), model_contract=None, interpretation_warrants=()
    )

    validated = validate_research_answer(proposed, context=deterministic_context)

    assert validated.to_document()["model_contract"] is None


def test_unavailable_answer_can_safely_return_only_an_open_question() -> None:
    unavailable_context = replace(
        context(),
        authorized_citations=(),
        model_contract=None,
        interpretation_warrants=(),
    )
    proposed = document()
    question = "What compatible revenue evidence is available in a later approved release?"
    proposed.update(
        {
            "status": "unavailable",
            "answer": question,
            "answer_statement_ids": ["s-question"],
            "statements": [
                {
                    "statement_id": "s-question",
                    "kind": "open_question",
                    "text": question,
                    "citation_ids": [],
                    "derived_from_statement_ids": [],
                    "measurement": None,
                    "calculation": None,
                }
            ],
            "citations": [],
            "unavailable": [
                {
                    "request": "Later compatible revenue period",
                    "reason": "not_released",
                    "detail": "No approved later release is in the admitted scope.",
                }
            ],
            "model_contract": None,
        }
    )

    validated = validate_research_answer(proposed, context=unavailable_context)

    assert validated.to_document()["status"] == "unavailable"


def test_authorized_narrative_is_visible_context_only() -> None:
    proposed = document()
    narrative = narrative_authorization()
    proposed["citations"].append(  # type: ignore[union-attr]
        {
            "citation_id": "c-context",
            "source_type": "narrative_disclosure",
            "verification_role": "context_only",
            "release_manifest_hash": RELEASE_HASH,
            "source_record_id": "msft-2024-mdna",
            "source_url": "https://www.sec.gov/Archives/msft-2024.htm",
            "evidence_id": None,
            "chunk_hash": "f" * 64,
            "source_span": {"start_char": 120, "end_char": 198},
        }
    )
    proposed["statements"].append(  # type: ignore[union-attr]
        {
            "statement_id": "s-context",
            "kind": "narrative_context",
            "text": narrative.statement_text,
            "citation_ids": ["c-context"],
            "derived_from_statement_ids": [],
            "measurement": None,
            "calculation": None,
        }
    )
    proposed["answer_statement_ids"].append("s-context")  # type: ignore[union-attr]
    proposed["answer"] = (
        f"{CALCULATION_TEXT}\n\n{INTERPRETATION_TEXT}\n\n{narrative.statement_text}"
    )

    validated = validate_research_answer(
        proposed,
        context=replace(
            context(),
            authorized_citations=(
                current_authorization(),
                prior_authorization(),
                narrative,
            ),
        ),
    )

    citation = validated.to_document()["citations"][2]  # type: ignore[index]
    assert citation["verification_role"] == "context_only"


def test_answer_is_composed_only_from_selected_validated_statements() -> None:
    proposed = document()
    proposed["answer"] = "An unsupported summary."
    assert_failure(proposed, "answer_composition_mismatch")


def test_duplicate_and_unknown_statement_references_fail_closed() -> None:
    duplicate = document()
    statement(duplicate, "s-prior")["statement_id"] = "s-current"
    assert_failure(duplicate, "duplicate_identifier")

    unknown = document()
    statement(unknown, "s-analysis")["derived_from_statement_ids"] = ["missing"]
    assert_failure(unknown, "unknown_reference")


def test_cyclic_and_unreachable_statements_fail_closed() -> None:
    cyclic = document()
    change = statement(cyclic, "s-change")
    change["derived_from_statement_ids"] = ["s-analysis"]
    change["calculation"]["inputs"] = [{"statement_id": "s-analysis"}]  # type: ignore[index]
    analysis = statement(cyclic, "s-analysis")
    analysis["derived_from_statement_ids"] = ["s-change"]
    assert_failure(cyclic, "cyclic_reference")

    unreachable = document()
    unreachable["statements"].append(  # type: ignore[union-attr]
        {
            "statement_id": "s-orphan",
            "kind": "open_question",
            "text": "What evidence is not present in this release?",
            "citation_ids": [],
            "derived_from_statement_ids": [],
            "measurement": None,
            "calculation": None,
        }
    )
    assert_failure(unreachable, "unreachable_statement")


def test_entity_release_and_audit_scope_cannot_be_broadened_by_the_document() -> None:
    entity = document()
    entity["entities"][0]["entity_id"] = "0000320193"  # type: ignore[index]
    assert_failure(entity, "scope_mismatch")

    release = document()
    release["release_scope"]["release_ids"] = ["different-release"]  # type: ignore[index]
    assert_failure(release, "scope_mismatch")

    audit = document()
    audit["audit_manifest_hash"] = "f" * 64
    assert_failure(audit, "audit_mismatch")


def test_citation_provenance_text_and_measurement_must_be_independently_authorized() -> None:
    provenance = document()
    provenance["citations"][0]["source_record_id"] = "invented-record"  # type: ignore[index]
    assert_failure(provenance, "citation_not_authorized")

    text = document()
    statement(text, "s-current")["text"] = "Microsoft revenue was 999 USD."
    assert_failure(text, "citation_not_authorized")

    measurement = document()
    statement(measurement, "s-current")["measurement"] = {"value": "999", "unit": "USD"}
    assert_failure(measurement, "citation_not_authorized")


def test_narrative_context_can_never_fill_a_released_fact_role() -> None:
    proposed = document()
    narrative = narrative_authorization()
    validation_context = replace(
        context(), authorized_citations=(narrative, prior_authorization())
    )
    proposed["citations"][0] = {  # type: ignore[index]
        "citation_id": "c-current",
        "source_type": "narrative_disclosure",
        "verification_role": "context_only",
        "release_manifest_hash": RELEASE_HASH,
        "source_record_id": "msft-2024-mdna",
        "source_url": "https://www.sec.gov/Archives/msft-2024.htm",
        "evidence_id": None,
        "chunk_hash": "f" * 64,
        "source_span": {"start_char": 120, "end_char": 198},
    }
    current = statement(proposed, "s-current")
    current["text"] = narrative.statement_text
    current["measurement"] = None
    assert_failure(proposed, "citation_role_invalid", validation_context=validation_context)


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("value", "15.68", "calculation_mismatch"),
        ("unit", "ratio", "calculation_mismatch"),
        ("decimal_places", 13, "invalid_value"),
    ],
)
def test_calculation_result_unit_and_precision_must_replay(
    field: str, value: object, expected_code: str
) -> None:
    proposed = document()
    statement(proposed, "s-change")["calculation"][field] = value  # type: ignore[index]
    assert_failure(proposed, expected_code)


def test_calculation_input_order_and_rendered_text_are_contract_bound() -> None:
    order = document()
    change = statement(order, "s-change")
    change["calculation"]["inputs"] = [  # type: ignore[index]
        {"statement_id": "s-prior"},
        {"statement_id": "s-current"},
    ]
    assert_failure(order, "calculation_invalid")

    rendered = document()
    statement(rendered, "s-change")["text"] = "Revenue changed by 15.67%."
    assert_failure(rendered, "calculation_mismatch")


@pytest.mark.parametrize(
    ("operation", "value", "unit", "text"),
    [
        ("sum", "457037000000", "USD", "Calculated sum: 457037000000 USD."),
        (
            "difference",
            "33207000000",
            "USD",
            "Calculated difference: 33207000000 USD.",
        ),
    ],
)
def test_sum_and_difference_operations_replay(
    operation: str, value: str, unit: str, text: str
) -> None:
    proposed = document()
    proposed["statements"] = [
        item
        for item in proposed["statements"]  # type: ignore[union-attr]
        if item["statement_id"] != "s-analysis"
    ]
    calculation_statement = statement(proposed, "s-change")
    calculation_statement["text"] = text
    calculation_statement["calculation"].update(  # type: ignore[union-attr]
        {
            "operation": operation,
            "value": value,
            "unit": unit,
            "decimal_places": 0,
        }
    )
    proposed["answer"] = text
    proposed["answer_statement_ids"] = ["s-change"]
    proposed["model_contract"] = None

    validate_research_answer(
        proposed,
        context=replace(context(), model_contract=None, interpretation_warrants=()),
    )


def test_percentage_point_change_replays_only_percentage_inputs() -> None:
    current_text = "The current released rate was 5.25 percent."
    prior_text = "The baseline released rate was 5.50 percent."
    current = replace(
        current_authorization(),
        statement_text=current_text,
        measurement_value=Decimal("5.25"),
        measurement_unit="percent",
    )
    prior = replace(
        prior_authorization(),
        statement_text=prior_text,
        measurement_value=Decimal("5.50"),
        measurement_unit="percent",
    )
    proposed = document()
    proposed["statements"] = [
        item
        for item in proposed["statements"]  # type: ignore[union-attr]
        if item["statement_id"] != "s-analysis"
    ]
    current_statement = statement(proposed, "s-current")
    current_statement["text"] = current_text
    current_statement["measurement"] = {"value": "5.25", "unit": "percent"}
    prior_statement = statement(proposed, "s-prior")
    prior_statement["text"] = prior_text
    prior_statement["measurement"] = {"value": "5.50", "unit": "percent"}
    calculation_text = "Calculated percentage-point change: -0.25 percentage points."
    calculation_statement = statement(proposed, "s-change")
    calculation_statement["text"] = calculation_text
    calculation_statement["calculation"].update(  # type: ignore[union-attr]
        {
            "operation": "percentage_point_change",
            "value": "-0.25",
            "unit": "percentage_points",
            "decimal_places": 2,
        }
    )
    proposed["answer"] = calculation_text
    proposed["answer_statement_ids"] = ["s-change"]
    proposed["model_contract"] = None

    validate_research_answer(
        proposed,
        context=replace(
            context(),
            authorized_citations=(current, prior),
            model_contract=None,
            interpretation_warrants=(),
        ),
    )


def test_interpretation_requires_an_independent_exact_warrant() -> None:
    proposed = document()
    statement(proposed, "s-analysis")["text"] = "An unwarranted causal explanation."
    proposed["answer"] = f"{CALCULATION_TEXT}\n\nAn unwarranted causal explanation."
    assert_failure(proposed, "interpretation_not_warranted")


def test_model_contract_must_match_the_attributable_provider_attempt() -> None:
    proposed = document()
    proposed["model_contract"]["provider_attempt_id"] = "another-attempt"  # type: ignore[index]
    assert_failure(proposed, "model_contract_mismatch")

    missing = document()
    missing["model_contract"] = None
    assert_failure(missing, "model_contract_mismatch")


def test_verification_results_must_exactly_match_deterministic_verifier_output() -> None:
    result = {
        "claim_id": "revenue-growth",
        "verdict": "verified",
        "authority": "deterministic_verifier",
        "evidence_scope_manifest_hash": RELEASE_HASH,
        "audit_manifest_hash": VERIFIER_AUDIT_HASH,
    }
    proposed = document()
    proposed["verification_results"] = [result]
    expected = VerificationResultBinding(
        claim_id="revenue-growth",
        verdict="verified",
        evidence_scope_manifest_hash=RELEASE_HASH,
        audit_manifest_hash=VERIFIER_AUDIT_HASH,
    )
    validate_research_answer(
        proposed,
        context=replace(context(), verification_results=(expected,)),
    )

    invented = document()
    invented["verification_results"] = [result]
    assert_failure(invented, "verification_authority_mismatch")

    model_verdict = document()
    model_verdict["verification_results"] = [{**result, "authority": "model"}]
    assert_failure(model_verdict, "verification_authority_mismatch")


def test_prohibited_trade_and_advisory_language_is_rejected_even_when_typed() -> None:
    proposed = document()
    analysis = statement(proposed, "s-analysis")
    analysis["kind"] = "open_question"
    analysis["text"] = "Buy Microsoft shares."
    proposed["answer"] = f"{CALCULATION_TEXT}\n\nBuy Microsoft shares."
    assert_failure(proposed, "prohibited_content")


def test_unavailable_status_requires_an_explicit_unavailable_item() -> None:
    proposed = document()
    proposed["status"] = "unavailable"
    assert_failure(proposed, "invalid_shape")


def test_unused_citations_and_non_json_enum_values_fail_with_typed_errors() -> None:
    proposed = document()
    extra = narrative_authorization()
    proposed["citations"].append(  # type: ignore[union-attr]
        {
            "citation_id": "c-unused",
            "source_type": "narrative_disclosure",
            "verification_role": "context_only",
            "release_manifest_hash": RELEASE_HASH,
            "source_record_id": "msft-2024-mdna",
            "source_url": "https://www.sec.gov/Archives/msft-2024.htm",
            "evidence_id": None,
            "chunk_hash": "f" * 64,
            "source_span": {"start_char": 120, "end_char": 198},
        }
    )
    assert_failure(
        proposed,
        "unused_citation",
        validation_context=replace(
            context(),
            authorized_citations=(current_authorization(), prior_authorization(), extra),
        ),
    )

    malformed = document()
    malformed["status"] = ["completed"]
    assert_failure(malformed, "invalid_value")


def test_independent_context_is_immutable_typed_and_release_bound() -> None:
    with pytest.raises(ResearchAnswerValidationError) as mutable:
        replace(context(), authorized_citations=list(context().authorized_citations))  # type: ignore[arg-type]
    assert mutable.value.code == "invalid_context"

    with pytest.raises(ResearchAnswerValidationError) as outside_scope:
        replace(
            context(),
            authorized_citations=(
                replace(current_authorization(), release_manifest_hash="f" * 64),
            ),
        )
    assert outside_scope.value.code == "invalid_context"
