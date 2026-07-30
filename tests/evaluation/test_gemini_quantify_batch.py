from __future__ import annotations

import json
from pathlib import Path

from quantify.engine import (
    MetricBaselineClaim,
    MetricComparisonClaim,
    MetricThresholdClaim,
)
from quantify.evaluation import load_evaluation_model_profile, load_frozen_case_set
from quantify.evaluation.gemini_quantify_batch import (
    GeminiQuantifyBatchClient,
    build_quantify_parity_worklist,
    quantify_outcome_artifact_as_dict,
)


ROOT = Path(__file__).parents[2]
CASE_ROOT = ROOT / "fixtures" / "cases"
SNAPSHOT_ROOT = ROOT / "fixtures" / "sec"
PROFILE = ROOT / "fixtures" / "evaluation" / "gemini_3_1_flash_lite_batch_v1.json"


def _cases():
    return (
        load_frozen_case_set(
            path=CASE_ROOT / "mechanical_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
        load_frozen_case_set(
            path=CASE_ROOT / "judgment_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
    )


class _Transport:
    def __init__(self, worklist) -> None:
        self.worklist = worklist
        self.url = ""
        self.headers: dict[str, str] = {}
        self.body: dict = {}

    def post_json(self, *, url: str, headers: dict[str, str], body: dict) -> dict:
        self.url = url
        self.headers = headers
        self.body = body
        return {"name": "batches/quantify-fixture-123"}

    def get_json(self, *, url: str, headers: dict[str, str]) -> dict:
        self.url = url
        self.headers = headers
        return _successful_batch_response(self.worklist)


def test_submits_public_facts_without_private_labels_and_verifies_locally() -> None:
    mechanical, judgment = _cases()
    worklist = build_quantify_parity_worklist(
        mechanical_cases=mechanical, judgment_cases=judgment
    )
    transport = _Transport(worklist)
    client = GeminiQuantifyBatchClient(api_key="test-key", transport=transport)
    profile = load_evaluation_model_profile(path=PROFILE)

    submission = client.submit(profile=profile, worklist=worklist)
    serialized = json.dumps(transport.body, sort_keys=True)
    result = client.collect(
        batch_name=submission.batch_name, profile=profile, worklist=worklist
    )
    artifact = quantify_outcome_artifact_as_dict(outcomes=result)

    assert submission.estimated_total_cost_usd == 0.06912
    assert transport.url.endswith("/batches/quantify-fixture-123")
    assert len(transport.body["batch"]["input_config"]["requests"]["requests"]) == 30
    assert "case_id" not in serialized
    assert "expected_outcome" not in serialized
    assert "expected_verdict" not in serialized
    assert "disclosure_assessment" not in serialized
    assert artifact["path"] == "quantify"
    assert len(artifact["run"]["prompt_hash"]) == 64
    assert dict(result.outcomes) == {
        item.request_id: _expected_outcome(worklist.case_for(request_id=item.request_id))
        for item in worklist.items
    }


def test_invalid_model_claim_fails_closed_to_unclassified() -> None:
    mechanical, judgment = _cases()
    worklist = build_quantify_parity_worklist(
        mechanical_cases=mechanical, judgment_cases=judgment
    )

    class _InvalidProposalTransport(_Transport):
        def get_json(self, *, url: str, headers: dict[str, str]) -> dict:
            payload = _successful_batch_response(self.worklist)
            payload["response"]["inlinedResponses"][0]["response"]["candidates"][0][
                "content"
            ]["parts"][0]["text"] = json.dumps(
                {"classification": "classified", "claim_type": "threshold"}
            )
            return payload

    result = GeminiQuantifyBatchClient(
        api_key="test-key", transport=_InvalidProposalTransport(worklist)
    ).collect(
        batch_name="batches/quantify-fixture-123",
        profile=load_evaluation_model_profile(path=PROFILE),
        worklist=worklist,
    )

    assert result.outcomes[0][1] == "unclassified"


def _successful_batch_response(worklist) -> dict:
    return {
        "metadata": {"state": "BATCH_STATE_SUCCEEDED"},
        "response": {
            "inlinedResponses": [
                {
                    "metadata": {"key": item.request_id},
                    "response": {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "text": json.dumps(
                                                _proposal(
                                                    worklist.case_for(
                                                        request_id=item.request_id
                                                    )
                                                )
                                            )
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                }
                for item in worklist.items
            ]
        },
    }


def _proposal(case) -> dict:
    if case.expected_unclassified_statement_ids:
        return {
            "statements": [
                {
                    "classification": "unclassified",
                    "report_span_id": "report-s1",
                    "claim_type": "none",
                }
            ]
        }
    claim = case.extraction.statements[0].claims[0]
    if isinstance(claim, MetricThresholdClaim):
        statement = {
            "classification": "classified",
            "report_span_id": "report-s1",
            "claim_type": "threshold",
            "relation": claim.relation.value,
            "cited_evidence_id": claim.cited_evidence_id,
            "threshold": str(claim.threshold),
        }
    elif isinstance(claim, MetricComparisonClaim):
        statement = {
            "classification": "classified",
            "report_span_id": "report-s1",
            "claim_type": "comparison",
            "relation": claim.relation.value,
            "left_evidence_id": claim.left_evidence_id,
            "right_evidence_id": claim.right_evidence_id,
        }
    else:
        assert isinstance(claim, MetricBaselineClaim)
        statement = {
            "classification": "classified",
            "report_span_id": "report-s1",
            "claim_type": "baseline",
            "relation": claim.relation.value,
            "cited_evidence_id": claim.cited_evidence_id,
            "historical_evidence_ids": list(claim.calibration.historical_evidence_ids),
            "historical_cutoff": claim.calibration.historical_cutoff.isoformat(),
        }
    return {"statements": [statement]}


def _expected_outcome(case) -> str:
    if case.expected_unclassified_statement_ids:
        return "unclassified"
    return case.expected_verdicts[0][1].value
