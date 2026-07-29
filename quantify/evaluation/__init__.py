"""Frozen offline regression-case support."""

from .regression import EvaluationSummary, RegressionCase, run_cases, summarize_cases
from .corpus import case_from_json, load_case_specs

__all__ = [
    "EvaluationSummary",
    "RegressionCase",
    "case_from_json",
    "load_case_specs",
    "run_cases",
    "summarize_cases",
]
