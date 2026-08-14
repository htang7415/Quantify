export type EtfHolding = {
  rank: number;
  holding_id: string;
  issuer_name: string;
  issuer_title: string;
  cusip: string;
  ticker: string | null;
  theme: string | null;
  balance: number;
  unit: string;
  currency_code: string;
  currency_value: number;
  filed_percentage: number;
  investment_country: string;
};

export type EtfHoldingsFund = {
  fund_id: string;
  ticker: "VGT" | "QQQ" | "SMH";
  slug: "vgt" | "qqq" | "smh";
  name: string;
  accession: string;
  filed_date: string;
  report_date: string;
  net_assets_usd: number;
  total_holding_rows: number;
  published_holding_rows: 10;
  top_ten_concentration_pct: number;
  holdings: EtfHolding[];
  source_url: string;
};

export type EtfHoldingsCatalog = {
  schema_version: "etf-holdings-catalog.v1";
  release_id: string;
  manifest_hash: string;
  source_record_hash: string;
  flow_release_id: string;
  flow_manifest_hash: string;
  security_metadata_hash: string;
  dataset_period: string;
  dataset_url: string;
  dataset_sha256: string;
  dataset_published_at: string;
  retrieved_at: string;
  observed_at: string;
  fresh_until: string;
  selection_rule: "top_10_by_filed_percentage_desc";
  scope: string;
  methodology: string;
  limitations: string[];
  funds: EtfHoldingsFund[];
};

export type EtfExposure = {
  fund: EtfHoldingsFund;
  holding: EtfHolding;
};
