import type { ChangeKind } from "../investors/types";

export type CryptoExposurePosition = {
  manager_slug: string;
  manager_firm: string;
  reporting_manager_name: string;
  reporting_manager_cik: string;
  fund_ticker: string;
  fund_name: string;
  cusip: string;
  value_usd: number;
  shares: number;
  portfolio_weight_pct: number;
  change: Exclude<ChangeKind, "exited">;
  share_delta_pct: number | null;
  filing_accession: string;
  filing_source_url: string;
  identity_source_url: string;
};

export type CryptoExposureAsset = {
  asset_id: string;
  slug: string;
  name: string;
  symbol: string;
  network: string;
  market_data_status: "unavailable";
  reported_etp_value_usd: number;
  reporting_manager_count: number;
  positions: CryptoExposurePosition[];
};

export type CryptoExposureCatalog = {
  schema_version: "crypto-exposure-catalog.v1";
  release_id: string;
  manifest_hash: string;
  investor_release_id: string;
  investor_manifest_hash: string;
  report_period: string;
  source: string;
  limitations: string[];
  assets: CryptoExposureAsset[];
};
