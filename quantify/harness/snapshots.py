"""Build policy-selected snapshots from cached SEC Company Facts payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quantify.engine import EvidenceSnapshot, RestatementPolicy, RestatementSelection, freeze_selected_snapshot

from .audit import AuditManifest, build_audit_manifest
from .sec.client import SecPayload
from .sec.normalize import normalize_revenue_facts


@dataclass(frozen=True, slots=True)
class SnapshotBuild:
    snapshot: EvidenceSnapshot
    selection: RestatementSelection
    audit_manifest: AuditManifest


def build_revenue_snapshot(
    *, source: SecPayload, as_of_date: date, policy: RestatementPolicy
) -> SnapshotBuild:
    evidence = normalize_revenue_facts(
        company_facts=source.json(), source_url=source.source_url
    )
    snapshot, selection = freeze_selected_snapshot(
        snapshot_id=f"sec-revenue-{source.cik}-{as_of_date.isoformat()}",
        evidence=evidence,
        policy=policy,
        as_of_date=as_of_date,
    )
    return SnapshotBuild(
        snapshot=snapshot,
        selection=selection,
        audit_manifest=build_audit_manifest(
            snapshot=snapshot, selection=selection, source=source
        ),
    )
