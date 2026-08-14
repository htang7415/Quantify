export type FomcDetails = {
  kind: "fomc_decision";
  decision: "maintained";
  target_range_low_pct: number;
  target_range_high_pct: number;
  vote_for: number;
  vote_against: number;
  implementation_source_url: string;
  implementation_source_sha256: string;
  next_meeting_start: string;
  next_meeting_end: string;
  calendar_source_url: string;
  calendar_source_sha256: string;
};

export type JointStandardsDetails = {
  kind: "joint_data_standards";
  rule_type: "final";
  release_numbers: string[];
  federal_register_publish_date: string;
  reporting_requirements_change_at_effective_date: false;
  agencies: string[];
  standard_domains: string[];
};

export type ExportRuleDetails = {
  kind: "advanced_computing_export_rule";
  rule_type: "final";
  federal_register_citation: string;
  review_policy_before: "presumption_of_denial";
  review_policy_after: "case_by_case_if_conditions_met";
  destinations: string[];
  named_products: string[];
  related_company_tickers: string[];
  conditions: string[];
};

export type PolicyDetails = FomcDetails | JointStandardsDetails | ExportRuleDetails;

export type PolicyEvent = {
  event_id: string;
  category: "monetary_policy" | "financial_regulation" | "trade_export_controls";
  authority_id: string;
  authority_name: string;
  title: string;
  action_type: "decision" | "final_rule";
  status: "active" | "scheduled_effective";
  published_at: string;
  effective_at: string;
  source_document_id: string;
  source_url: string;
  source_sha256: string;
  details: PolicyDetails;
};

export type PolicyEventCatalog = {
  schema_version: "policy-event-catalog.v1";
  release_id: string;
  manifest_hash: string;
  source_record_hash: string;
  observed_at: string;
  retrieved_at: string;
  scope: string;
  methodology: string;
  limitations: string[];
  events: PolicyEvent[];
};
