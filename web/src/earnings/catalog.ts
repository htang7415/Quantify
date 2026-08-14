import rawCatalog from "../data/earningsCatalog.json";
import { releaseFor } from "../releases/catalog";
import type { EarningsCatalog, EarningsCompany, EarningsMetric } from "./types";

function record(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(message);
  return value as Record<string, unknown>;
}

function text(value: unknown, message: string): string {
  if (typeof value !== "string" || !value) throw new Error(message);
  return value;
}

function finite(value: unknown, message: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(message);
  return value;
}

function secUrl(value: unknown, host: string, message: string): string {
  const parsed = text(value, message);
  if (!parsed.startsWith(`https://${host}/`)) throw new Error(message);
  return parsed;
}

function metric(value: unknown): EarningsMetric {
  const row = record(value, "Earnings metric is invalid.");
  const unit = text(row.unit, "Earnings metric unit is missing.");
  if (unit !== "USD" && unit !== "USD/shares") throw new Error("Earnings metric unit is unsupported.");
  const concept = text(row.concept, "Earnings metric concept is missing.");
  if (!concept.startsWith("us-gaap:")) throw new Error("Earnings metric concept must be US-GAAP.");
  return {
    concept,
    unit,
    value: finite(row.value, "Earnings metric value is invalid."),
    prior_year_value: finite(row.prior_year_value, "Earnings prior-year value is invalid."),
    yoy_change_pct: finite(row.yoy_change_pct, "Earnings year-over-year change is invalid.")
  };
}

function company(value: unknown): EarningsCompany {
  const row = record(value, "Earnings company is invalid.");
  const fiscal_period = text(row.fiscal_period, "Earnings fiscal period is missing.") as EarningsCompany["fiscal_period"];
  if (!["Q1", "Q2", "Q3", "Q4"].includes(fiscal_period)) throw new Error("Earnings fiscal period is unsupported.");
  const fiscal_year = finite(row.fiscal_year, "Earnings fiscal year is invalid.");
  if (!Number.isInteger(fiscal_year)) throw new Error("Earnings fiscal year is invalid.");
  return {
    ticker: text(row.ticker, "Earnings ticker is missing."),
    slug: text(row.slug, "Earnings company slug is missing."),
    cik: text(row.cik, "Earnings CIK is missing."),
    name: text(row.name, "Earnings company name is missing."),
    fiscal_year,
    fiscal_period,
    period_start: text(row.period_start, "Earnings period start is missing."),
    period_end: text(row.period_end, "Earnings period end is missing."),
    prior_year_period_start: text(row.prior_year_period_start, "Earnings prior period start is missing."),
    prior_year_period_end: text(row.prior_year_period_end, "Earnings prior period end is missing."),
    filed_at: text(row.filed_at, "Earnings filing date is missing."),
    accession: text(row.accession, "Earnings accession is missing."),
    form: row.form === "10-Q" ? "10-Q" : (() => { throw new Error("Earnings form must be 10-Q."); })(),
    filing_url: secUrl(row.filing_url, "www.sec.gov", "Earnings filing URL is invalid."),
    companyfacts_url: secUrl(row.companyfacts_url, "data.sec.gov", "Earnings Company Facts URL is invalid."),
    revenue: metric(row.revenue),
    diluted_eps: metric(row.diluted_eps)
  };
}

export function parseEarningsCatalog(value: unknown): EarningsCatalog {
  const catalog = record(value, "Earnings catalog is invalid.");
  if (catalog.schema_version !== "earnings-catalog.v1") throw new Error("Earnings catalog schema is unsupported.");
  if (!Array.isArray(catalog.companies) || catalog.companies.length === 0 || !Array.isArray(catalog.limitations) || catalog.limitations.length === 0) throw new Error("Earnings catalog collections are invalid.");
  const manifest_hash = text(catalog.manifest_hash, "Earnings manifest is missing.");
  const source_manifest_hash = text(catalog.source_manifest_hash, "Earnings source manifest is missing.");
  if (!/^[a-f0-9]{64}$/.test(manifest_hash) || !/^[a-f0-9]{64}$/.test(source_manifest_hash)) throw new Error("Earnings hash is invalid.");
  const companies = catalog.companies.map(company);
  if (new Set(companies.map((item) => item.ticker)).size !== companies.length || new Set(companies.map((item) => item.slug)).size !== companies.length) throw new Error("Earnings company identities must be unique.");
  return {
    schema_version: "earnings-catalog.v1",
    release_id: text(catalog.release_id, "Earnings release ID is missing."),
    manifest_hash,
    source_manifest_hash,
    observed_at: text(catalog.observed_at, "Earnings observation time is missing."),
    source_retrieved_at: text(catalog.source_retrieved_at, "Earnings source retrieval time is missing."),
    scope: text(catalog.scope, "Earnings scope is missing."),
    methodology: text(catalog.methodology, "Earnings methodology is missing."),
    limitations: catalog.limitations.map((item) => text(item, "Earnings limitation is invalid.")),
    companies
  };
}

export const earningsCatalog = parseEarningsCatalog(rawCatalog);
const earningsRelease = releaseFor("earnings");
if (earningsRelease.release_id !== earningsCatalog.release_id || earningsRelease.manifest_hash !== earningsCatalog.manifest_hash) {
  throw new Error("Earnings catalog is not bound to the active public release.");
}

export function earningsForTicker(ticker: string): EarningsCompany | null {
  return earningsCatalog.companies.find((company) => company.ticker === ticker) ?? null;
}
