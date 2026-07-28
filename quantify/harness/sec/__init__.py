"""SEC EDGAR acquisition and normalization adapters."""

from .client import SecCompanyFactsClient, SecPayload
from .normalize import normalize_revenue_facts

__all__ = ["SecCompanyFactsClient", "SecPayload", "normalize_revenue_facts"]
