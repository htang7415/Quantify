"""Snapshot construction from the cache-first SEC adapters."""

from __future__ import annotations

from datetime import date

from quantify.engine import RestatementPolicy
from quantify.harness.snapshots import SnapshotBuild, build_revenue_snapshot

from .client import SecCompanyFactsClient
from .filings import resolve_filings


class SecSnapshotProvider:
    """Build an auditable, policy-selected snapshot for one company and cutoff."""

    def __init__(
        self,
        *,
        client: SecCompanyFactsClient,
        restatement_policy: RestatementPolicy = RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
    ) -> None:
        self._client = client
        self._restatement_policy = restatement_policy

    def build(
        self, *, cik: str, as_of_date: date, forms: tuple[str, ...]
    ) -> SnapshotBuild:
        source = self._client.fetch_company_facts(cik)
        root_submissions = self._client.fetch_submissions(cik)
        historical_submissions = tuple(
            payload.json()
            for payload in self._client.fetch_submission_histories(root_submissions)
        )
        filings = resolve_filings(
            submissions=root_submissions.json(),
            historical_submissions=historical_submissions,
            cik=source.cik,
            forms=forms,
            as_of_date=as_of_date,
        )
        if not filings:
            raise ValueError("no eligible SEC filings exist for the requested scope")
        return build_revenue_snapshot(
            source=source,
            as_of_date=as_of_date,
            policy=self._restatement_policy,
            forms=forms,
            filings=filings,
        )
