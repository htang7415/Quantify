export type MacroMetricId = "headline_cpi_yoy" | "core_cpi_yoy" | "unemployment_rate";

export type MacroInput = {
  period: string;
  value: number;
};

export type MacroObservation = {
  metric_id: MacroMetricId;
  label: string;
  series_id: string;
  value_pct: number;
  previous_value_pct: number;
  change_pp: number;
  period: string;
  previous_period: string;
  seasonal_adjustment: "not_seasonally_adjusted" | "seasonally_adjusted";
  derivation: "year_over_year_percent_change" | "published_value";
  source_url: string;
  inputs: MacroInput[];
};

export type BlsMacroCatalog = {
  schema_version: "bls-macro-catalog.v1";
  release_id: string;
  manifest_hash: string;
  source_record_hash: string;
  observed_at: string;
  observed_period: string;
  retrieved_at: string;
  fresh_until: string;
  terms_url: string;
  methodology: string;
  disclaimer: string;
  limitations: string[];
  observations: MacroObservation[];
};
