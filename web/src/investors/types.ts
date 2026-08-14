export type ChangeKind = "new" | "added" | "reduced" | "exited" | "unchanged";
export type ManagerStatus = "available" | "source_review";

export type FilingReference = {
  form: string;
  report_period: string;
  filed_date: string;
  accession: string;
  source_url: string;
};

export type Holding = {
  security_id: string;
  issuer: string;
  ticker: string | null;
  cusip: string;
  title: string;
  instrument_type: string;
  put_call: string | null;
  value_usd: number;
  previous_value_usd?: number;
  shares: number;
  weight_pct: number;
  weight_delta_pp: number;
  share_delta_pct: number | null;
  change: ChangeKind;
  theme: string | null;
};

export type Allocation = { label: string; weight_pct: number };
export type HistorySeries = {
  security_id: string;
  issuer: string;
  ticker: string | null;
  points: Array<{ period: string; weight_pct: number }>;
};

export type InvestorManager = {
  slug: string;
  firm: string;
  person: string | null;
  reporting_manager_name: string;
  reporting_manager_cik: string;
  category: string;
  primary_theme: string;
  latest_filing: FilingReference;
  status: ManagerStatus;
  status_reason: string | null;
  disclosed_portfolio_value_usd: number | null;
  holdings_count: number | null;
  top_five_concentration_pct: number | null;
  classification_coverage_pct: number;
  holdings: Holding[];
  changes: Holding[];
  allocation: Allocation[];
  history: HistorySeries[];
};

export type InvestorCatalog = {
  schema_version: "investor-catalog.v1";
  release_id: string;
  manifest_hash: string;
  source: string;
  report_period: string;
  source_fresh_through: string;
  limitations: string[];
  managers: InvestorManager[];
};
