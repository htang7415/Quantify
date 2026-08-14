import rawCatalog from "../data/cryptoExposureCatalog.json";
import { investorCatalog } from "../investors/catalog";
import { releaseFor } from "../releases/catalog";
import type { ChangeKind } from "../investors/types";
import type { CryptoExposureAsset, CryptoExposureCatalog, CryptoExposurePosition } from "./types";

const changes = new Set<Exclude<ChangeKind, "exited">>(["new", "added", "reduced", "unchanged"]);

function record(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(message);
  return value as Record<string, unknown>;
}

function text(value: unknown, message: string): string {
  if (typeof value !== "string" || !value) throw new Error(message);
  return value;
}

function number(value: unknown, message: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) throw new Error(message);
  return value;
}

function signedNumber(value: unknown, message: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(message);
  return value;
}

function secUrl(value: unknown, message: string): string {
  const parsed = text(value, message);
  if (!parsed.startsWith("https://www.sec.gov/")) throw new Error(message);
  return parsed;
}

function parsePosition(value: unknown): CryptoExposurePosition {
  const row = record(value, "Crypto exposure position is invalid.");
  const change = text(row.change, "Crypto exposure change is missing.") as Exclude<ChangeKind, "exited">;
  if (!changes.has(change)) throw new Error("Crypto exposure change is invalid.");
  return {
    manager_slug: text(row.manager_slug, "Crypto exposure manager slug is missing."),
    manager_firm: text(row.manager_firm, "Crypto exposure manager firm is missing."),
    reporting_manager_name: text(row.reporting_manager_name, "Crypto exposure reporting manager is missing."),
    reporting_manager_cik: text(row.reporting_manager_cik, "Crypto exposure manager CIK is missing."),
    fund_ticker: text(row.fund_ticker, "Crypto exposure fund ticker is missing."),
    fund_name: text(row.fund_name, "Crypto exposure fund name is missing."),
    cusip: text(row.cusip, "Crypto exposure CUSIP is missing."),
    value_usd: number(row.value_usd, "Crypto exposure value is invalid."),
    shares: number(row.shares, "Crypto exposure shares are invalid."),
    portfolio_weight_pct: number(row.portfolio_weight_pct, "Crypto exposure portfolio weight is invalid."),
    change,
    share_delta_pct: row.share_delta_pct === null ? null : signedNumber(row.share_delta_pct, "Crypto exposure share change is invalid."),
    filing_accession: text(row.filing_accession, "Crypto exposure filing accession is missing."),
    filing_source_url: secUrl(row.filing_source_url, "Crypto exposure filing source is invalid."),
    identity_source_url: secUrl(row.identity_source_url, "Crypto exposure identity source is invalid.")
  };
}

function parseAsset(value: unknown): CryptoExposureAsset {
  const row = record(value, "Crypto exposure asset is invalid.");
  if (row.market_data_status !== "unavailable") throw new Error("Crypto exposure cannot publish market data.");
  if (!Array.isArray(row.positions)) throw new Error("Crypto exposure positions are invalid.");
  return {
    asset_id: text(row.asset_id, "Crypto asset ID is missing."),
    slug: text(row.slug, "Crypto asset slug is missing."),
    name: text(row.name, "Crypto asset name is missing."),
    symbol: text(row.symbol, "Crypto asset symbol is missing."),
    network: text(row.network, "Crypto asset network is missing."),
    market_data_status: "unavailable",
    reported_etp_value_usd: number(row.reported_etp_value_usd, "Crypto reported ETP value is invalid."),
    reporting_manager_count: number(row.reporting_manager_count, "Crypto reporting manager count is invalid."),
    positions: row.positions.map(parsePosition)
  };
}

export function parseCryptoExposureCatalog(value: unknown): CryptoExposureCatalog {
  const catalog = record(value, "Crypto exposure catalog is invalid.");
  if (catalog.schema_version !== "crypto-exposure-catalog.v1") throw new Error("Crypto exposure catalog schema is unsupported.");
  if (!Array.isArray(catalog.assets) || !Array.isArray(catalog.limitations) || catalog.limitations.length === 0) throw new Error("Crypto exposure catalog collections are invalid.");
  const manifest_hash = text(catalog.manifest_hash, "Crypto exposure manifest hash is missing.");
  if (!/^[a-f0-9]{64}$/.test(manifest_hash)) throw new Error("Crypto exposure manifest hash is invalid.");
  const parsed: CryptoExposureCatalog = {
    schema_version: "crypto-exposure-catalog.v1",
    release_id: text(catalog.release_id, "Crypto exposure release ID is missing."),
    manifest_hash,
    investor_release_id: text(catalog.investor_release_id, "Crypto exposure investor release ID is missing."),
    investor_manifest_hash: text(catalog.investor_manifest_hash, "Crypto exposure investor manifest is missing."),
    report_period: text(catalog.report_period, "Crypto exposure report period is missing."),
    source: text(catalog.source, "Crypto exposure source is missing."),
    limitations: catalog.limitations.map((item) => text(item, "Crypto exposure limitation is invalid.")),
    assets: catalog.assets.map(parseAsset)
  };
  if (new Set(parsed.assets.map((asset) => asset.asset_id)).size !== parsed.assets.length) throw new Error("Crypto asset IDs must be unique.");
  return parsed;
}

export const cryptoExposureCatalog = parseCryptoExposureCatalog(rawCatalog);
const exposureRelease = releaseFor("crypto_exposure");
if (
  cryptoExposureCatalog.investor_release_id !== investorCatalog.release_id ||
  cryptoExposureCatalog.investor_manifest_hash !== investorCatalog.manifest_hash ||
  exposureRelease.release_id !== cryptoExposureCatalog.release_id ||
  exposureRelease.manifest_hash !== cryptoExposureCatalog.manifest_hash
) {
  throw new Error("Crypto exposure release is not bound to the active public releases.");
}
