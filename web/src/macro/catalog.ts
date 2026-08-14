import rawCatalog from "../data/blsMacroCatalog.json";
import { releaseFor } from "../releases/catalog";
import type { BlsMacroCatalog, MacroInput, MacroMetricId, MacroObservation } from "./types";

const metricIds = new Set<MacroMetricId>(["headline_cpi_yoy", "core_cpi_yoy", "unemployment_rate"]);
const adjustments = new Set(["not_seasonally_adjusted", "seasonally_adjusted"]);
const derivations = new Set(["year_over_year_percent_change", "published_value"]);

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

function month(value: unknown, message: string): string {
  const parsed = text(value, message);
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(parsed)) throw new Error(message);
  return parsed;
}

function input(value: unknown): MacroInput {
  const row = record(value, "BLS macro input is invalid.");
  return { period: month(row.period, "BLS macro input period is invalid."), value: finite(row.value, "BLS macro input value is invalid.") };
}

function observation(value: unknown): MacroObservation {
  const row = record(value, "BLS macro observation is invalid.");
  const metric_id = text(row.metric_id, "BLS macro metric ID is missing.") as MacroMetricId;
  const seasonal_adjustment = text(row.seasonal_adjustment, "BLS macro adjustment is missing.") as MacroObservation["seasonal_adjustment"];
  const derivation = text(row.derivation, "BLS macro derivation is missing.") as MacroObservation["derivation"];
  const source_url = text(row.source_url, "BLS macro source is missing.");
  if (!metricIds.has(metric_id) || !adjustments.has(seasonal_adjustment) || !derivations.has(derivation)) throw new Error("BLS macro observation contains an unsupported value.");
  if (!source_url.startsWith("https://api.bls.gov/")) throw new Error("BLS macro source must use the official API host.");
  if (!Array.isArray(row.inputs) || row.inputs.length < 2) throw new Error("BLS macro calculation inputs are missing.");
  return {
    metric_id,
    label: text(row.label, "BLS macro metric label is missing."),
    series_id: text(row.series_id, "BLS macro series ID is missing."),
    value_pct: finite(row.value_pct, "BLS macro value is invalid."),
    previous_value_pct: finite(row.previous_value_pct, "BLS macro previous value is invalid."),
    change_pp: finite(row.change_pp, "BLS macro change is invalid."),
    period: month(row.period, "BLS macro period is invalid."),
    previous_period: month(row.previous_period, "BLS macro previous period is invalid."),
    seasonal_adjustment,
    derivation,
    source_url,
    inputs: row.inputs.map(input)
  };
}

export function parseBlsMacroCatalog(value: unknown): BlsMacroCatalog {
  const catalog = record(value, "BLS macro catalog is invalid.");
  if (catalog.schema_version !== "bls-macro-catalog.v1") throw new Error("BLS macro catalog schema is unsupported.");
  if (!Array.isArray(catalog.observations) || catalog.observations.length !== 3 || !Array.isArray(catalog.limitations) || catalog.limitations.length === 0) throw new Error("BLS macro catalog collections are invalid.");
  const manifest_hash = text(catalog.manifest_hash, "BLS macro manifest is missing.");
  const source_record_hash = text(catalog.source_record_hash, "BLS source record hash is missing.");
  const terms_url = text(catalog.terms_url, "BLS macro terms URL is missing.");
  if (!/^[a-f0-9]{64}$/.test(manifest_hash) || !/^[a-f0-9]{64}$/.test(source_record_hash)) throw new Error("BLS macro hash is invalid.");
  if (!terms_url.startsWith("https://www.bls.gov/")) throw new Error("BLS macro terms must use the official host.");
  const observations = catalog.observations.map(observation);
  if (new Set(observations.map((item) => item.metric_id)).size !== observations.length) throw new Error("BLS macro metric IDs must be unique.");
  return {
    schema_version: "bls-macro-catalog.v1",
    release_id: text(catalog.release_id, "BLS macro release ID is missing."),
    manifest_hash,
    source_record_hash,
    observed_at: text(catalog.observed_at, "BLS macro observation time is missing."),
    observed_period: month(catalog.observed_period, "BLS macro observation period is invalid."),
    retrieved_at: text(catalog.retrieved_at, "BLS macro retrieval time is missing."),
    fresh_until: text(catalog.fresh_until, "BLS macro freshness limit is missing."),
    terms_url,
    methodology: text(catalog.methodology, "BLS macro methodology is missing."),
    disclaimer: text(catalog.disclaimer, "BLS macro disclaimer is missing."),
    limitations: catalog.limitations.map((item) => text(item, "BLS macro limitation is invalid.")),
    observations
  };
}

export const blsMacroCatalog = parseBlsMacroCatalog(rawCatalog);
const macroRelease = releaseFor("macro");
if (macroRelease.release_id !== blsMacroCatalog.release_id || macroRelease.manifest_hash !== blsMacroCatalog.manifest_hash) {
  throw new Error("BLS macro catalog is not bound to the active public release.");
}

export function macroFreshness(now = new Date()): "current" | "stale" {
  return now.getTime() <= new Date(blsMacroCatalog.fresh_until).getTime() ? "current" : "stale";
}

export function macroMetric(metricId: MacroMetricId): MacroObservation {
  const metric = blsMacroCatalog.observations.find((item) => item.metric_id === metricId);
  if (!metric) throw new Error(`BLS macro release does not contain ${metricId}.`);
  return metric;
}
