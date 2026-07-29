"""Frozen offline regression-case support."""

from .regression import (
    EvaluationSummary,
    FalsePositiveAnalysis,
    RegressionCase,
    analyze_false_positives,
    run_cases,
    summarize_cases,
)
from .corpus import case_from_json, load_case_specs, load_frozen_case_set
from .parity import (
    PromptingParityArtifact,
    PromptingParityCase,
    PromptingParityDecision,
    PromptingParitySummary,
    evaluate_prompting_parity,
    load_prompting_parity_artifact,
)
from .readiness import (
    ReadinessAssessment,
    ReadinessDecision,
    ReadinessInputs,
    ReadinessPolicy,
    assess_readiness,
)
from .readiness_run import (
    OperationalMeasurements,
    ReadinessRun,
    load_operational_measurements,
    readiness_run_as_dict,
    run_readiness_evaluation,
)
from .parity_worklist import (
    PromptingParityReference,
    PromptingParityWorkItem,
    PromptingParityWorklist,
    build_prompting_parity_worklist,
    load_prompting_parity_references,
)
from .parity_compile import (
    ModelOutcomeArtifact,
    compile_prompting_parity_artifact,
    load_model_outcome_artifact,
    prompting_parity_artifact_as_dict,
)
from .model_profiles import (
    EvaluationCostEstimate,
    EvaluationExecutionMode,
    EvaluationModelProfile,
    estimate_evaluation_cost,
    load_evaluation_model_profile,
    require_cost_within_budget,
)

__all__ = [
    "EvaluationSummary",
    "FalsePositiveAnalysis",
    "RegressionCase",
    "case_from_json",
    "analyze_false_positives",
    "load_case_specs",
    "load_frozen_case_set",
    "run_cases",
    "summarize_cases",
    "PromptingParityArtifact",
    "PromptingParityCase",
    "PromptingParityDecision",
    "PromptingParitySummary",
    "evaluate_prompting_parity",
    "load_prompting_parity_artifact",
    "ReadinessAssessment",
    "ReadinessDecision",
    "ReadinessInputs",
    "ReadinessPolicy",
    "assess_readiness",
    "OperationalMeasurements",
    "ReadinessRun",
    "load_operational_measurements",
    "readiness_run_as_dict",
    "run_readiness_evaluation",
    "PromptingParityReference",
    "PromptingParityWorkItem",
    "PromptingParityWorklist",
    "build_prompting_parity_worklist",
    "load_prompting_parity_references",
    "ModelOutcomeArtifact",
    "compile_prompting_parity_artifact",
    "load_model_outcome_artifact",
    "prompting_parity_artifact_as_dict",
    "EvaluationCostEstimate",
    "EvaluationExecutionMode",
    "EvaluationModelProfile",
    "estimate_evaluation_cost",
    "load_evaluation_model_profile",
    "require_cost_within_budget",
]
