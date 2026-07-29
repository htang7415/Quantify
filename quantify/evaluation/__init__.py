"""Frozen offline regression-case support."""

from .regression import (
    EvaluationSummary,
    FalsePositiveAnalysis,
    RegressionCase,
    analyze_false_positives,
    run_cases,
    summarize_cases,
)
from .corpus import case_from_json, load_case_specs

__all__ = [
    "EvaluationSummary",
    "FalsePositiveAnalysis",
    "RegressionCase",
    "case_from_json",
    "analyze_false_positives",
    "load_case_specs",
    "run_cases",
    "summarize_cases",
]
