import rawCatalog from "../data/policyEventCatalog.json";
import { releaseFor } from "../releases/catalog";
import type { ExportRuleDetails, FomcDetails, JointStandardsDetails, PolicyDetails, PolicyEvent, PolicyEventCatalog } from "./types";

function record(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(message);
  return value as Record<string, unknown>;
}

function text(value: unknown, message: string): string {
  if (typeof value !== "string" || !value) throw new Error(message);
  return value;
}

function finite(value: unknown, message: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(message);
  return value;
}

function integer(value: unknown, message: string): number {
  const parsed = finite(value, message);
  if (!Number.isInteger(parsed)) throw new Error(message);
  return parsed;
}

function strings(value: unknown, message: string, expected?: number): string[] {
  if (!Array.isArray(value) || value.length === 0 || (expected !== undefined && value.length !== expected)) throw new Error(message);
  const values = value.map((item) => text(item, message));
  if (new Set(values).size !== values.length) throw new Error(message);
  return values;
}

function hash(value: unknown, message: string): string {
  const parsed = text(value, message);
  if (!/^[a-f0-9]{64}$/.test(parsed)) throw new Error(message);
  return parsed;
}

function officialUrl(value: unknown, message: string): string {
  const parsed = text(value, message);
  if (!/^https:\/\/(www\.federalreserve\.gov|www\.sec\.gov|www\.federalregister\.gov)\//.test(parsed)) throw new Error(message);
  return parsed;
}

function details(value: unknown): PolicyDetails {
  const row = record(value, "Policy details are invalid.");
  if (row.kind === "fomc_decision") {
    const low = finite(row.target_range_low_pct, "FOMC target range is invalid.");
    const high = finite(row.target_range_high_pct, "FOMC target range is invalid.");
    if (row.decision !== "maintained" || low < 0 || high <= low || high > 20) throw new Error("FOMC decision is invalid.");
    return {
      kind: "fomc_decision",
      decision: "maintained",
      target_range_low_pct: low,
      target_range_high_pct: high,
      vote_for: integer(row.vote_for, "FOMC vote is invalid."),
      vote_against: integer(row.vote_against, "FOMC vote is invalid."),
      implementation_source_url: officialUrl(row.implementation_source_url, "FOMC implementation source is invalid."),
      implementation_source_sha256: hash(row.implementation_source_sha256, "FOMC implementation hash is invalid."),
      next_meeting_start: text(row.next_meeting_start, "FOMC meeting date is missing."),
      next_meeting_end: text(row.next_meeting_end, "FOMC meeting date is missing."),
      calendar_source_url: officialUrl(row.calendar_source_url, "FOMC calendar source is invalid."),
      calendar_source_sha256: hash(row.calendar_source_sha256, "FOMC calendar hash is invalid.")
    } satisfies FomcDetails;
  }
  if (row.kind === "joint_data_standards") {
    if (row.rule_type !== "final" || row.reporting_requirements_change_at_effective_date !== false) throw new Error("Joint data standards status is invalid.");
    return {
      kind: "joint_data_standards",
      rule_type: "final",
      release_numbers: strings(row.release_numbers, "Joint data standards releases are invalid."),
      federal_register_publish_date: text(row.federal_register_publish_date, "Joint data standards publication date is missing."),
      reporting_requirements_change_at_effective_date: false,
      agencies: strings(row.agencies, "Joint data standards agencies are invalid.", 9),
      standard_domains: strings(row.standard_domains, "Joint data standards domains are invalid.")
    } satisfies JointStandardsDetails;
  }
  if (row.kind === "advanced_computing_export_rule") {
    if (row.rule_type !== "final" || row.review_policy_before !== "presumption_of_denial" || row.review_policy_after !== "case_by_case_if_conditions_met") throw new Error("Export-control review policy is invalid.");
    return {
      kind: "advanced_computing_export_rule",
      rule_type: "final",
      federal_register_citation: text(row.federal_register_citation, "Federal Register citation is missing."),
      review_policy_before: "presumption_of_denial",
      review_policy_after: "case_by_case_if_conditions_met",
      destinations: strings(row.destinations, "Export-control destinations are invalid."),
      named_products: strings(row.named_products, "Export-control products are invalid."),
      related_company_tickers: strings(row.related_company_tickers, "Export-control tickers are invalid."),
      conditions: strings(row.conditions, "Export-control conditions are invalid.", 4)
    } satisfies ExportRuleDetails;
  }
  throw new Error("Policy detail kind is unsupported.");
}

function event(value: unknown): PolicyEvent {
  const row = record(value, "Policy event is invalid.");
  const category = text(row.category, "Policy category is missing.") as PolicyEvent["category"];
  const action_type = text(row.action_type, "Policy action type is missing.") as PolicyEvent["action_type"];
  const status = text(row.status, "Policy status is missing.") as PolicyEvent["status"];
  if (!["monetary_policy", "financial_regulation", "trade_export_controls"].includes(category) || !["decision", "final_rule"].includes(action_type) || !["active", "scheduled_effective"].includes(status)) throw new Error("Policy classification is invalid.");
  return {
    event_id: text(row.event_id, "Policy event ID is missing."),
    category,
    authority_id: text(row.authority_id, "Policy authority ID is missing."),
    authority_name: text(row.authority_name, "Policy authority is missing."),
    title: text(row.title, "Policy title is missing."),
    action_type,
    status,
    published_at: text(row.published_at, "Policy publication date is missing."),
    effective_at: text(row.effective_at, "Policy effective date is missing."),
    source_document_id: text(row.source_document_id, "Policy source document ID is missing."),
    source_url: officialUrl(row.source_url, "Policy source URL is invalid."),
    source_sha256: hash(row.source_sha256, "Policy source hash is invalid."),
    details: details(row.details)
  };
}

export function parsePolicyEventCatalog(value: unknown): PolicyEventCatalog {
  const catalog = record(value, "Policy event catalog is invalid.");
  if (catalog.schema_version !== "policy-event-catalog.v1") throw new Error("Policy event catalog schema is unsupported.");
  if (!Array.isArray(catalog.events) || catalog.events.length !== 3 || !Array.isArray(catalog.limitations) || catalog.limitations.length === 0) throw new Error("Policy event catalog collections are invalid.");
  const manifest_hash = hash(catalog.manifest_hash, "Policy manifest is invalid.");
  const source_record_hash = hash(catalog.source_record_hash, "Policy source record hash is invalid.");
  const events = catalog.events.map(event);
  if (new Set(events.map((item) => item.event_id)).size !== events.length) throw new Error("Policy event IDs must be unique.");
  return {
    schema_version: "policy-event-catalog.v1",
    release_id: text(catalog.release_id, "Policy release ID is missing."),
    manifest_hash,
    source_record_hash,
    observed_at: text(catalog.observed_at, "Policy observation time is missing."),
    retrieved_at: text(catalog.retrieved_at, "Policy retrieval time is missing."),
    scope: text(catalog.scope, "Policy scope is missing."),
    methodology: text(catalog.methodology, "Policy methodology is missing."),
    limitations: catalog.limitations.map((item) => text(item, "Policy limitation is invalid.")),
    events
  };
}

export const policyEventCatalog = parsePolicyEventCatalog(rawCatalog);
const policyRelease = releaseFor("policy");
if (policyRelease.release_id !== policyEventCatalog.release_id || policyRelease.manifest_hash !== policyEventCatalog.manifest_hash) throw new Error("Policy event catalog is not bound to the active public release.");

export function policyEventsForTicker(ticker: string): PolicyEvent[] {
  return policyEventCatalog.events.filter((item) => item.details.kind === "advanced_computing_export_rule" && item.details.related_company_tickers.includes(ticker));
}
