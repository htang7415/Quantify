from __future__ import annotations

from decimal import Decimal

import pytest

from quantify.engine import (
    ClaimVerdict,
    ClaimAnalysisResult,
    CounterevidencePair,
    DisclosureAssessment,
    DisclosureStatus,
    MetricThresholdClaim,
    LocalWarrantResult,
    Relation,
    analyze_claims,
    compose_claim_verdicts,
)
from tests.conftest import load_snapshot


def _countered_analysis():
    snapshot = load_snapshot("quantum_revenue_restatement.json", allow_conflicting_evidence=True)
    claim = MetricThresholdClaim(
        claim_id="countered",
        cited_evidence_id="qtm-revenue-fy2023-as-filed",
        relation=Relation.LESS_THAN,
        threshold=Decimal("415000000"),
    )
    return analyze_claims(snapshot=snapshot, claims=(claim,))


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (DisclosureStatus.NOT_DISCLOSED, ClaimVerdict.DEFEATED),
        (DisclosureStatus.DISCLOSED_SAME_SENTENCE, ClaimVerdict.QUALIFIED),
        (DisclosureStatus.DISCLOSED_ELSEWHERE, ClaimVerdict.QUALIFIED),
        (DisclosureStatus.AMBIGUOUS, ClaimVerdict.REQUIRES_AGENT_RESOLUTION),
    ],
)
def test_composes_counterevidence_using_disclosure_status(status, expected) -> None:
    results = compose_claim_verdicts(
        analysis=_countered_analysis(),
        disclosure_assessments=(
            DisclosureAssessment(
                claim_id="countered",
                defeating_evidence_id="qtm-revenue-fy2023-restated",
                status=status,
            ),
        ),
    )

    assert results[0].verdict is expected
    assert results[0].counterevidence_detail[0].disclosure_status is status


def test_missing_disclosure_assessment_requires_agent_resolution() -> None:
    assert compose_claim_verdicts(
        analysis=_countered_analysis(), disclosure_assessments=()
    )[0].verdict is ClaimVerdict.REQUIRES_AGENT_RESOLUTION


def test_rejects_assessment_for_non_ce1_pair() -> None:
    with pytest.raises(ValueError, match="non-CE1"):
        compose_claim_verdicts(
            analysis=_countered_analysis(),
            disclosure_assessments=(
                DisclosureAssessment(
                    claim_id="countered",
                    defeating_evidence_id="not-in-analysis",
                    status=DisclosureStatus.NOT_DISCLOSED,
                ),
            ),
        )


def test_mixed_disclosure_remains_qualified_without_an_omission_accusation() -> None:
    analysis = ClaimAnalysisResult(
        local_warrants=(
            LocalWarrantResult(
                claim_id="mixed",
                passed=True,
                cited_evidence_ids=("cited",),
            ),
        ),
        counterevidence_pairs=(
            CounterevidencePair(claim_id="mixed", evidence_id="defeating-disclosed"),
            CounterevidencePair(claim_id="mixed", evidence_id="defeating-undisclosed"),
        ),
    )

    result = compose_claim_verdicts(
        analysis=analysis,
        disclosure_assessments=(
            DisclosureAssessment(
                claim_id="mixed",
                defeating_evidence_id="defeating-disclosed",
                status=DisclosureStatus.DISCLOSED_ELSEWHERE,
            ),
            DisclosureAssessment(
                claim_id="mixed",
                defeating_evidence_id="defeating-undisclosed",
                status=DisclosureStatus.NOT_DISCLOSED,
            ),
        ),
    )

    assert result[0].verdict is ClaimVerdict.QUALIFIED
    assert [detail.disclosure_status for detail in result[0].counterevidence_detail] == [
        DisclosureStatus.DISCLOSED_ELSEWHERE,
        DisclosureStatus.NOT_DISCLOSED,
    ]
