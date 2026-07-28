"""SEC EDGAR acquisition and normalization adapters."""

from .client import SecCompanyFactsClient, SecPayload
from .filings import SecFiling, resolve_filings
from .normalize import INITIAL_METRIC_ROUTES, MetricRoute, normalize_company_facts, normalize_revenue_facts

__all__ = [
    "INITIAL_METRIC_ROUTES",
    "MetricRoute",
    "SecCompanyFactsClient",
    "SecFiling",
    "SecPayload",
    "normalize_company_facts",
    "normalize_revenue_facts",
    "resolve_filings",
]
