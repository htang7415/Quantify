import rawCatalog from "../data/treasuryRatesCatalog.json";
import { releaseFor } from "../releases/catalog";
import type { TreasuryCurvePoint, TreasuryRatesCatalog, TreasurySpread } from "./types";

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

function officialUrl(value: unknown, message: string): string {
  const parsed = text(value, message);
  if (!parsed.startsWith("https://home.treasury.gov/")) throw new Error(message);
  return parsed;
}

function point(value: unknown): TreasuryCurvePoint {
  const row = record(value, "Treasury curve point is invalid.");
  const years = finite(row.years, "Treasury curve maturity is invalid.");
  const yield_pct = finite(row.yield_pct, "Treasury curve yield is invalid.");
  if (years <= 0 || yield_pct < -5 || yield_pct > 25) throw new Error("Treasury curve point is outside the permitted range.");
  return { maturity: text(row.maturity, "Treasury curve label is missing."), years, yield_pct };
}

function spread(value: unknown): TreasurySpread {
  const row = record(value, "Treasury spread is invalid.");
  if (!Array.isArray(row.derived_from) || row.derived_from.length !== 2) throw new Error("Treasury spread inputs are invalid.");
  return {
    name: text(row.name, "Treasury spread name is missing."),
    value_pp: finite(row.value_pp, "Treasury spread value is invalid."),
    derived_from: [text(row.derived_from[0], "Treasury spread input is missing."), text(row.derived_from[1], "Treasury spread input is missing.")]
  };
}

export function parseTreasuryRatesCatalog(value: unknown): TreasuryRatesCatalog {
  const catalog = record(value, "Treasury rates catalog is invalid.");
  if (catalog.schema_version !== "treasury-rates-catalog.v1") throw new Error("Treasury rates catalog schema is unsupported.");
  if (!Array.isArray(catalog.curve) || !Array.isArray(catalog.spreads) || !Array.isArray(catalog.limitations) || catalog.limitations.length === 0) throw new Error("Treasury rates catalog collections are invalid.");
  const manifest_hash = text(catalog.manifest_hash, "Treasury rates manifest is missing.");
  const source_record_hash = text(catalog.source_record_hash, "Treasury source record hash is missing.");
  if (!/^[a-f0-9]{64}$/.test(manifest_hash) || !/^[a-f0-9]{64}$/.test(source_record_hash)) throw new Error("Treasury rates hash is invalid.");
  const parsed: TreasuryRatesCatalog = {
    schema_version: "treasury-rates-catalog.v1",
    release_id: text(catalog.release_id, "Treasury rates release ID is missing."),
    manifest_hash,
    source_record_hash,
    observed_at: text(catalog.observed_at, "Treasury observation time is missing."),
    published_at: text(catalog.published_at, "Treasury publication time is missing."),
    fresh_until: text(catalog.fresh_until, "Treasury freshness limit is missing."),
    source_url: officialUrl(catalog.source_url, "Treasury source URL is invalid."),
    source_record_id: officialUrl(catalog.source_record_id, "Treasury record URL is invalid."),
    methodology: text(catalog.methodology, "Treasury methodology is missing."),
    limitations: catalog.limitations.map((item) => text(item, "Treasury limitation is invalid.")),
    curve: catalog.curve.map(point),
    spreads: catalog.spreads.map(spread)
  };
  if (new Set(parsed.curve.map((item) => item.maturity)).size !== parsed.curve.length) throw new Error("Treasury curve maturities must be unique.");
  return parsed;
}

export const treasuryRatesCatalog = parseTreasuryRatesCatalog(rawCatalog);
const ratesRelease = releaseFor("rates");
if (ratesRelease.release_id !== treasuryRatesCatalog.release_id || ratesRelease.manifest_hash !== treasuryRatesCatalog.manifest_hash) {
  throw new Error("Treasury rates catalog is not bound to the active public release.");
}

export function ratesFreshness(now = new Date()): "current" | "stale" {
  return now.getTime() <= new Date(treasuryRatesCatalog.fresh_until).getTime() ? "current" : "stale";
}

export function rate(maturity: string): number {
  const value = treasuryRatesCatalog.curve.find((point) => point.maturity === maturity)?.yield_pct;
  if (value === undefined) throw new Error(`Treasury release does not contain ${maturity}.`);
  return value;
}
