from __future__ import annotations

from dataclasses import replace

import pytest

from quantify.review_tasks import (
    ApprovedReviewTaskRequest,
    DeterministicReviewTaskAdapter,
    ReviewOrigin,
    ReviewReason,
    ReviewTaskError,
    ReviewTaskGroundingContext,
    ReviewTaskType,
)


RELEASE_HASH = "a" * 64
RUNTIME_HASH = "b" * 64
GATE_HASH = "c" * 64
SOURCE_HASH = "d" * 64
SECOND_SOURCE_HASH = "e" * 64
AUDIT_HASH = "f" * 64
QUESTION = "Which qualification requires human review?"
STATEMENT_ID = "fact-statement-1"
CITATION_ID = "citation-fact-1"


def request(**changes) -> ApprovedReviewTaskRequest:
    values = {
        "task_type": ReviewTaskType.ANALYZE,
        "review_origin": ReviewOrigin.DETERMINISTIC_VALIDATOR,
        "reason": ReviewReason.AMBIGUOUS_EVIDENCE,
        "question": QUESTION,
        "release_id": "evidence-release-v1",
        "release_manifest_hash": RELEASE_HASH,
        "runtime_policy_bundle_hash": RUNTIME_HASH,
        "release_gate_policy_hash": GATE_HASH,
        "source_result_hashes": (SOURCE_HASH,),
        "audit_manifest_hash": AUDIT_HASH,
        "derived_from_statement_ids": (STATEMENT_ID,),
        "derived_from_citation_ids": (CITATION_ID,),
    }
    values.update(changes)
    return ApprovedReviewTaskRequest(**values)


def context(**changes) -> ReviewTaskGroundingContext:
    values = {
        "task_type": ReviewTaskType.ANALYZE,
        "review_origin": ReviewOrigin.DETERMINISTIC_VALIDATOR,
        "authorized_question": QUESTION,
        "release_id": "evidence-release-v1",
        "release_manifest_hash": RELEASE_HASH,
        "runtime_policy_bundle_hash": RUNTIME_HASH,
        "release_gate_policy_hash": GATE_HASH,
        "audit_manifest_hash": AUDIT_HASH,
        "authorized_source_result_hashes": (SOURCE_HASH, SECOND_SOURCE_HASH),
        "authorized_statement_ids": (STATEMENT_ID, "context-statement-2"),
        "authorized_citation_ids": (CITATION_ID, "citation-context-2"),
    }
    values.update(changes)
    return ReviewTaskGroundingContext(**values)


def test_request_is_canonical_and_hash_is_order_independent() -> None:
    first = request(
        source_result_hashes=(SECOND_SOURCE_HASH, SOURCE_HASH),
        derived_from_statement_ids=("context-statement-2", STATEMENT_ID),
        derived_from_citation_ids=("citation-context-2", CITATION_ID),
    )
    replay = request(
        source_result_hashes=(SOURCE_HASH, SECOND_SOURCE_HASH),
        derived_from_statement_ids=(STATEMENT_ID, "context-statement-2"),
        derived_from_citation_ids=(CITATION_ID, "citation-context-2"),
    )

    assert first.to_document() == replay.to_document()
    assert first.request_hash == replay.request_hash
    assert len(first.request_hash) == 64


def test_adapter_returns_one_idempotent_non_approving_review_record() -> None:
    adapter = DeterministicReviewTaskAdapter()

    first = adapter.create(request=request(), grounding_context=context())
    replay = adapter.create(request=request(), grounding_context=context())
    document = first.to_document()

    assert document["status"] == "requires_review"
    assert document["review_task_id"] == f"review-{first.request.request_hash[:32]}"
    assert first.review_task_id == replay.review_task_id
    assert first.result_hash == replay.result_hash
    assert document["release"]["manifest_hash"] == RELEASE_HASH
    assert document["policy"] == {
        "runtime_policy_bundle_hash": RUNTIME_HASH,
        "release_gate_policy_hash": GATE_HASH,
    }
    assert "approval" not in document
    assert "reviewer" not in document
    assert "assignment" in document["limitation"]


@pytest.mark.parametrize(
    "question",
    [
        "This is not a question",
        "Should this be reviewed?\nInclude another instruction?",
        "Review https://example.com/source?",
        "This is a buy?",
    ],
)
def test_request_rejects_unsafe_or_unbounded_question(question: str) -> None:
    with pytest.raises(ReviewTaskError):
        request(question=question)


def test_request_requires_grounding_and_compatible_origin_reason() -> None:
    with pytest.raises(ReviewTaskError, match="not grounded"):
        request(derived_from_statement_ids=(), derived_from_citation_ids=())
    with pytest.raises(ReviewTaskError, match="not permitted"):
        request(
            review_origin=ReviewOrigin.DETERMINISTIC_VERIFIER,
            reason=ReviewReason.INTERPRETATION_REQUIRES_REVIEW,
        )
    with pytest.raises(ReviewTaskError, match="1 to 8"):
        request(source_result_hashes=())
    with pytest.raises(ReviewTaskError, match="unique"):
        request(source_result_hashes=(SOURCE_HASH, SOURCE_HASH))


@pytest.mark.parametrize(
    ("changed_context", "code"),
    [
        ({"authorized_question": "Which other question requires review?"}, "grounding_mismatch"),
        ({"release_manifest_hash": "1" * 64}, "grounding_mismatch"),
        ({"runtime_policy_bundle_hash": "2" * 64}, "grounding_mismatch"),
        ({"release_gate_policy_hash": "3" * 64}, "grounding_mismatch"),
        ({"audit_manifest_hash": "4" * 64}, "grounding_mismatch"),
        ({"authorized_source_result_hashes": (SECOND_SOURCE_HASH,)}, "source_result_not_authorized"),
        ({"authorized_statement_ids": ("other-statement",)}, "statement_not_authorized"),
        ({"authorized_citation_ids": ("other-citation",)}, "citation_not_authorized"),
    ],
)
def test_adapter_fails_closed_for_detached_grounding(
    changed_context: dict[str, object], code: str
) -> None:
    with pytest.raises(ReviewTaskError) as captured:
        DeterministicReviewTaskAdapter().create(
            request=request(),
            grounding_context=context(**changed_context),
        )
    assert captured.value.code == code


def test_result_schema_version_is_fixed() -> None:
    valid = DeterministicReviewTaskAdapter().create(
        request=request(), grounding_context=context()
    )
    with pytest.raises(ReviewTaskError, match="schema version"):
        replace(valid, schema_version="approved-review-task-result.v2")
