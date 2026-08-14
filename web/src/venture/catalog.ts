import rawCatalog from "../data/vcCatalog.json";
import { releaseFor } from "../releases/catalog";
import type { VentureCatalog, VentureFirm, VentureFollowOn, VentureRelationship, VentureRole, VentureSector, VentureStage } from "./types";

const sectors = new Set<VentureSector>(["ai", "autonomy", "climate_energy", "consumer", "defense", "enterprise_software", "fintech", "semiconductors", "space"]);
const stages = new Set<VentureStage>(["pre_seed_seed", "early", "growth", "undisclosed"]);
const roles = new Set<VentureRole>(["lead", "participant", "undisclosed"]);
const followOns = new Set<VentureFollowOn>(["yes", "no", "undisclosed"]);
const officialSource = /^https:\/\/((www\.)?(sequoiacap\.com|a16z\.com|foundersfund\.com|khoslaventures\.com|generalcatalyst\.com)|jobs\.thrivecap\.com)\//;
const hash = /^[a-f0-9]{64}$/;

function object(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(message);
  return value as Record<string, unknown>;
}

function exactKeys(value: Record<string, unknown>, expected: string[], message: string) {
  const actual = Object.keys(value).sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== [...expected].sort()[index])) throw new Error(message);
}

function text(value: unknown, message: string): string {
  if (typeof value !== "string" || !value) throw new Error(message);
  return value;
}

function patterned(value: unknown, pattern: RegExp, message: string): string {
  const parsed = text(value, message);
  if (!pattern.test(parsed)) throw new Error(message);
  return parsed;
}

function integer(value: unknown, message: string): number {
  if (!Number.isInteger(value) || (value as number) < 0) throw new Error(message);
  return value as number;
}

function parseRelationship(value: unknown, observedYear: number): VentureRelationship {
  const row = object(value, "Venture relationship is invalid.");
  exactKeys(row, ["company_id", "company_name", "sector", "first_partnered_year", "stage", "participation_role", "follow_on_status", "source_url", "source_sha256"], "Venture relationship fields are invalid.");
  const sector = text(row.sector, "Venture sector is missing.") as VentureSector;
  const stage = text(row.stage, "Venture stage is missing.") as VentureStage;
  const participationRole = text(row.participation_role, "Venture participation role is missing.") as VentureRole;
  const followOnStatus = text(row.follow_on_status, "Venture follow-on status is missing.") as VentureFollowOn;
  if (!sectors.has(sector) || !stages.has(stage) || !roles.has(participationRole) || !followOns.has(followOnStatus)) throw new Error("Venture relationship classification is invalid.");
  const partneredYear = row.first_partnered_year === null ? null : integer(row.first_partnered_year, "Venture partnered year is invalid.");
  if (partneredYear !== null && (partneredYear < 1900 || partneredYear > observedYear)) throw new Error("Venture partnered year is outside the released scope.");
  return {
    company_id: patterned(row.company_id, /^[a-z0-9-]+$/, "Venture company ID is invalid."),
    company_name: text(row.company_name, "Venture company name is missing."),
    sector,
    first_partnered_year: partneredYear,
    stage,
    participation_role: participationRole,
    follow_on_status: followOnStatus,
    source_url: patterned(row.source_url, officialSource, "Venture relationship source is invalid."),
    source_sha256: patterned(row.source_sha256, hash, "Venture relationship source hash is invalid.")
  };
}

function parseFirm(value: unknown, observedYear: number): VentureFirm {
  const firm = object(value, "Venture firm is invalid.");
  exactKeys(firm, ["firm_id", "name", "category", "strategy_labels", "source_url", "source_sha256", "tracked_relationship_count", "sector_counts", "relationships"], "Venture firm fields are invalid.");
  if (firm.category !== "core_technology_ai" || !Array.isArray(firm.strategy_labels) || !Array.isArray(firm.sector_counts) || !Array.isArray(firm.relationships)) throw new Error("Venture firm contract is invalid.");
  const relationships = firm.relationships.map((item) => parseRelationship(item, observedYear));
  const relationshipIds = new Set(relationships.map((row) => row.company_id));
  const trackedRelationshipCount = integer(firm.tracked_relationship_count, "Venture relationship count is invalid.");
  if (relationshipIds.size !== relationships.length || trackedRelationshipCount !== relationships.length) throw new Error("Venture relationship count or identity is invalid.");
  const firmSourceUrl = patterned(firm.source_url, officialSource, "Venture firm source is invalid.");
  const firmSourceHost = new URL(firmSourceUrl).hostname.replace(/^www\./, "");
  if (relationships.some((row) => new URL(row.source_url).hostname.replace(/^www\./, "") !== firmSourceHost)) throw new Error("Venture relationship source host does not match its firm.");
  const sectorCounts = firm.sector_counts.map((value) => {
    const row = object(value, "Venture sector count is invalid.");
    exactKeys(row, ["sector", "company_count"], "Venture sector count fields are invalid.");
    const sector = text(row.sector, "Venture sector count label is missing.") as VentureSector;
    if (!sectors.has(sector)) throw new Error("Venture sector count label is invalid.");
    return { sector, company_count: integer(row.company_count, "Venture sector count is invalid.") };
  });
  const expectedCounts = new Map<VentureSector, number>();
  relationships.forEach((row) => expectedCounts.set(row.sector, (expectedCounts.get(row.sector) ?? 0) + 1));
  if (sectorCounts.length !== expectedCounts.size || sectorCounts.some((row) => expectedCounts.get(row.sector) !== row.company_count)) throw new Error("Venture sector counts do not match released relationships.");
  return {
    firm_id: patterned(firm.firm_id, /^[a-z0-9-]+$/, "Venture firm ID is invalid."),
    name: text(firm.name, "Venture firm name is missing."),
    category: "core_technology_ai",
    strategy_labels: firm.strategy_labels.map((item) => text(item, "Venture strategy label is invalid.")),
    source_url: firmSourceUrl,
    source_sha256: patterned(firm.source_sha256, hash, "Venture firm source hash is invalid."),
    tracked_relationship_count: trackedRelationshipCount,
    sector_counts: sectorCounts,
    relationships
  };
}

export function parseVentureCatalog(value: unknown): VentureCatalog {
  const catalog = object(value, "Venture catalog is invalid.");
  exactKeys(catalog, ["schema_version", "release_id", "manifest_hash", "source_manifest_hash", "observed_at", "source_fresh_through", "scope", "methodology", "limitations", "firms"], "Venture catalog fields are invalid.");
  if (catalog.schema_version !== "vc-catalog.v1" || !Array.isArray(catalog.limitations) || !Array.isArray(catalog.firms)) throw new Error("Venture catalog contract is invalid.");
  const observedAt = text(catalog.observed_at, "Venture observed time is missing.");
  const observedYear = new Date(observedAt).getUTCFullYear();
  if (!Number.isInteger(observedYear)) throw new Error("Venture observed time is invalid.");
  const firms = catalog.firms.map((item) => parseFirm(item, observedYear));
  if (new Set(firms.map((firm) => firm.firm_id)).size !== firms.length) throw new Error("Venture firm IDs must be unique.");
  const companyDefinitions = new Map<string, string>();
  firms.flatMap((firm) => firm.relationships).forEach((row) => {
    const definition = `${row.company_name}\u0000${row.sector}`;
    if (companyDefinitions.has(row.company_id) && companyDefinitions.get(row.company_id) !== definition) throw new Error("Venture company definitions conflict across firms.");
    companyDefinitions.set(row.company_id, definition);
  });
  const parsed: VentureCatalog = {
    schema_version: "vc-catalog.v1",
    release_id: text(catalog.release_id, "Venture release ID is missing."),
    manifest_hash: patterned(catalog.manifest_hash, hash, "Venture manifest hash is invalid."),
    source_manifest_hash: patterned(catalog.source_manifest_hash, hash, "Venture source manifest hash is invalid."),
    observed_at: observedAt,
    source_fresh_through: text(catalog.source_fresh_through, "Venture source date is missing."),
    scope: text(catalog.scope, "Venture scope is missing."),
    methodology: text(catalog.methodology, "Venture methodology is missing."),
    limitations: catalog.limitations.map((item) => text(item, "Venture limitation is invalid.")),
    firms
  };
  const release = releaseFor("venture");
  if (release.status !== "available" || release.release_id !== parsed.release_id || release.manifest_hash !== parsed.manifest_hash || release.observed_at !== parsed.observed_at) throw new Error("Venture release binding is invalid.");
  return parsed;
}

export const ventureCatalog = parseVentureCatalog(rawCatalog);

export function ventureFirm(firmId: string): VentureFirm | null {
  return ventureCatalog.firms.find((firm) => firm.firm_id === firmId) ?? null;
}
