import rawCatalog from "../data/etfHoldingsCatalog.json";
import { releaseFor } from "../releases/catalog";
import { etfFlowCatalog } from "./catalog";
import type { EtfExposure, EtfHoldingsCatalog, EtfHoldingsFund } from "./holdingsTypes";

function parseCatalog(value: unknown): EtfHoldingsCatalog {
  if (!value || typeof value !== "object") throw new Error("ETF holdings catalog is invalid.");
  const catalog = value as EtfHoldingsCatalog;
  if (catalog.schema_version !== "etf-holdings-catalog.v1" || !Array.isArray(catalog.funds) || catalog.funds.length !== 3) throw new Error("ETF holdings catalog contract is invalid.");
  if (catalog.flow_release_id !== etfFlowCatalog.release_id || catalog.flow_manifest_hash !== etfFlowCatalog.manifest_hash) throw new Error("ETF holdings flow binding is invalid.");
  for (const fund of catalog.funds) {
    if (fund.holdings.length !== 10 || fund.published_holding_rows !== 10 || !fund.source_url.startsWith("https://www.sec.gov/")) throw new Error("ETF holdings fund contract is invalid.");
    const concentration = fund.holdings.reduce((total, holding, index) => {
      if (holding.rank !== index + 1 || (index > 0 && holding.filed_percentage > fund.holdings[index - 1].filed_percentage)) throw new Error("ETF holdings rank contract is invalid.");
      return total + holding.filed_percentage;
    }, 0);
    if (Math.abs(concentration - fund.top_ten_concentration_pct) > 0.000001) throw new Error("ETF holdings concentration is invalid.");
  }
  const release = releaseFor("etf_holdings");
  if (release.release_id !== catalog.release_id || release.manifest_hash !== catalog.manifest_hash) throw new Error("ETF holdings release binding is invalid.");
  return catalog;
}

export const etfHoldingsCatalog = parseCatalog(rawCatalog);

export function etfHoldingsFund(slugOrTicker: string): EtfHoldingsFund | undefined {
  const key = slugOrTicker.toLowerCase();
  return etfHoldingsCatalog.funds.find((fund) => fund.slug === key || fund.ticker.toLowerCase() === key);
}

export function etfExposuresForTicker(ticker: string): EtfExposure[] {
  return etfHoldingsCatalog.funds
    .flatMap((fund) => fund.holdings.filter((holding) => holding.ticker === ticker).map((holding) => ({ fund, holding })))
    .sort((left, right) => right.holding.filed_percentage - left.holding.filed_percentage);
}
