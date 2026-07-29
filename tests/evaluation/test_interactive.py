from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from quantify.evaluation import (
    InteractiveRuntimeAuthorization,
    compile_interactive_runtime_artifact,
    RepeatedRunPathStability,
    RepeatedRunStability,
    interactive_runtime_artifact_as_dict,
    interactive_runtime_trial_as_dict,
    load_interactive_runtime_trial,
    evaluate_interactive_repeated_run_stability,
    load_operational_measurements,
    repeated_run_stability_hash,
    run_interactive_runtime_evaluation,
    run_interactive_runtime_trial,
)
from quantify.evaluation.corpus import load_frozen_case_set
from quantify.evaluation.interactive_cli import main as interactive_main
from quantify.evaluation.interactive_stability_cli import main as stability_main
from quantify.evaluation.interactive_trial_cli import main as trial_main
from quantify.harness import GeminiExtractionConfig


ROOT = Path(__file__).parents[2]
CASE_ROOT = ROOT / "fixtures" / "cases"
SNAPSHOT_ROOT = ROOT / "fixtures" / "sec"
PROMPT_HASH = "a" * 64


def _cases() -> tuple[tuple, tuple]:
    return (
        load_frozen_case_set(
            path=CASE_ROOT / "mechanical_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
        load_frozen_case_set(
            path=CASE_ROOT / "judgment_v1.json", snapshot_root=SNAPSHOT_ROOT
        ),
    )


def _stability(
    *, prompt_hash: str = PROMPT_HASH, model: str = "gemini-test"
) -> RepeatedRunStability:
    path = RepeatedRunPathStability(
        model=model, prompt_hash=prompt_hash, temperature=0.0,
        exact_report_level_agreement=True, statement_level_agreement=1.0,
        classified_unclassified_transitions=0, verified_defeated_flips=0,
        mechanical_verified_defeated_flips=0,
    )
    return RepeatedRunStability(
        artifact_version="1.0.0", case_count=30, trial_count=2,
        prompt_only=path, quantify=path,
    )


def _authorization(*, maximum_request_cost: float = 0.01) -> InteractiveRuntimeAuthorization:
    return InteractiveRuntimeAuthorization(
        authorization_version="1.0.0", provider="google", model="gemini-test",
        temperature=0.0, prompt_hash=PROMPT_HASH, request_timeout_seconds=4.0,
        max_total_cost_usd=0.30, max_request_cost_usd=maximum_request_cost,
    )


class _Extractor:
    def __init__(self, *, cost: float = 0.001) -> None:
        self.calls: list[str] = []
        self.cost = cost

    def extract(self, *, report_text, snapshot):
        self.calls.append(snapshot.snapshot_id)
        # The frozen extractor result makes this test completely offline.  The
        # runtime evaluator must not use case labels or gold disclosures.
        case = next(
            item
            for item in (*_cases()[0], *_cases()[1])
            if item.snapshot.snapshot_id == snapshot.snapshot_id
            and item.report_text == report_text
        )
        return replace(
            case.extraction,
            extractor_version="gemini-test-1.0.0",
            input_tokens=100,
            output_tokens=10,
            total_cost=self.cost,
        )


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        result = self.value
        self.value += 0.25
        return result


def test_interactive_runtime_runs_exact_frozen_corpus_and_emits_replayable_artifact(
    tmp_path: Path,
) -> None:
    mechanical, judgment = _cases()
    extractor = _Extractor()
    measurement = run_interactive_runtime_evaluation(
        mechanical_cases=mechanical,
        judgment_cases=judgment,
        extractor=extractor,
        authorization=_authorization(),
        stability=_stability(),
        clock=_Clock(),
    )

    assert len(extractor.calls) == 30
    assert {item.case_id for item in measurement.cases} == {
        item.case_id for item in (*mechanical, *judgment)
    }
    assert all(item.end_to_end_request_seconds == 0.25 for item in measurement.cases)
    artifact = interactive_runtime_artifact_as_dict(measurement=measurement)
    assert artifact["provenance"]["execution_mode"] == "interactive_runtime"
    assert artifact["measurements"] == {
        "verified_defeated_flips": 0,
        "latency_seconds": 0.25,
        "cost_per_report": pytest.approx(0.001),
        "sec_insufficiency_count": 0,
    }
    serialized = json.dumps(artifact, sort_keys=True)
    assert "expected_outcome" not in serialized
    assert "GEMINI_API_KEY" not in serialized

    path = tmp_path / "interactive.json"
    path.write_text(json.dumps(artifact))
    loaded = load_operational_measurements(path=path)
    assert loaded.latency_seconds == 0.25
    assert loaded.cost_per_report == pytest.approx(0.001)
    assert loaded.stability_artifact_hash == repeated_run_stability_hash(
        stability=_stability()
    )


def test_interactive_runtime_refuses_tampered_or_incomplete_artifacts(tmp_path: Path) -> None:
    mechanical, judgment = _cases()
    measurement = run_interactive_runtime_evaluation(
        mechanical_cases=mechanical, judgment_cases=judgment, extractor=_Extractor(),
        authorization=_authorization(), stability=_stability(), clock=_Clock(),
    )
    artifact = interactive_runtime_artifact_as_dict(measurement=measurement)
    artifact["cases"][0]["total_cost_usd"] = 0.25
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(artifact))
    with pytest.raises(ValueError, match="run hash"):
        load_operational_measurements(path=path)

    artifact = interactive_runtime_artifact_as_dict(measurement=measurement)
    artifact["measurements"]["latency_seconds"] = 9.0
    unsigned = {key: value for key, value in artifact.items() if key != "run_hash"}
    artifact["run_hash"] = sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.write_text(json.dumps(artifact))
    with pytest.raises(ValueError, match="measurements are invalid"):
        load_operational_measurements(path=path)


def test_interactive_runtime_requires_matching_stability_and_stays_within_cap() -> None:
    mechanical, judgment = _cases()
    with pytest.raises(ValueError, match="must match stability metadata"):
        run_interactive_runtime_evaluation(
            mechanical_cases=mechanical, judgment_cases=judgment, extractor=_Extractor(),
            authorization=_authorization(), stability=_stability(prompt_hash="b" * 64),
        )

    with pytest.raises(ValueError, match="exceeds its authorization"):
        run_interactive_runtime_evaluation(
            mechanical_cases=mechanical, judgment_cases=judgment,
            extractor=_Extractor(cost=0.02), authorization=_authorization(),
            stability=_stability(),
        )


def test_interactive_runtime_requires_full_20_plus_10_case_set() -> None:
    mechanical, judgment = _cases()
    with pytest.raises(ValueError, match="exactly 30 unique cases"):
        run_interactive_runtime_evaluation(
            mechanical_cases=mechanical[:-1], judgment_cases=judgment,
            extractor=_Extractor(), authorization=_authorization(), stability=_stability(),
        )


def test_normal_prompt_repeated_trials_measure_stability_without_batch_metadata() -> None:
    mechanical, judgment = _cases()
    first = run_interactive_runtime_trial(
        mechanical_cases=mechanical, judgment_cases=judgment, extractor=_Extractor(),
        authorization=_authorization(), clock=_Clock(),
    )
    second = run_interactive_runtime_trial(
        mechanical_cases=mechanical, judgment_cases=judgment, extractor=_Extractor(),
        authorization=_authorization(), clock=_Clock(),
    )
    stability = evaluate_interactive_repeated_run_stability(
        first_trial=first, second_trial=second
    )
    assert stability.model == "gemini-test"
    assert stability.prompt_hash == PROMPT_HASH
    assert stability.trial_count == 2
    assert stability.statement_level_agreement == 1.0
    assert stability.mechanical_verified_defeated_flips == 0

    mismatched = replace(second, authorization=replace(_authorization(), model="other"))
    with pytest.raises(ValueError, match="identical authorization"):
        evaluate_interactive_repeated_run_stability(first_trial=first, second_trial=mismatched)


def test_normal_prompt_trial_artifact_is_hash_validated(tmp_path: Path) -> None:
    mechanical, judgment = _cases()
    trial = run_interactive_runtime_trial(
        mechanical_cases=mechanical, judgment_cases=judgment, extractor=_Extractor(),
        authorization=_authorization(), clock=_Clock(),
    )
    payload = interactive_runtime_trial_as_dict(trial=trial)
    path = tmp_path / "trial.json"
    path.write_text(json.dumps(payload))
    assert load_interactive_runtime_trial(path=path) == trial
    payload["cases"][0]["input_tokens"] = 999
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="invalid hash"):
        load_interactive_runtime_trial(path=path)


def test_interactive_stability_cli_compiles_two_trials(tmp_path: Path) -> None:
    mechanical, judgment = _cases()
    trial = run_interactive_runtime_trial(
        mechanical_cases=mechanical, judgment_cases=judgment, extractor=_Extractor(),
        authorization=_authorization(), clock=_Clock(),
    )
    first, second, output = (tmp_path / name for name in ("first.json", "second.json", "stability.json"))
    first.write_text(json.dumps(interactive_runtime_trial_as_dict(trial=trial)))
    second.write_text(json.dumps(interactive_runtime_trial_as_dict(trial=trial)))
    assert stability_main([
        "--first-trial", str(first), "--second-trial", str(second), "--output", str(output)
    ]) == 0
    assert json.loads(output.read_text())["stability"]["mechanical_verified_defeated_flips"] == 0


def test_normal_stability_compiles_a_readiness_compatible_operations_artifact(tmp_path: Path) -> None:
    mechanical, judgment = _cases()
    first = run_interactive_runtime_trial(
        mechanical_cases=mechanical, judgment_cases=judgment, extractor=_Extractor(), authorization=_authorization(), clock=_Clock()
    )
    second = run_interactive_runtime_trial(
        mechanical_cases=mechanical, judgment_cases=judgment, extractor=_Extractor(), authorization=_authorization(), clock=_Clock()
    )
    payload = compile_interactive_runtime_artifact(
        trial=first,
        stability=evaluate_interactive_repeated_run_stability(first_trial=first, second_trial=second),
    )
    path = tmp_path / "operations.json"
    path.write_text(json.dumps(payload))
    operations = load_operational_measurements(path=path)
    assert operations.normal_prompt_stability is True
    assert operations.verified_defeated_flips == 0


def test_interactive_trial_cli_preflight_is_no_network(capsys: pytest.CaptureFixture[str]) -> None:
    assert trial_main([
        "--mechanical-cases", str(CASE_ROOT / "mechanical_v1.json"),
        "--judgment-cases", str(CASE_ROOT / "judgment_v1.json"),
        "--snapshot-root", str(SNAPSHOT_ROOT),
        "--input-price-per-million-usd", "0", "--output-price-per-million-usd", "0",
        "--max-total-cost-usd", "1", "--max-request-cost-usd", "0.01", "--preflight",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["case_count"] == 30


def test_interactive_cli_requires_explicit_execution_acknowledgement(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        interactive_main(
            [
                "--mechanical-cases", str(tmp_path / "mechanical.json"),
                "--judgment-cases", str(tmp_path / "judgment.json"),
                "--snapshot-root", str(tmp_path),
                "--stability-artifact", str(tmp_path / "stability.json"),
                "--output", str(tmp_path / "output.json"),
                "--input-price-per-million-usd", "0",
                "--output-price-per-million-usd", "0",
                "--max-total-cost-usd", "1",
                "--max-request-cost-usd", "0.01",
            ]
        )


def test_interactive_cli_preflight_validates_without_loading_credentials(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = GeminiExtractionConfig()
    stability_path = tmp_path / "stability.json"
    stability_path.write_text(
        json.dumps(
            asdict(_stability(prompt_hash=config.prompt_hash, model=config.model))
        )
    )
    assert interactive_main(
        [
            "--mechanical-cases", str(CASE_ROOT / "mechanical_v1.json"),
            "--judgment-cases", str(CASE_ROOT / "judgment_v1.json"),
            "--snapshot-root", str(SNAPSHOT_ROOT),
            "--stability-artifact", str(stability_path),
            "--input-price-per-million-usd", "0",
            "--output-price-per-million-usd", "0",
            "--max-total-cost-usd", "1",
            "--max-request-cost-usd", "0.01",
            "--preflight",
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["case_count"] == 30


def test_interactive_cli_preflight_rejects_a_batch_prompt_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stability_path = tmp_path / "batch-stability.json"
    stability_path.write_text(json.dumps(asdict(_stability())))
    with pytest.raises(SystemExit):
        interactive_main(
            [
                "--mechanical-cases", str(CASE_ROOT / "mechanical_v1.json"),
                "--judgment-cases", str(CASE_ROOT / "judgment_v1.json"),
                "--snapshot-root", str(SNAPSHOT_ROOT),
                "--stability-artifact", str(stability_path),
                "--input-price-per-million-usd", "0",
                "--output-price-per-million-usd", "0",
                "--max-total-cost-usd", "1",
                "--max-request-cost-usd", "0.01",
                "--preflight",
            ]
        )
    assert "must match stability metadata" in capsys.readouterr().err
