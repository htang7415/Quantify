from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import json

import pytest

from quantify.engine import RestatementPolicy, SourceType, freeze_selected_snapshot
from quantify.harness import build_revenue_snapshot
from quantify.harness.audit import build_audit_manifest
from quantify.harness.sec import (
    SecCompanyFactsClient,
    SecFiling,
    normalize_company_facts,
    normalize_revenue_facts,
)


def _microsoft_company_facts() -> dict:
    """Real FY2023/FY2024 revenue values from Microsoft's FY2024 SEC filing."""

    return {
        "cik": 789019,
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {
                                "start": "2022-07-01",
                                "end": "2023-06-30",
                                "val": 211915000000,
                                "form": "10-K",
                                "fp": "FY",
                                "filed": "2024-07-30",
                                "accn": "0000950170-24-087843",
                            },
                            {
                                "start": "2023-07-01",
                                "end": "2024-06-30",
                                "val": 245122000000,
                                "form": "10-K",
                                "fp": "FY",
                                "filed": "2024-07-30",
                                "accn": "0000950170-24-087843",
                            },
                            {
                                "start": "2024-04-01",
                                "end": "2024-06-30",
                                "val": 64700000000,
                                "form": "10-Q",
                                "fp": "Q3",
                                "filed": "2024-04-25",
                                "accn": "0000950170-24-050212",
                            },
                        ]
                    }
                },
                "OperatingIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "start": "2023-07-01",
                                "end": "2024-06-30",
                                "val": 109433000000,
                                "form": "10-K",
                                "fp": "FY",
                                "filed": "2024-07-30",
                                "accn": "0000950170-24-087843",
                            }
                        ]
                    }
                }
            }
        },
    }


def test_client_caches_exact_sec_payload_bytes(tmp_path) -> None:
    payload = json.dumps(_microsoft_company_facts()).encode()
    calls: list[tuple[str, str]] = []

    def transport(url: str, user_agent: str) -> bytes:
        calls.append((url, user_agent))
        return payload

    client = SecCompanyFactsClient(
        cache_dir=tmp_path,
        user_agent="Quantify test contact@example.com",
        transport=transport,
        now=lambda: datetime(2026, 7, 28, tzinfo=timezone.utc),
    )

    first = client.fetch_company_facts("789019")
    second = client.fetch_company_facts(789019)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.payload_sha256 == second.payload_sha256
    assert len(calls) == 1
    assert calls[0][0].endswith("CIK0000789019.json")
    assert (
        tmp_path / "objects" / f"{first.payload_sha256}.json"
    ).read_bytes() == payload


def test_client_rejects_corrupted_content_addressed_cache_object(tmp_path) -> None:
    payload = json.dumps(_microsoft_company_facts()).encode()
    client = SecCompanyFactsClient(
        cache_dir=tmp_path,
        user_agent="Quantify test contact@example.com",
        transport=lambda _url, _agent: payload,
    )
    source = client.fetch_company_facts(789019)
    object_path = tmp_path / "objects" / f"{source.payload_sha256}.json"
    object_path.write_bytes(b"corrupt")

    with pytest.raises(ValueError, match="content hash"):
        client.fetch_company_facts(789019)


def test_client_caches_historical_submission_indexes_separately(tmp_path) -> None:
    payload = b'{"form": []}'
    calls: list[str] = []
    client = SecCompanyFactsClient(
        cache_dir=tmp_path,
        user_agent="Quantify test contact@example.com",
        transport=lambda url, _agent: calls.append(url) or payload,
    )

    first = client.fetch_submission_history(789019, "CIK0000789019-submissions-001.json")
    second = client.fetch_submission_history(789019, "CIK0000789019-submissions-001.json")

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert calls == [
        "https://data.sec.gov/submissions/CIK0000789019-submissions-001.json"
    ]
    with pytest.raises(ValueError, match="basename"):
        client.fetch_submission_history(789019, "../invalid.json")


def test_client_resolves_all_historical_indexes_declared_by_root_submission(tmp_path) -> None:
    root_payload = json.dumps(
        {
            "filings": {
                "files": [
                    {"name": "CIK0000789019-submissions-002.json"},
                    {"name": "CIK0000789019-submissions-001.json"},
                ]
            }
        }
    ).encode()
    calls: list[str] = []

    def transport(url: str, _agent: str) -> bytes:
        calls.append(url)
        return root_payload if url.endswith("CIK0000789019.json") else b'{"form": []}'

    client = SecCompanyFactsClient(
        cache_dir=tmp_path,
        user_agent="Quantify test contact@example.com",
        transport=transport,
        min_request_interval_seconds=0,
    )
    root = client.fetch_submissions(789019)
    histories = client.fetch_submission_histories(root)

    assert [item.source_url for item in histories] == [
        "https://data.sec.gov/submissions/CIK0000789019-submissions-001.json",
        "https://data.sec.gov/submissions/CIK0000789019-submissions-002.json",
    ]
    assert calls == [
        "https://data.sec.gov/submissions/CIK0000789019.json",
        "https://data.sec.gov/submissions/CIK0000789019-submissions-001.json",
        "https://data.sec.gov/submissions/CIK0000789019-submissions-002.json",
    ]


def test_client_paces_cache_misses(tmp_path) -> None:
    payload = json.dumps(_microsoft_company_facts()).encode()
    clock_values = iter((10.0, 10.02, 10.1))
    waits: list[float] = []
    client = SecCompanyFactsClient(
        cache_dir=tmp_path,
        user_agent="Quantify test contact@example.com",
        transport=lambda _url, _agent: payload,
        min_request_interval_seconds=0.1,
        clock=lambda: next(clock_values),
        sleeper=waits.append,
    )

    client.fetch_company_facts(789019)
    client.fetch_company_facts(320193)

    assert waits == [pytest.approx(0.08)]


def test_normalizer_and_snapshot_builder_are_offline_and_auditable(tmp_path) -> None:
    payload = json.dumps(_microsoft_company_facts()).encode()
    client = SecCompanyFactsClient(
        cache_dir=tmp_path,
        user_agent="Quantify test contact@example.com",
        transport=lambda _url, _agent: payload,
        now=lambda: datetime(2026, 7, 28, tzinfo=timezone.utc),
    )
    source = client.fetch_company_facts(789019)
    facts = normalize_revenue_facts(
        company_facts=source.json(), source_url=source.source_url
    )

    assert [fact.value for fact in facts] == [211915000000, 245122000000, 64700000000]
    build = build_revenue_snapshot(
        source=source,
        as_of_date=date(2024, 7, 30),
        policy=RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
    )

    assert len(build.snapshot.evidence) == 3
    assert build.audit_manifest.cache_hit is False
    assert build.audit_manifest.filing_accessions == (
        "0000950170-24-050212",
        "0000950170-24-087843",
    )
    assert len(build.audit_manifest.manifest_hash) == 64
    assert build.audit_manifest.normalizer_version == "1.1.0"
    assert build.audit_manifest.extraction_model == "unconfigured"
    assert build.audit_manifest.source_retrieved_at == "2026-07-28T00:00:00+00:00"
    assert build.audit_manifest.requested_forms == ("10-K", "10-Q")
    assert build.audit_manifest.selection_rationale.startswith("latest_available_at_cutoff")


def test_manifest_hash_changes_when_replay_relevant_model_metadata_changes(tmp_path) -> None:
    payload = json.dumps(_microsoft_company_facts()).encode()
    client = SecCompanyFactsClient(cache_dir=tmp_path, user_agent="Quantify test contact@example.com", transport=lambda _url, _agent: payload)
    source = client.fetch_company_facts(789019)
    build = build_revenue_snapshot(source=source, as_of_date=date(2024, 7, 30), policy=RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF)
    baseline = build.audit_manifest
    changed = build_audit_manifest(snapshot=build.snapshot, selection=build.selection, source=source, extraction_model="pinned-model-2026-01", prompt_hash="abc")

    assert baseline.manifest_hash != changed.manifest_hash


def test_manifest_hash_is_stable_across_operational_cache_status(tmp_path) -> None:
    payload = json.dumps(_microsoft_company_facts()).encode()
    client = SecCompanyFactsClient(
        cache_dir=tmp_path,
        user_agent="Quantify test contact@example.com",
        transport=lambda _url, _agent: payload,
    )
    source = client.fetch_company_facts(789019)
    build = build_revenue_snapshot(
        source=source,
        as_of_date=date(2024, 7, 30),
        policy=RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
    )

    assert build.audit_manifest.manifest_hash == replace(
        build.audit_manifest, cache_hit=True
    ).manifest_hash


def test_snapshot_builder_limits_normalization_to_resolved_filings(tmp_path) -> None:
    payload = _microsoft_company_facts()
    payload["facts"]["us-gaap"][
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    ]["units"]["USD"].append(
        {
            "start": "2023-07-01",
            "end": "2024-06-30",
            "val": 999999999999,
            "form": "10-K",
            "fp": "FY",
            "filed": "2024-07-30",
            "accn": "0000950170-24-UNSCOPED",
        }
    )
    client = SecCompanyFactsClient(
        cache_dir=tmp_path,
        user_agent="Quantify test contact@example.com",
        transport=lambda _url, _agent: json.dumps(payload).encode(),
        now=lambda: datetime(2026, 7, 28, tzinfo=timezone.utc),
    )
    source = client.fetch_company_facts(789019)
    filing = SecFiling(
        cik="0000789019",
        form="10-K",
        accession="0000950170-24-087843",
        filing_date=date(2024, 7, 30),
        report_date=date(2024, 6, 30),
        primary_document="msft-20240630.htm",
    )

    build = build_revenue_snapshot(
        source=source,
        as_of_date=date(2024, 7, 30),
        policy=RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
        forms=("10-K",),
        filings=(filing,),
        request_timestamp="2026-07-28T01:00:00+00:00",
    )

    assert [fact.value for fact in build.snapshot.evidence] == [211915000000, 245122000000]
    assert build.audit_manifest.resolved_filing_accessions == (filing.accession,)
    assert build.audit_manifest.request_timestamp == "2026-07-28T01:00:00+00:00"


def test_snapshot_builder_rejects_out_of_scope_resolved_filings(tmp_path) -> None:
    client = SecCompanyFactsClient(
        cache_dir=tmp_path,
        user_agent="Quantify test contact@example.com",
        transport=lambda _url, _agent: json.dumps(_microsoft_company_facts()).encode(),
    )
    source = client.fetch_company_facts(789019)
    wrong_entity_filing = SecFiling(
        cik="0000320193",
        form="10-K",
        accession="0000320193-24-000123",
        filing_date=date(2024, 11, 1),
        report_date=date(2024, 9, 28),
        primary_document="aapl-20240928.htm",
    )

    with pytest.raises(ValueError, match="source CIK and requested forms"):
        build_revenue_snapshot(
            source=source,
            as_of_date=date(2024, 11, 1),
            policy=RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
            filings=(wrong_entity_filing,),
        )


def test_audit_manifest_records_restatement_accessions(tmp_path) -> None:
    payload = _microsoft_company_facts()
    revenue_facts = payload["facts"]["us-gaap"][
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    ]["units"]["USD"]
    revenue_facts.append(
        {
            "start": "2023-07-01",
            "end": "2024-06-30",
            "val": 245123000000,
            "form": "10-K/A",
            "fp": "FY",
            "filed": "2025-01-15",
            "accn": "0000950170-25-000001",
        }
    )
    client = SecCompanyFactsClient(
        cache_dir=tmp_path,
        user_agent="Quantify test contact@example.com",
        transport=lambda _url, _agent: json.dumps(payload).encode(),
    )
    source = client.fetch_company_facts(789019)
    build = build_revenue_snapshot(
        source=source,
        as_of_date=date(2025, 1, 15),
        policy=RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
    )

    assert build.audit_manifest.filing_accessions == (
        "0000950170-24-050212",
        "0000950170-24-087843",
        "0000950170-25-000001",
    )
    assert build.audit_manifest.superseded_filing_accessions == (
        "0000950170-24-087843",
    )
    assert "superseded accessions ('0000950170-24-087843',)" in (
        build.audit_manifest.selection_rationale
    )


def test_normalizes_the_initial_metric_routes_and_excludes_unrouted_values() -> None:
    facts = _microsoft_company_facts()
    normalized = normalize_company_facts(
        company_facts=facts, source_url="https://data.sec.gov/example"
    )

    assert {(item.metric, item.value) for item in normalized} == {
        ("revenue", 64700000000),
        ("revenue", 211915000000),
        ("revenue", 245122000000),
        ("operating_income", 109433000000),
    }


def test_normalizer_distinguishes_annual_and_quarterly_facts_in_one_filing() -> None:
    payload = _microsoft_company_facts()
    facts = normalize_company_facts(
        company_facts=payload,
        source_url="https://data.sec.gov/example",
    )

    snapshot, _ = freeze_selected_snapshot(
        snapshot_id="mixed-duration-facts",
        evidence=facts,
        policy=RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
        as_of_date=date(2024, 7, 30),
        source_type=SourceType.SEC_COMPANY_FACTS,
    )

    revenue_ids = [item.evidence_id for item in snapshot.evidence if item.metric == "revenue"]
    assert len(revenue_ids) == len(set(revenue_ids)) == 3


def test_normalizer_respects_requested_form_scope_for_quarterly_facts() -> None:
    facts = normalize_revenue_facts(
        company_facts=_microsoft_company_facts(),
        source_url="https://data.sec.gov/example",
        forms=("10-K",),
    )

    assert [item.value for item in facts] == [211915000000, 245122000000]
