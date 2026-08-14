export type TreasuryCurvePoint = {
  maturity: string;
  years: number;
  yield_pct: number;
};

export type TreasurySpread = {
  name: string;
  value_pp: number;
  derived_from: [string, string];
};

export type TreasuryRatesCatalog = {
  schema_version: "treasury-rates-catalog.v1";
  release_id: string;
  manifest_hash: string;
  source_record_hash: string;
  observed_at: string;
  published_at: string;
  fresh_until: string;
  source_url: string;
  source_record_id: string;
  methodology: string;
  limitations: string[];
  curve: TreasuryCurvePoint[];
  spreads: TreasurySpread[];
};
