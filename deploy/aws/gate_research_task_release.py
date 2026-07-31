"""Compile a canonical offline approval record for one frozen evidence release."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

from quantify.aws_lambda import S3SignedPolicyArtifactLoader
from quantify.policy_control import ArtifactKind, ReleaseGatePolicy
from quantify.release_factory import build_evidence_release
from quantify.release_operations import ReleaseEvaluation, ReleaseLane, ReviewerApproval, SourceValidation, gate_release


def _object(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"release-gate input is unreadable: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"release-gate input must be an object: {path.name}")
    return value


def _release(*, fixtures_directory: Path, declaration_path: Path):
    declaration = _object(declaration_path)
    try:
        return build_evidence_release(
            fixtures_directory=fixtures_directory,
            release_id=str(declaration["release_id"]),
            issuer_ciks=tuple(declaration["issuer_ciks"]),
            evaluation_corpus=fixtures_directory / str(declaration["evaluation_corpus"]),
            source_policy_version=str(declaration["source_policy_version"]),
            eligibility_policy_version=str(declaration["eligibility_policy_version"]),
            restatement_policy_version=str(declaration["restatement_policy_version"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("release declaration is invalid") from error


def _sources(path: Path) -> tuple[SourceValidation, ...]:
    payload = _object(path)
    values = payload.get("sources")
    if payload.get("schema_version") != "1.0.0" or not isinstance(values, list):
        raise ValueError("source-validation input has an invalid schema")
    try:
        sources = tuple(SourceValidation(**value) for value in values if isinstance(value, dict))
    except (TypeError, ValueError) as error:
        raise ValueError("source-validation input is invalid") from error
    if len(sources) != len(values) or not sources:
        raise ValueError("source-validation input is invalid")
    return sources


def _evaluation(path: Path) -> ReleaseEvaluation:
    payload = _object(path)
    if set(payload) != {"automated_pass_rate_basis_points", "review_exception_rate_basis_points", "correction_rate_basis_points"}:
        raise ValueError("release evaluation input has an invalid schema")
    try:
        return ReleaseEvaluation(**payload)
    except (TypeError, ValueError) as error:
        raise ValueError("release evaluation input is invalid") from error


def _policy(path: Path) -> ReleaseGatePolicy:
    artifact = S3SignedPolicyArtifactLoader._artifact_from_payload(kind=ArtifactKind.RELEASE_GATE_POLICY, payload=_object(path))
    assert isinstance(artifact, ReleaseGatePolicy)
    return artifact


def _reviewer(path: Path | None) -> ReviewerApproval | None:
    if path is None:
        return None
    try:
        return ReviewerApproval(**_object(path))
    except (TypeError, ValueError) as error:
        raise ValueError("reviewer approval input is invalid") from error


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures-directory", type=Path, required=True)
    parser.add_argument("--release-declaration", type=Path, required=True)
    parser.add_argument("--source-validations", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--release-gate-policy", type=Path, required=True)
    parser.add_argument("--lane", choices=[lane.value for lane in ReleaseLane], required=True)
    parser.add_argument("--reviewer-approval", type=Path)
    parser.add_argument("--approval-output", type=Path)
    args = parser.parse_args(argv)
    record = gate_release(
        release=_release(fixtures_directory=args.fixtures_directory, declaration_path=args.release_declaration),
        sources=_sources(args.source_validations),
        evaluation=_evaluation(args.evaluation),
        policy=_policy(args.release_gate_policy),
        lane=ReleaseLane(args.lane),
        reviewer=_reviewer(args.reviewer_approval),
    )
    serialized = json.dumps(record.as_dict(), sort_keys=True, separators=(",", ":"))
    if args.approval_output is not None:
        try:
            with args.approval_output.open("x", encoding="utf-8") as output:
                output.write(serialized)
                output.write("\n")
        except FileExistsError as error:
            raise ValueError("release approval output already exists") from error
    print(serialized)
    if not record.approved:
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as error:
        print(f"Quantify research-task release gate failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
