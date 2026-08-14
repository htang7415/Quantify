import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_public_release_fixture_matches_declared_catalog_contract() -> None:
    schema = load_json("schemas/public_release_index.v1.schema.json")
    release_index = load_json("web/src/data/publicReleaseIndex.json")
    investor_catalog = load_json("web/src/data/investorCatalog.json")

    assert release_index["schema_version"] == schema["properties"]["schema_version"]["const"]
    releases = {release["catalog"]: release for release in release_index["releases"]}
    assert set(releases) == set(schema["properties"]["releases"]["items"]["properties"]["catalog"]["enum"])
    assert releases["investors"]["status"] == "available"
    assert releases["investors"]["release_id"] == investor_catalog["release_id"]
    assert releases["investors"]["manifest_hash"] == investor_catalog["manifest_hash"]
    assert all(
        releases[catalog]["status"] == "unavailable"
        for catalog in {"markets", "etf_flows", "crypto", "events"}
    )
    assert releases["macro"]["status"] == "available"
    assert releases["macro"]["manifest_hash"] == load_json("web/src/data/blsMacroCatalog.json")["manifest_hash"]
    assert releases["rates"]["status"] == "available"
    assert releases["rates"]["manifest_hash"] == load_json("web/src/data/treasuryRatesCatalog.json")["manifest_hash"]
    assert releases["crypto_exposure"]["status"] == "available"
    assert releases["crypto_exposure"]["manifest_hash"] == load_json("web/src/data/cryptoExposureCatalog.json")["manifest_hash"]
    assert releases["earnings"]["status"] == "available"
    assert releases["earnings"]["manifest_hash"] == load_json("web/src/data/earningsCatalog.json")["manifest_hash"]
    assert releases["policy"]["status"] == "available"
    assert releases["policy"]["manifest_hash"] == load_json("web/src/data/policyEventCatalog.json")["manifest_hash"]


def test_crypto_schema_requires_identity_freshness_and_methodology() -> None:
    schema = load_json("schemas/crypto_market_catalog.v1.schema.json")
    asset = schema["properties"]["assets"]["items"]
    metric = asset["properties"]["metrics"]["items"]

    assert schema["properties"]["schema_version"]["const"] == "crypto-market-catalog.v1"
    assert {"observed_at", "fresh_until", "methodology", "limitations"}.issubset(schema["required"])
    assert {"asset_id", "symbol", "network", "contract_address", "status", "metrics"}.issubset(asset["required"])
    assert {"value", "unit", "effective_at", "source", "source_record_id", "methodology"}.issubset(metric["required"])


def test_public_source_register_keeps_unlicensed_market_feeds_blocked() -> None:
    schema = load_json("schemas/public_intelligence_sources.v1.schema.json")
    register = load_json("sources/public_intelligence_sources.v1.json")

    assert register["schema_version"] == schema["properties"]["schema_version"]["const"]
    sources = {source["source_id"]: source for source in register["sources"]}
    assert sources["us-treasury-daily-rates"]["status"] == "approved"
    assert sources["bls-public-data-api"]["status"] == "approved"
    assert sources["sec-edgar-public-filings"]["status"] == "approved"
    assert sources["coinbase-exchange-market-data"]["status"] == "blocked_public_display"
    assert sources["coingecko-api"]["status"] == "license_required"
    assert sources["coin-metrics-community"]["status"] == "blocked_commercial_use"
    assert all(source["terms_url"].startswith("https://") for source in sources.values())


def test_bls_macro_schema_requires_scope_freshness_and_calculation_inputs() -> None:
    schema = load_json("schemas/bls_macro_catalog.v1.schema.json")
    observation = schema["properties"]["observations"]["items"]

    assert schema["properties"]["schema_version"]["const"] == "bls-macro-catalog.v1"
    assert {"observed_period", "retrieved_at", "fresh_until", "methodology", "disclaimer"}.issubset(schema["required"])
    assert {"series_id", "value_pct", "previous_value_pct", "derivation", "source_url", "inputs"}.issubset(observation["required"])


def test_earnings_schema_requires_exact_filing_and_comparable_metrics() -> None:
    schema = load_json("schemas/earnings_catalog.v1.schema.json")
    company = schema["properties"]["companies"]["items"]
    metric = schema["$defs"]["metric"]

    assert schema["properties"]["schema_version"]["const"] == "earnings-catalog.v1"
    assert {"source_manifest_hash", "source_retrieved_at", "scope", "methodology"}.issubset(schema["required"])
    assert {"cik", "accession", "filing_url", "companyfacts_url", "revenue", "diluted_eps"}.issubset(company["required"])
    assert {"concept", "unit", "value", "prior_year_value", "yoy_change_pct"}.issubset(metric["required"])


def test_policy_schema_requires_authority_dates_sources_and_typed_details() -> None:
    schema = load_json("schemas/policy_event_catalog.v1.schema.json")
    event = schema["$defs"]["event"]

    assert schema["properties"]["schema_version"]["const"] == "policy-event-catalog.v1"
    assert {"source_record_hash", "observed_at", "retrieved_at", "scope", "methodology"}.issubset(schema["required"])
    assert {"authority_id", "action_type", "status", "published_at", "effective_at", "source_document_id", "source_url", "source_sha256", "details"}.issubset(event["required"])
    assert len(event["properties"]["details"]["oneOf"]) == 3
