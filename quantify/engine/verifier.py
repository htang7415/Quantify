"""Pure local-warrant and counterevidence verification."""

from __future__ import annotations

from decimal import Decimal, localcontext

from .measurement import build_upper_baseline_calibration
from .schemas import (
    EvidenceSnapshot,
    EvidenceValue,
    MeasurementMode,
    MetricBaselineClaim,
    MetricComparisonClaim,
    MetricThresholdClaim,
    Relation,
    VerificationOutcome,
    VerificationResult,
)


def _satisfies(*, value: object, relation: Relation, threshold: object) -> bool:
    if relation is Relation.GREATER_THAN:
        return value > threshold
    if relation is Relation.LESS_THAN:
        return value < threshold
    raise ValueError(f"unsupported relation: {relation}")


def _threshold_defeats(*, evidence: EvidenceValue, claim: MetricThresholdClaim) -> bool:
    return not _satisfies(
        value=evidence.value,
        relation=claim.relation,
        threshold=claim.threshold,
    )


def _result(
    *,
    claim_id: str,
    outcome: VerificationOutcome,
    cited_evidence_ids: tuple[str, ...],
    counterevidence_evidence_ids: tuple[str, ...] = (),
    measurement_mode: MeasurementMode = MeasurementMode.EXACT,
    calibrated_distance: Decimal | None = None,
    calibration_id: str | None = None,
) -> VerificationResult:
    return VerificationResult(
        claim_id=claim_id,
        outcome=outcome,
        cited_evidence_ids=cited_evidence_ids,
        counterevidence_evidence_ids=counterevidence_evidence_ids,
        measurement_mode=measurement_mode,
        calibrated_distance=calibrated_distance,
        calibration_id=calibration_id,
    )


def _verify_threshold_claim(
    *, snapshot: EvidenceSnapshot, claim: MetricThresholdClaim
) -> VerificationResult:
    """Return a deterministic pre-disclosure verification outcome.

    A claim is unsupported when its cited fact is absent, ineligible, or does
    not satisfy the typed relation. A locally warranted claim receives a
    counterevidence outcome only when another eligible fact has identical
    semantic identity and directly fails that same relation.

    Disclosure assessment is intentionally outside this pure function; a later
    layer can compose a final ``DEFEATED`` or ``QUALIFIED`` verdict.
    """

    cited = snapshot.evidence_by_id(claim.cited_evidence_id)
    if (
        claim.relation not in (Relation.GREATER_THAN, Relation.LESS_THAN)
        or cited is None
        or not cited.eligible
    ):
        return _result(
            claim_id=claim.claim_id,
            outcome=VerificationOutcome.UNSUPPORTED,
            cited_evidence_ids=(claim.cited_evidence_id,),
        )

    if not _satisfies(
        value=cited.value, relation=claim.relation, threshold=claim.threshold
    ):
        return _result(
            claim_id=claim.claim_id,
            outcome=VerificationOutcome.UNSUPPORTED,
            cited_evidence_ids=(claim.cited_evidence_id,),
        )

    counterevidence_ids = tuple(
        item.evidence_id
        for item in snapshot.evidence
        if (
            item.evidence_id != cited.evidence_id
            and item.eligible
            and item.semantic_key == cited.semantic_key
            and _threshold_defeats(evidence=item, claim=claim)
        )
    )
    if counterevidence_ids:
        return _result(
            claim_id=claim.claim_id,
            outcome=VerificationOutcome.COUNTEREVIDENCE,
            cited_evidence_ids=(cited.evidence_id,),
            counterevidence_evidence_ids=counterevidence_ids,
        )

    return _result(
        claim_id=claim.claim_id,
        outcome=VerificationOutcome.VERIFIED,
        cited_evidence_ids=(cited.evidence_id,),
    )


def _verify_comparison_claim(
    *, snapshot: EvidenceSnapshot, claim: MetricComparisonClaim
) -> VerificationResult:
    cited_ids = (claim.left_evidence_id, claim.right_evidence_id)
    left = snapshot.evidence_by_id(claim.left_evidence_id)
    right = snapshot.evidence_by_id(claim.right_evidence_id)
    if (
        claim.relation not in (Relation.GREATER_THAN, Relation.LESS_THAN)
        or
        left is None
        or right is None
        or not left.eligible
        or not right.eligible
        or left.comparability_key != right.comparability_key
        or left.period_end == right.period_end
    ):
        return _result(
            claim_id=claim.claim_id,
            outcome=VerificationOutcome.UNSUPPORTED,
            cited_evidence_ids=cited_ids,
        )

    if not _satisfies(value=left.value, relation=claim.relation, threshold=right.value):
        return _result(
            claim_id=claim.claim_id,
            outcome=VerificationOutcome.UNSUPPORTED,
            cited_evidence_ids=cited_ids,
        )

    left_candidates = tuple(
        item
        for item in snapshot.evidence
        if item.eligible and item.semantic_key == left.semantic_key
    )
    right_candidates = tuple(
        item
        for item in snapshot.evidence
        if item.eligible and item.semantic_key == right.semantic_key
    )
    defeating_ids: set[str] = set()
    for candidate_left in left_candidates:
        for candidate_right in right_candidates:
            if (
                candidate_left.evidence_id == left.evidence_id
                and candidate_right.evidence_id == right.evidence_id
            ):
                continue
            if not _satisfies(
                value=candidate_left.value,
                relation=claim.relation,
                threshold=candidate_right.value,
            ):
                if candidate_left.evidence_id != left.evidence_id:
                    defeating_ids.add(candidate_left.evidence_id)
                if candidate_right.evidence_id != right.evidence_id:
                    defeating_ids.add(candidate_right.evidence_id)

    if defeating_ids:
        return _result(
            claim_id=claim.claim_id,
            outcome=VerificationOutcome.COUNTEREVIDENCE,
            cited_evidence_ids=cited_ids,
            counterevidence_evidence_ids=tuple(sorted(defeating_ids)),
        )

    return _result(
        claim_id=claim.claim_id,
        outcome=VerificationOutcome.VERIFIED,
        cited_evidence_ids=cited_ids,
    )


def _calibrated_distance(*, value: Decimal, baseline: Decimal, scale: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 28
        distance = (value - baseline) / scale
    return max(Decimal("0"), min(Decimal("1"), distance))


def _verify_baseline_claim(
    *, snapshot: EvidenceSnapshot, claim: MetricBaselineClaim
) -> VerificationResult:
    cited = snapshot.evidence_by_id(claim.cited_evidence_id)
    if (
        claim.relation is not Relation.OUTSIDE_UPPER_BASELINE
        or cited is None
        or not cited.eligible
        or cited.period_end <= claim.calibration.historical_cutoff
    ):
        return _result(
            claim_id=claim.claim_id,
            outcome=VerificationOutcome.UNSUPPORTED,
            cited_evidence_ids=claim.cited_evidence_ids,
            measurement_mode=MeasurementMode.CALIBRATED_DISTANCE,
        )

    try:
        expected = build_upper_baseline_calibration(
            snapshot=snapshot,
            historical_evidence_ids=claim.calibration.historical_evidence_ids,
            historical_cutoff=claim.calibration.historical_cutoff,
            method=claim.calibration.method,
        )
    except ValueError:
        return _result(
            claim_id=claim.claim_id,
            outcome=VerificationOutcome.UNSUPPORTED,
            cited_evidence_ids=claim.cited_evidence_ids,
            measurement_mode=MeasurementMode.CALIBRATED_DISTANCE,
        )

    if expected != claim.calibration or cited.comparability_key != snapshot.evidence_by_id(
        expected.historical_evidence_ids[0]
    ).comparability_key:
        return _result(
            claim_id=claim.claim_id,
            outcome=VerificationOutcome.UNSUPPORTED,
            cited_evidence_ids=claim.cited_evidence_ids,
            measurement_mode=MeasurementMode.CALIBRATED_DISTANCE,
        )

    distance = _calibrated_distance(
        value=cited.value,
        baseline=expected.upper_baseline,
        scale=expected.scale_value,
    )
    if cited.value <= expected.upper_baseline:
        return _result(
            claim_id=claim.claim_id,
            outcome=VerificationOutcome.UNSUPPORTED,
            cited_evidence_ids=claim.cited_evidence_ids,
            measurement_mode=MeasurementMode.CALIBRATED_DISTANCE,
            calibrated_distance=distance,
            calibration_id=expected.calibration_id,
        )

    counterevidence_ids = tuple(
        item.evidence_id
        for item in snapshot.evidence
        if (
            item.evidence_id != cited.evidence_id
            and item.eligible
            and item.semantic_key == cited.semantic_key
            and item.value <= expected.upper_baseline
        )
    )
    return _result(
        claim_id=claim.claim_id,
        outcome=(
            VerificationOutcome.COUNTEREVIDENCE
            if counterevidence_ids
            else VerificationOutcome.VERIFIED
        ),
        cited_evidence_ids=claim.cited_evidence_ids,
        counterevidence_evidence_ids=counterevidence_ids,
        measurement_mode=MeasurementMode.CALIBRATED_DISTANCE,
        calibrated_distance=distance,
        calibration_id=expected.calibration_id,
    )


def verify_claim(
    *, snapshot: EvidenceSnapshot, claim: MetricThresholdClaim | MetricComparisonClaim | MetricBaselineClaim
) -> VerificationResult:
    """Return a deterministic pre-disclosure verification outcome.

    A claim is unsupported when its cited fact or facts are absent, ineligible,
    incompatible, or do not satisfy its typed relation. A locally warranted
    claim receives a counterevidence outcome only when another eligible fact in
    the same semantic slot directly fails that relation.

    Disclosure assessment is intentionally outside this pure function; a later
    layer can compose a final ``DEFEATED`` or ``QUALIFIED`` verdict.
    """

    if isinstance(claim, MetricThresholdClaim):
        return _verify_threshold_claim(snapshot=snapshot, claim=claim)
    if isinstance(claim, MetricComparisonClaim):
        return _verify_comparison_claim(snapshot=snapshot, claim=claim)
    if isinstance(claim, MetricBaselineClaim):
        return _verify_baseline_claim(snapshot=snapshot, claim=claim)
    raise TypeError(f"unsupported claim type: {type(claim).__name__}")
