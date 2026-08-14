import { buildCompanyOwnership } from "../companies/ownership";
import { companyConnections } from "../companies/connections";
import { cryptoExposureCatalog } from "../crypto/catalog";
import { displayName, readableDate, sentenceCase } from "../format";
import { investorCatalog } from "../investors/catalog";
import { blsMacroCatalog } from "../macro/catalog";
import { policyEventCatalog } from "../policy/catalog";
import { treasuryRatesCatalog } from "../rates/catalog";
import { releaseFor } from "../releases/catalog";
import type { PublicCatalog, ReleaseFreshness } from "../releases/types";
import { etfFlowCatalog } from "../etfs/catalog";
import { etfHoldingsFund } from "../etfs/holdingsCatalog";

export type SearchEntityKind = "Investor" | "Company" | "ETF" | "Macro" | "Rates" | "Crypto" | "Policy";

export type SearchEntitySource = {
  catalog: PublicCatalog;
  releaseId: string;
  observedAt: string;
  freshness: ReleaseFreshness;
};

export type SearchEntity = {
  id: string;
  kind: SearchEntityKind;
  label: string;
  symbol: string | null;
  description: string;
  href: string;
  identifiers: string[];
  sources: SearchEntitySource[];
  availability: "released" | "source_review";
};

function source(catalog: PublicCatalog): SearchEntitySource {
  const release = releaseFor(catalog);
  if (release.status !== "available" || !release.release_id || !release.observed_at) {
    throw new Error(`Search cannot index unavailable catalog ${catalog}.`);
  }
  return {
    catalog,
    releaseId: release.release_id,
    observedAt: release.observed_at,
    freshness: release.freshness
  };
}

function uniqueSources(sources: SearchEntitySource[]): SearchEntitySource[] {
  return [...new Map(sources.map((item) => [item.catalog, item])).values()];
}

const investorSource = source("investors");
const companies = buildCompanyOwnership(investorCatalog);

export function buildSearchEntityGraph(): SearchEntity[] {
  const entities: SearchEntity[] = [];

  for (const manager of investorCatalog.managers) {
    entities.push({
      id: `investor:${manager.reporting_manager_cik}`,
      kind: "Investor",
      label: displayName(manager.firm),
      symbol: manager.person,
      description: manager.status === "available"
        ? `${manager.holdings_count} reported positions · ${manager.primary_theme}`
        : "Filing available · derived metrics withheld",
      href: `/investors/${manager.slug}`,
      identifiers: [manager.reporting_manager_cik, manager.reporting_manager_name, manager.slug, manager.latest_filing.accession],
      sources: [investorSource],
      availability: manager.status === "available" ? "released" : "source_review"
    });
  }

  for (const company of companies) {
    const connections = companyConnections(company);
    const sources = [investorSource];
    if (connections.etfRows) sources.push(source("etf_holdings"));
    if (connections.earningsAvailable) sources.push(source("earnings"));
    if (connections.policyEvents) sources.push(source("policy"));
    entities.push({
      id: `company:${company.ticker}`,
      kind: "Company",
      label: displayName(company.issuer),
      symbol: company.ticker,
      description: `${connections.reportingManagers} reporting ${connections.reportingManagers === 1 ? "manager" : "managers"} · ${sources.length} connected ${sources.length === 1 ? "release" : "releases"}`,
      href: `/companies/${company.slug}`,
      identifiers: [company.ticker, company.slug, ...company.positions.flatMap(({ holding }) => [holding.security_id, holding.cusip])],
      sources: uniqueSources(sources),
      availability: "released"
    });
  }

  for (const fund of etfFlowCatalog.funds) {
    const detail = etfHoldingsFund(fund.ticker);
    entities.push({
      id: `etf:${fund.fund_id}`,
      kind: "ETF",
      label: fund.name,
      symbol: fund.ticker,
      description: `${fund.category} · report ${readableDate(fund.report_date)}`,
      href: detail ? `/markets/etfs/${detail.slug}` : "/markets/etfs",
      identifiers: [fund.fund_id, fund.ticker, fund.registrant_cik, fund.registrant_name, fund.series_id ?? "", fund.fund_lei],
      sources: uniqueSources([source("etf_flows"), ...(detail ? [source("etf_holdings")] : [])]),
      availability: "released"
    });
  }

  for (const observation of blsMacroCatalog.observations) {
    entities.push({
      id: `macro:${observation.metric_id}`,
      kind: "Macro",
      label: observation.label,
      symbol: observation.series_id,
      description: `BLS · ${observation.period} · ${observation.value_pct.toFixed(1)}%`,
      href: "/markets/macro",
      identifiers: [observation.metric_id, observation.series_id, observation.derivation],
      sources: [source("macro")],
      availability: "released"
    });
  }

  for (const point of treasuryRatesCatalog.curve) {
    entities.push({
      id: `rates:${point.maturity}`,
      kind: "Rates",
      label: `U.S. Treasury ${point.maturity}`,
      symbol: point.maturity,
      description: `${point.yield_pct.toFixed(2)}% · observed ${readableDate(treasuryRatesCatalog.observed_at.slice(0, 10))}`,
      href: "/markets/rates",
      identifiers: [point.maturity, `${point.years} year`, treasuryRatesCatalog.source_record_id],
      sources: [source("rates")],
      availability: "released"
    });
  }

  for (const asset of cryptoExposureCatalog.assets) {
    entities.push({
      id: `crypto:${asset.asset_id}`,
      kind: "Crypto",
      label: asset.name,
      symbol: asset.symbol,
      description: `${asset.network} · reported ETP exposure only`,
      href: "/markets/crypto",
      identifiers: [asset.asset_id, asset.slug, asset.symbol, asset.network],
      sources: [source("crypto_exposure")],
      availability: "released"
    });
  }

  for (const event of policyEventCatalog.events) {
    const relatedTickers = event.details.kind === "advanced_computing_export_rule" ? event.details.related_company_tickers : [];
    entities.push({
      id: `policy:${event.event_id}`,
      kind: "Policy",
      label: event.title,
      symbol: event.authority_name,
      description: `${sentenceCase(event.action_type)} · effective ${readableDate(event.effective_at)}`,
      href: "/intelligence/policy",
      identifiers: [event.event_id, event.authority_id, event.source_document_id, event.category, ...relatedTickers],
      sources: [source("policy")],
      availability: "released"
    });
  }

  const ids = new Set<string>();
  for (const entity of entities) {
    if (ids.has(entity.id)) throw new Error(`Search entity ID is duplicated: ${entity.id}`);
    ids.add(entity.id);
  }
  return entities;
}

export const searchEntityGraph = buildSearchEntityGraph();

function normalized(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function score(entity: SearchEntity, query: string): number | null {
  const fields = [entity.symbol ?? "", entity.label, entity.id, ...entity.identifiers]
    .map(normalized)
    .filter(Boolean);
  if (fields.some((field) => field === query)) return 0;
  if (fields.some((field) => field.startsWith(query))) return 10;
  if (fields.some((field) => field.split(" ").some((word) => word.startsWith(query)))) return 20;
  const tokens = query.split(" ").filter(Boolean);
  if (tokens.length && tokens.every((token) => fields.some((field) => field.includes(token)))) return 30;
  return null;
}

const kindOrder: Record<SearchEntityKind, number> = { Company: 0, Investor: 1, ETF: 2, Macro: 3, Rates: 4, Crypto: 5, Policy: 6 };

export function searchReleasedEntities(query: string, limit = 10): SearchEntity[] {
  const cleanQuery = normalized(query);
  if (!cleanQuery) {
    return [...searchEntityGraph]
      .sort((left, right) => kindOrder[left.kind] - kindOrder[right.kind] || left.label.localeCompare(right.label))
      .slice(0, limit);
  }
  return searchEntityGraph
    .map((entity) => ({ entity, score: score(entity, cleanQuery) }))
    .filter((row): row is { entity: SearchEntity; score: number } => row.score !== null)
    .sort((left, right) => left.score - right.score || kindOrder[left.entity.kind] - kindOrder[right.entity.kind] || left.entity.label.localeCompare(right.entity.label))
    .slice(0, limit)
    .map(({ entity }) => entity);
}
