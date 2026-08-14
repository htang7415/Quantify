import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_public_release_fixture_matches_declared_catalog_contract() -> None:
    schema = load_json("schemas/public_release_index.v3.schema.json")
    release_index = load_json("web/src/data/publicReleaseIndex.json")
    investor_catalog = load_json("web/src/data/investorCatalog.json")

    assert release_index["schema_version"] == schema["properties"]["schema_version"]["const"]
    releases = {release["catalog"]: release for release in release_index["releases"]}
    assert set(releases) == set(schema["properties"]["releases"]["items"]["properties"]["catalog"]["enum"])
    assert releases["investors"]["status"] == "available"
    assert releases["investors"]["release_id"] == investor_catalog["release_id"]
    assert releases["investors"]["manifest_hash"] == investor_catalog["manifest_hash"]
    venture_catalog = load_json("web/src/data/vcCatalog.json")
    assert releases["venture"]["status"] == "available"
    assert releases["venture"]["release_id"] == venture_catalog["release_id"]
    assert releases["venture"]["manifest_hash"] == venture_catalog["manifest_hash"]
    assert all(
        releases[catalog]["status"] == "unavailable"
        for catalog in {"markets", "crypto", "events"}
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
    assert releases["etf_flows"]["status"] == "available"
    assert releases["etf_flows"]["manifest_hash"] == load_json("web/src/data/etfFlowCatalog.json")["manifest_hash"]
    assert releases["etf_holdings"]["status"] == "available"
    assert releases["etf_holdings"]["manifest_hash"] == load_json("web/src/data/etfHoldingsCatalog.json")["manifest_hash"]


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
    assert sources["sec-form-n-port-datasets"]["status"] == "approved"
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


def test_etf_flow_schema_requires_exact_filed_inputs_and_release_scope() -> None:
    schema = load_json("schemas/etf_flow_catalog.v2.schema.json")
    fund = schema["$defs"]["fund"]
    flow = schema["$defs"]["flow"]
    assert schema["properties"]["schema_version"]["const"] == "etf-flow-catalog.v2"
    assert {"dataset_sha256", "fresh_until", "observed_through", "methodology", "funds"}.issubset(schema["required"])
    assert {"accession", "report_date", "months", "net_assets_usd", "three_month_net_flow_usd", "monthly_flows"}.issubset(fund["required"])
    assert {"sales_nav_usd", "reinvestment_nav_usd", "redemption_nav_usd", "net_flow_usd"}.issubset(flow["required"])


def test_etf_holdings_schema_requires_exact_rows_and_flow_binding() -> None:
    schema = load_json("schemas/etf_holdings_catalog.v1.schema.json")
    fund = schema["$defs"]["fund"]
    holding = schema["$defs"]["holding"]
    assert schema["properties"]["schema_version"]["const"] == "etf-holdings-catalog.v1"
    assert {"flow_release_id", "flow_manifest_hash", "security_metadata_hash", "selection_rule", "funds"}.issubset(schema["required"])
    assert {"report_date", "total_holding_rows", "top_ten_concentration_pct", "holdings"}.issubset(fund["required"])
    assert {"holding_id", "cusip", "ticker", "currency_value", "filed_percentage"}.issubset(holding["required"])


def test_investor_source_bundle_schema_binds_local_sec_resources() -> None:
    schema = load_json("schemas/investor_sec_source_bundle.v1.schema.json")
    resource = schema["$defs"]["resource"]
    assert schema["properties"]["schema_version"]["const"] == "investor-sec-source-bundle.v1"
    assert {"source_id", "created_at", "quarters", "manager_ciks", "resources"}.issubset(schema["required"])
    assert {"url", "path", "sha256", "media_type"}.issubset(resource["required"])
    assert resource["properties"]["url"]["pattern"].startswith("^https://")


def test_investor_compilation_record_binds_source_metadata_and_output() -> None:
    schema = load_json("schemas/investor_compilation_record.v1.schema.json")
    assert schema["properties"]["schema_version"]["const"] == "investor-compilation-record.v1"
    assert {
        "source_manifest_sha256",
        "security_metadata_sha256",
        "compiler_contract",
        "catalog_release_id",
        "catalog_manifest_hash",
    }.issubset(schema["required"])


def test_venture_contracts_are_source_bound_and_cannot_authorize_publication() -> None:
    source_schema = load_json("schemas/vc_source_bundle.v1.schema.json")
    catalog_schema = load_json("schemas/vc_catalog.v1.schema.json")
    record_schema = load_json("schemas/vc_compilation_record.v1.schema.json")
    catalog = load_json("web/src/data/vcCatalog.json")
    compilation = load_json("web/src/data/vcCompilationRecord.json")

    assert source_schema["properties"]["schema_version"]["const"] == "vc-source-bundle.v1"
    assert catalog_schema["properties"]["schema_version"]["const"] == "vc-catalog.v1"
    assert record_schema["properties"]["publication_authorized"]["const"] is False
    assert compilation["publication_authorized"] is False
    assert compilation["catalog_release_id"] == catalog["release_id"]
    assert compilation["catalog_manifest_hash"] == catalog["manifest_hash"]
    relationship = catalog_schema["$defs"]["relationship"]
    assert relationship["additionalProperties"] is False
    assert {"first_partnered_year", "stage", "participation_role", "follow_on_status", "source_url", "source_sha256"}.issubset(relationship["required"])
    forbidden = {"ownership", "position_value", "investment_value", "aum", "valuation", "return", "weight"}
    assert forbidden.isdisjoint(relationship["properties"])


def test_investor_filing_readiness_schema_is_bounded_and_never_authorizes_a_candidate() -> None:
    schema = load_json("schemas/investor_filing_readiness.v1.schema.json")
    manager = schema["$defs"]["manager"]
    assert schema["properties"]["schema_version"]["const"] == "investor-filing-readiness.v1"
    assert schema["properties"]["candidate_build_authorized"]["const"] is False
    assert {"source_manifest_sha256", "target_report_period", "ready_manager_count", "managers"}.issubset(schema["required"])
    assert manager["properties"]["status"]["enum"] == ["ready", "waiting", "ahead"]


def test_public_candidate_gate_policy_keeps_review_and_dependency_controls_non_bypassable() -> None:
    schema = load_json("schemas/public_candidate_gate_policy.v2.schema.json")
    policy = load_json("policies/public_candidate_gate_policy.v2.json")
    assert policy["schema_version"] == schema["properties"]["schema_version"]["const"]
    assert policy["require_no_status_regression"] is True
    assert policy["require_no_observation_regression"] is True
    assert policy["require_investor_crypto_dependency_rebuild"] is True
    assert policy["require_venture_full_review"] is True
    assert policy["lane_a_spot_review_required"] is True
    assert policy["lane_b_full_review_required"] is True


def test_public_candidate_review_schema_is_typed_and_cannot_authorize_promotion() -> None:
    schema = load_json("schemas/public_candidate_review.v2.schema.json")
    metrics = schema["$defs"]["metrics"]
    assert schema["properties"]["schema_version"]["const"] == "public-candidate-review.v2"
    assert schema["properties"]["promotion_authorized"]["const"] is False
    assert metrics["additionalProperties"] is False
    assert {"investors", "venture", "etf_flows", "etf_holdings", "crypto_dependency"}.issubset(metrics["required"])


def test_research_answer_contract_separates_analysis_from_verifier_authority() -> None:
    schema = load_json("schemas/research_answer.v1.schema.json")
    statement = schema["$defs"]["statement"]
    verification = schema["$defs"]["verification_result"]

    assert schema["properties"]["schema_version"]["const"] == "research-answer.v1"
    assert schema["additionalProperties"] is False
    assert {
        "release_scope",
        "answer_statement_ids",
        "statements",
        "citations",
        "counterpoint_statement_ids",
        "unavailable",
        "limitations",
        "model_contract",
        "verification_results",
        "audit_manifest_hash",
    }.issubset(schema["required"])
    assert statement["properties"]["kind"]["enum"] == [
        "released_fact",
        "deterministic_calculation",
        "agent_interpretation",
        "narrative_context",
        "open_question",
    ]
    assert "measurement" in statement["required"]
    calculation = schema["$defs"]["calculation"]
    assert schema["$defs"]["measurement"]["properties"]["value"]["type"] == "string"
    assert calculation["properties"]["operation"]["enum"] == [
        "sum",
        "difference",
        "percent_change",
        "percentage_point_change",
    ]
    assert calculation["properties"]["decimal_places"]["maximum"] == 12
    assert calculation["properties"]["value"]["type"] == "string"
    assert verification["properties"]["authority"]["const"] == "deterministic_verifier"
    forbidden = {"recommendation", "price_target", "allocation", "trade_instruction", "confidence"}
    assert forbidden.isdisjoint(schema["properties"])


def test_research_answer_citations_keep_narrative_and_news_context_only() -> None:
    citation = load_json("schemas/research_answer.v1.schema.json")["$defs"]["citation"]
    rules = {
        rule["if"]["properties"]["source_type"]["const"]: rule["then"]["properties"]
        for rule in citation["allOf"]
    }

    assert rules["structured_fact"]["verification_role"]["const"] == "verdict_evidence"
    assert rules["structured_fact"]["evidence_id"]["type"] == "string"
    assert rules["structured_fact"]["source_span"]["type"] == "null"
    for source_type in ("narrative_disclosure", "licensed_news"):
        assert rules[source_type]["verification_role"]["const"] == "context_only"
        assert rules[source_type]["evidence_id"]["type"] == "null"
        assert rules[source_type]["chunk_hash"]["$ref"] == "#/$defs/sha256"
        assert rules[source_type]["source_span"]["$ref"] == "#/$defs/source_span"


def test_research_answer_model_contract_is_replay_visible_when_present() -> None:
    model_contract = load_json("schemas/research_answer.v1.schema.json")["$defs"]["model_contract"]

    assert model_contract["additionalProperties"] is False
    assert {
        "provider",
        "model_id",
        "prompt_contract_hash",
        "tool_contract_hash",
        "provider_attempt_id",
    } == set(model_contract["required"])


def test_approved_evidence_search_request_is_exact_release_bound_and_capped() -> None:
    schema = load_json("schemas/approved_evidence_search_request.v1.schema.json")
    query = schema["$defs"]["query"]

    assert (
        schema["properties"]["schema_version"]["const"]
        == "approved-evidence-search-request.v1"
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["queries"]["minItems"] == 1
    assert schema["properties"]["queries"]["maxItems"] == 32
    assert set(query["required"]) == {
        "query_id",
        "metric",
        "period_start",
        "period_end",
        "unit",
    }
    assert query["additionalProperties"] is False
    assert {"query", "text", "url", "provider"}.isdisjoint(query["properties"])


def test_approved_evidence_search_result_authorizes_structured_facts_only() -> None:
    schema = load_json("schemas/approved_evidence_search_result.v1.schema.json")
    fact = schema["$defs"]["fact"]
    citation = schema["$defs"]["citation"]

    assert (
        schema["properties"]["schema_version"]["const"]
        == "approved-evidence-search-result.v1"
    )
    assert schema["properties"]["status"]["enum"] == [
        "completed",
        "partial",
        "unavailable",
    ]
    assert fact["properties"]["measurement"]["properties"]["value"]["$ref"] == (
        "#/$defs/decimal"
    )
    assert citation["properties"]["source_type"]["const"] == "structured_fact"
    assert citation["properties"]["verification_role"]["const"] == "verdict_evidence"
    assert citation["properties"]["chunk_hash"]["type"] == "null"
    assert citation["properties"]["source_span"]["type"] == "null"
    assert schema["$defs"]["unavailable"]["properties"]["reason"]["const"] == (
        "exact_fact_not_found"
    )


def test_approved_calculation_request_cannot_supply_values_or_code() -> None:
    schema = load_json("schemas/approved_calculation_request.v1.schema.json")
    instruction = schema["$defs"]["instruction"]

    assert (
        schema["properties"]["schema_version"]["const"]
        == "approved-calculation-request.v1"
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["calculations"]["minItems"] == 1
    assert schema["properties"]["calculations"]["maxItems"] == 32
    assert instruction["additionalProperties"] is False
    assert set(instruction["required"]) == {
        "result_statement_id",
        "operation",
        "input_statement_ids",
        "decimal_places",
    }
    assert {
        "value",
        "unit",
        "text",
        "formula",
        "code",
        "url",
        "provider",
    }.isdisjoint(instruction["properties"])
    assert instruction["properties"]["input_statement_ids"]["items"]["$ref"] == (
        "#/$defs/fact_statement_id"
    )


def test_approved_calculation_result_matches_research_answer_calculation_shape() -> None:
    schema = load_json("schemas/approved_calculation_result.v1.schema.json")
    statement = schema["$defs"]["calculation_statement"]
    calculation = statement["properties"]["calculation"]

    assert (
        schema["properties"]["schema_version"]["const"]
        == "approved-calculation-result.v1"
    )
    assert schema["properties"]["status"]["const"] == "completed"
    assert set(statement["required"]) == {
        "statement_id",
        "kind",
        "text",
        "citation_ids",
        "derived_from_statement_ids",
        "measurement",
        "calculation",
    }
    assert statement["properties"]["kind"]["const"] == "deterministic_calculation"
    assert statement["properties"]["citation_ids"]["maxItems"] == 0
    assert statement["properties"]["measurement"]["type"] == "null"
    assert calculation["properties"]["operation"]["enum"] == [
        "sum",
        "difference",
        "percent_change",
        "percentage_point_change",
    ]
    assert calculation["properties"]["value"]["$ref"] == "#/$defs/decimal"
    assert calculation["properties"]["decimal_places"]["maximum"] == 12


def test_approved_narrative_context_request_is_exact_scoped_and_capped() -> None:
    schema = load_json("schemas/approved_narrative_context_request.v1.schema.json")

    assert (
        schema["properties"]["schema_version"]["const"]
        == "approved-narrative-context-request.v1"
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["filing_accessions"]["maxItems"] == 16
    assert schema["properties"]["filing_accessions"]["uniqueItems"] is True
    assert schema["properties"]["maximum_chunks"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 16,
    }
    assert {
        "query",
        "text",
        "url",
        "ranking",
        "provider",
        "licensed_news",
    }.isdisjoint(schema["properties"])


def test_approved_narrative_context_result_is_context_only() -> None:
    schema = load_json("schemas/approved_narrative_context_result.v1.schema.json")
    context = schema["$defs"]["context"]
    citation = schema["$defs"]["citation"]

    assert (
        schema["properties"]["schema_version"]["const"]
        == "approved-narrative-context-result.v1"
    )
    assert schema["properties"]["status"]["enum"] == [
        "completed",
        "partial",
        "unavailable",
    ]
    assert schema["properties"]["contexts"]["maxItems"] == 16
    assert context["properties"]["kind"]["const"] == "narrative_context"
    assert citation["properties"]["source_type"]["const"] == "narrative_disclosure"
    assert citation["properties"]["verification_role"]["const"] == "context_only"
    assert citation["properties"]["evidence_id"]["type"] == "null"
    assert citation["properties"]["chunk_hash"]["$ref"] == "#/$defs/sha256"
    assert citation["properties"]["source_span"]["$ref"] == "#/$defs/source_span"
    assert "measurement" not in context["properties"]
    assert "verdict" not in schema["properties"]


def test_approved_review_task_request_is_grounded_and_bounded() -> None:
    schema = load_json("schemas/approved_review_task_request.v1.schema.json")

    assert (
        schema["properties"]["schema_version"]["const"]
        == "approved-review-task-request.v1"
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["source_result_hashes"]["minItems"] == 1
    assert schema["properties"]["source_result_hashes"]["maxItems"] == 8
    assert schema["properties"]["derived_from_statement_ids"]["maxItems"] == 32
    assert schema["properties"]["derived_from_citation_ids"]["maxItems"] == 32
    assert len(schema["anyOf"]) == 2
    assert schema["properties"]["question"]["maxLength"] == 500
    assert {
        "reviewer",
        "assignee",
        "approval",
        "approved",
        "verdict",
        "notification",
    }.isdisjoint(schema["properties"])


def test_approved_review_task_result_cannot_claim_approval_or_assignment() -> None:
    schema = load_json("schemas/approved_review_task_result.v1.schema.json")

    assert (
        schema["properties"]["schema_version"]["const"]
        == "approved-review-task-result.v1"
    )
    assert schema["properties"]["status"]["const"] == "requires_review"
    assert schema["properties"]["review_task_id"]["pattern"] == (
        "^review-[a-f0-9]{32}$"
    )
    assert {
        "reviewer",
        "assignee",
        "approval",
        "approved",
        "verdict",
        "queued_at",
        "notified_at",
    }.isdisjoint(schema["properties"])
