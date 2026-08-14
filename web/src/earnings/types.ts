export type EarningsMetric = {
  concept: string;
  unit: "USD" | "USD/shares";
  value: number;
  prior_year_value: number;
  yoy_change_pct: number;
};

export type EarningsCompany = {
  ticker: string;
  slug: string;
  cik: string;
  name: string;
  fiscal_year: number;
  fiscal_period: "Q1" | "Q2" | "Q3" | "Q4";
  period_start: string;
  period_end: string;
  prior_year_period_start: string;
  prior_year_period_end: string;
  filed_at: string;
  accession: string;
  form: "10-Q";
  filing_url: string;
  companyfacts_url: string;
  revenue: EarningsMetric;
  diluted_eps: EarningsMetric;
};

export type EarningsCatalog = {
  schema_version: "earnings-catalog.v1";
  release_id: string;
  manifest_hash: string;
  source_manifest_hash: string;
  observed_at: string;
  source_retrieved_at: string;
  scope: string;
  methodology: string;
  limitations: string[];
  companies: EarningsCompany[];
};
