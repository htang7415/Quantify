import rawCatalog from "../data/investorCatalog.json";
import type { ChangeKind, InvestorCatalog, InvestorManager } from "./types";

const changeKinds = new Set<ChangeKind>(["new", "added", "reduced", "exited", "unchanged"]);

function record(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(message);
  return value as Record<string, unknown>;
}

function stringValue(value: unknown, message: string): string {
  if (typeof value !== "string" || !value) throw new Error(message);
  return value;
}

function finiteNumber(value: unknown, message: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(message);
  return value;
}

function nullableNumber(value: unknown, message: string): number | null {
  return value === null ? null : finiteNumber(value, message);
}

function matchingString(value: unknown, pattern: RegExp, message: string): string {
  const parsed = stringValue(value, message);
  if (!pattern.test(parsed)) throw new Error(message);
  return parsed;
}

function parseManager(value: unknown): InvestorManager {
  const manager = record(value, "Investor catalog contains an invalid manager.");
  const status = stringValue(manager.status, "Investor manager status is missing.");
  if (status !== "available" && status !== "source_review") throw new Error("Investor manager status is invalid.");
  const filing = record(manager.latest_filing, "Investor filing reference is invalid.");
  const holdings = Array.isArray(manager.holdings) ? manager.holdings : null;
  const changes = Array.isArray(manager.changes) ? manager.changes : null;
  const allocation = Array.isArray(manager.allocation) ? manager.allocation : null;
  const history = Array.isArray(manager.history) ? manager.history : null;
  if (!holdings || !changes || !allocation || !history) throw new Error("Investor manager collections are invalid.");

  const parsedHoldings = holdings.map((item) => {
    const holding = record(item, "Investor holding is invalid.");
    const change = stringValue(holding.change, "Investor holding change is missing.") as ChangeKind;
    if (!changeKinds.has(change)) throw new Error("Investor holding change is invalid.");
    return {
      security_id: stringValue(holding.security_id, "Investor security ID is missing."),
      issuer: stringValue(holding.issuer, "Investor holding issuer is missing."),
      ticker: holding.ticker === null ? null : stringValue(holding.ticker, "Investor ticker is invalid."),
      cusip: stringValue(holding.cusip, "Investor CUSIP is missing."),
      title: stringValue(holding.title, "Investor security class is missing."),
      instrument_type: stringValue(holding.instrument_type, "Investor instrument type is missing."),
      put_call: holding.put_call === null ? null : stringValue(holding.put_call, "Investor option type is invalid."),
      value_usd: finiteNumber(holding.value_usd, "Investor holding value is invalid."),
      ...(holding.previous_value_usd === undefined ? {} : { previous_value_usd: finiteNumber(holding.previous_value_usd, "Previous value is invalid.") }),
      shares: finiteNumber(holding.shares, "Investor share amount is invalid."),
      weight_pct: finiteNumber(holding.weight_pct, "Investor weight is invalid."),
      weight_delta_pp: finiteNumber(holding.weight_delta_pp, "Investor weight change is invalid."),
      share_delta_pct: nullableNumber(holding.share_delta_pct, "Investor share change is invalid."),
      change,
      theme: holding.theme === null ? null : stringValue(holding.theme, "Investor theme is invalid.")
    };
  });

  // Changes share the same strict public fields as holdings.
  const parsedChanges = changes.map((item) => parseManager({ ...manager, holdings: [item], changes: [], allocation: [], history: [] }).holdings[0]);
  const parsedAllocation = allocation.map((item) => {
    const row = record(item, "Investor allocation is invalid.");
    return { label: stringValue(row.label, "Investor allocation label is missing."), weight_pct: finiteNumber(row.weight_pct, "Investor allocation weight is invalid.") };
  });
  const parsedHistory = history.map((item) => {
    const series = record(item, "Investor history is invalid.");
    if (!Array.isArray(series.points)) throw new Error("Investor history points are invalid.");
    return {
      security_id: stringValue(series.security_id, "Investor history security ID is missing."),
      issuer: stringValue(series.issuer, "Investor history issuer is missing."),
      ticker: series.ticker === null ? null : stringValue(series.ticker, "Investor history ticker is invalid."),
      points: series.points.map((point) => {
        const row = record(point, "Investor history point is invalid.");
        return { period: stringValue(row.period, "Investor history period is missing."), weight_pct: finiteNumber(row.weight_pct, "Investor history weight is invalid.") };
      })
    };
  });

  return {
    slug: stringValue(manager.slug, "Investor slug is missing."),
    firm: stringValue(manager.firm, "Investor firm is missing."),
    person: manager.person === null ? null : stringValue(manager.person, "Investor name is invalid."),
    reporting_manager_name: stringValue(manager.reporting_manager_name, "Reporting manager name is missing."),
    reporting_manager_cik: stringValue(manager.reporting_manager_cik, "Reporting manager CIK is missing."),
    category: stringValue(manager.category, "Investor category is missing."),
    primary_theme: stringValue(manager.primary_theme, "Investor theme is missing."),
    latest_filing: {
      form: stringValue(filing.form, "Investor form is missing."),
      report_period: stringValue(filing.report_period, "Investor report period is missing."),
      filed_date: stringValue(filing.filed_date, "Investor filing date is missing."),
      accession: stringValue(filing.accession, "Investor accession is missing."),
      source_url: matchingString(filing.source_url, /^https:\/\/www\.sec\.gov\//, "Investor source URL is invalid.")
    },
    status,
    status_reason: manager.status_reason === null ? null : stringValue(manager.status_reason, "Investor status reason is invalid."),
    disclosed_portfolio_value_usd: nullableNumber(manager.disclosed_portfolio_value_usd, "Investor disclosed value is invalid."),
    holdings_count: nullableNumber(manager.holdings_count, "Investor holdings count is invalid."),
    top_five_concentration_pct: nullableNumber(manager.top_five_concentration_pct, "Investor concentration is invalid."),
    classification_coverage_pct: finiteNumber(manager.classification_coverage_pct, "Investor classification coverage is invalid."),
    holdings: parsedHoldings,
    changes: parsedChanges,
    allocation: parsedAllocation,
    history: parsedHistory
  };
}

export function parseInvestorCatalog(value: unknown): InvestorCatalog {
  const catalog = record(value, "Investor catalog is invalid.");
  if (catalog.schema_version !== "investor-catalog.v1") throw new Error("Investor catalog schema is unsupported.");
  if (!Array.isArray(catalog.limitations) || !Array.isArray(catalog.managers)) throw new Error("Investor catalog collections are invalid.");
  const managers = catalog.managers.map(parseManager);
  const slugs = new Set(managers.map((manager) => manager.slug));
  if (slugs.size !== managers.length) throw new Error("Investor catalog manager slugs must be unique.");
  return {
    schema_version: "investor-catalog.v1",
    release_id: stringValue(catalog.release_id, "Investor release ID is missing."),
    manifest_hash: matchingString(catalog.manifest_hash, /^[a-f0-9]{64}$/, "Investor manifest hash is invalid."),
    source: stringValue(catalog.source, "Investor source is missing."),
    report_period: stringValue(catalog.report_period, "Investor report period is missing."),
    source_fresh_through: stringValue(catalog.source_fresh_through, "Investor source date is missing."),
    limitations: catalog.limitations.map((item) => stringValue(item, "Investor limitation is invalid.")),
    managers
  };
}

export const investorCatalog = parseInvestorCatalog(rawCatalog);
