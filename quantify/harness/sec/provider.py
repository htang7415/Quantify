"""Snapshot construction from the cache-first SEC adapters."""

from __future__ import annotations

from datetime import date

from quantify.engine import RestatementPolicy
from quantify.harness.acquisition import EvidenceAcquisitionRecord
from quantify.harness.coverage import EvidenceRequestType
from quantify.harness.sec.normalize import INITIAL_METRIC_ROUTES
from quantify.harness.snapshots import SnapshotBuild, build_sec_snapshot

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
        self,
        *,
        cik: str,
        as_of_date: date,
        forms: tuple[str, ...],
        acquisition_records: tuple[EvidenceAcquisitionRecord, ...] = (),
    ) -> SnapshotBuild:
        source = self._client.fetch_company_facts(cik)
        root_submissions = self._client.fetch_submissions(cik)
        historical_submissions = tuple(
            payload.json()
            for payload in self._client.fetch_submission_histories(root_submissions)
        )
        expanded_forms = set(forms)
        request_types = {record.request_type for record in acquisition_records}
        if EvidenceRequestType.PRIOR_ANNUAL_PERIOD in request_types:
            expanded_forms.add("10-K")
        if EvidenceRequestType.PRIOR_QUARTER in request_types:
            expanded_forms.add("10-Q")
        metric_names = {"revenue"}
        metric_names.update(
            metric
            for request_type, metrics in {
                EvidenceRequestType.PROFITABILITY_METRICS: (
                    "gross_profit",
                    "operating_income",
                    "net_income",
                ),
                EvidenceRequestType.CASH_FLOW_METRICS: (
                    "operating_cash_flow",
                    "capital_expenditure",
                ),
                EvidenceRequestType.BALANCE_SHEET_METRICS: (
                    "cash",
                    "debt_current",
                    "debt_noncurrent",
                ),
                EvidenceRequestType.DILUTION_METRICS: ("diluted_share_count",),
            }.items()
            if request_type in request_types
            for metric in metrics
        )
        resolved_forms = tuple(sorted(expanded_forms))
        filings = resolve_filings(
            submissions=root_submissions.json(),
            historical_submissions=historical_submissions,
            cik=source.cik,
            forms=resolved_forms,
            as_of_date=as_of_date,
        )
        if not filings:
            raise ValueError("no eligible SEC filings exist for the requested scope")
        return build_sec_snapshot(
            source=source,
            as_of_date=as_of_date,
            policy=self._restatement_policy,
            forms=resolved_forms,
            filings=filings,
            routes=tuple(
                route
                for route in INITIAL_METRIC_ROUTES
                if route.metric in metric_names
            ),
            acquisition_records=tuple(
                (record.request_type.value, record.reason)
                for record in acquisition_records
            ),
        )
