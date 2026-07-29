from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantify.evaluation import (
    estimate_evaluation_cost,
    load_evaluation_model_profile,
    require_cost_within_budget,
)


PROFILE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "evaluation"
    / "gemini_3_1_flash_lite_batch_v1.json"
)


def test_pinned_batch_profile_caps_the_full_30_case_two_path_cost() -> None:
    profile = load_evaluation_model_profile(path=PROFILE)
    estimate = estimate_evaluation_cost(profile=profile)

    assert profile.model == "gemini-3.1-flash-lite"
    assert profile.execution_mode.value == "batch"
    assert estimate.request_count == 60
    assert estimate.total_cost_usd == pytest.approx(0.04224)
    assert estimate.within_budget is True
    require_cost_within_budget(estimate=estimate)


def test_profile_rejects_a_token_envelope_above_its_budget(tmp_path: Path) -> None:
    payload = json.loads(PROFILE.read_text())
    payload["max_total_cost_usd"] = 0.01
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(payload))

    estimate = estimate_evaluation_cost(
        profile=load_evaluation_model_profile(path=path)
    )
    assert estimate.within_budget is False
    with pytest.raises(ValueError, match="cost budget"):
        require_cost_within_budget(estimate=estimate)
