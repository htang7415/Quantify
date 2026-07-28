from __future__ import annotations

from datetime import date, datetime, timezone
import json

import pytest

from quantify.engine import RestatementPolicy
from quantify.harness import build_revenue_snapshot
from quantify.harness.sec import SecCompanyFactsClient, normalize_revenue_facts


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

    assert [fact.value for fact in facts] == [211915000000, 245122000000]
    build = build_revenue_snapshot(
        source=source,
        as_of_date=date(2024, 7, 30),
        policy=RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
    )

    assert len(build.snapshot.evidence) == 2
    assert build.audit_manifest.cache_hit is False
    assert build.audit_manifest.filing_accessions == ("0000950170-24-087843",)
    assert len(build.audit_manifest.manifest_hash) == 64
