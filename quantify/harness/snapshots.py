"""Build policy-selected snapshots from cached SEC Company Facts payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quantify.engine import (
    EvidenceSnapshot,
    RestatementPolicy,
    RestatementSelection,
    SourceType,
    freeze_selected_snapshot,
)

from .audit import AuditManifest, build_audit_manifest
from .sec.client import SecPayload
from .sec.filings import SecFiling
from .sec.normalize import INITIAL_METRIC_ROUTES, MetricRoute, normalize_company_facts


@dataclass(frozen=True, slots=True)
class SnapshotBuild:
    snapshot: EvidenceSnapshot
    selection: RestatementSelection
    audit_manifest: AuditManifest


def build_sec_snapshot(
    *,
    source: SecPayload,
    as_of_date: date,
    policy: RestatementPolicy,
    forms: tuple[str, ...] = ("10-K", "10-Q"),
    filings: tuple[SecFiling, ...] = (),
    request_timestamp: str | None = None,
    routes: tuple[MetricRoute, ...] = INITIAL_METRIC_ROUTES,
    acquisition_records: tuple[tuple[str, str], ...] = (),
    snapshot_label: str = "sec-company-facts",
) -> SnapshotBuild:
    normalized_forms = {form.removesuffix("/A") for form in forms}
    invalid_filings = tuple(
        filing
        for filing in filings
        if filing.cik != source.cik or filing.form.removesuffix("/A") not in normalized_forms
    )
    if invalid_filings:
        raise ValueError(
            "resolved filings must match the source CIK and requested forms"
        )
    evidence = normalize_company_facts(
        company_facts=source.json(),
        source_url=source.source_url,
        forms=forms,
        routes=routes,
        accessions=tuple(filing.accession for filing in filings) if filings else None,
    )
    snapshot, selection = freeze_selected_snapshot(
        snapshot_id=f"{snapshot_label}-{source.cik}-{as_of_date.isoformat()}",
        evidence=evidence,
        policy=policy,
        as_of_date=as_of_date,
        source_type=SourceType.SEC_COMPANY_FACTS,
    )
    return SnapshotBuild(
        snapshot=snapshot,
        selection=selection,
        audit_manifest=build_audit_manifest(
            snapshot=snapshot,
            selection=selection,
            source=source,
            requested_forms=forms,
            resolved_filing_accessions=tuple(filing.accession for filing in filings),
            request_timestamp=request_timestamp,
            normalized_evidence=evidence,
            acquisition_records=acquisition_records,
        ),
    )


def build_revenue_snapshot(
    *,
    source: SecPayload,
    as_of_date: date,
    policy: RestatementPolicy,
    forms: tuple[str, ...] = ("10-K", "10-Q"),
    filings: tuple[SecFiling, ...] = (),
    request_timestamp: str | None = None,
) -> SnapshotBuild:
    """Compatibility builder for the original revenue-only service path."""

    return build_sec_snapshot(
        source=source,
        as_of_date=as_of_date,
        policy=policy,
        forms=forms,
        filings=filings,
        request_timestamp=request_timestamp,
        routes=(INITIAL_METRIC_ROUTES[0],),
        snapshot_label="sec-revenue",
    )
