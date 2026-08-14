import rawCatalog from "../data/etfFlowCatalog.json";
import { releaseFor } from "../releases/catalog";
import type { EtfFlowCatalog } from "./types";

function parseCatalog(value: unknown): EtfFlowCatalog {
  if (!value || typeof value !== "object") throw new Error("ETF flow catalog is invalid.");
  const catalog = value as EtfFlowCatalog;
  if (catalog.schema_version !== "etf-flow-catalog.v2" || !Array.isArray(catalog.funds) || catalog.funds.length !== 5) throw new Error("ETF flow catalog contract is invalid.");
  for (const fund of catalog.funds) {
    if (!fund.ticker || !fund.source_url.startsWith("https://www.sec.gov/") || fund.months.length !== 3 || fund.monthly_flows.length !== 3) throw new Error("ETF flow fund contract is invalid.");
    if (fund.monthly_flows.some((row, index) => row.month !== fund.months[index])) throw new Error("ETF flow month binding is invalid.");
    for (const row of fund.monthly_flows) {
      const expected = row.sales_nav_usd + row.reinvestment_nav_usd - row.redemption_nav_usd;
      if (Math.abs(expected - row.net_flow_usd) > 0.01) throw new Error("ETF flow arithmetic is invalid.");
    }
  }
  const release = releaseFor("etf_flows");
  if (release.release_id !== catalog.release_id || release.manifest_hash !== catalog.manifest_hash) throw new Error("ETF flow release binding is invalid.");
  return catalog;
}

export const etfFlowCatalog = parseCatalog(rawCatalog);

export function etfFreshness(now = new Date()): "current" | "stale" {
  return now.getTime() <= new Date(etfFlowCatalog.fresh_until).getTime() ? "current" : "stale";
}
