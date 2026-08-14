import rawIndex from "../data/publicReleaseIndex.json";
import type { PublicCatalog, PublicRelease, PublicReleaseIndex, ReleaseFreshness, ReleaseStatus } from "./types";

const catalogs = new Set<PublicCatalog>(["investors", "markets", "macro", "rates", "etf_flows", "etf_holdings", "crypto", "crypto_exposure", "earnings", "policy", "events"]);
const statuses = new Set<ReleaseStatus>(["available", "unavailable", "source_review", "revoked"]);
const freshnessStates = new Set<ReleaseFreshness>(["current", "stale", "not_applicable", "unknown"]);

function record(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(message);
  return value as Record<string, unknown>;
}

function stringValue(value: unknown, message: string): string {
  if (typeof value !== "string" || !value) throw new Error(message);
  return value;
}

function nullableString(value: unknown, message: string): string | null {
  return value === null ? null : stringValue(value, message);
}

export function parsePublicReleaseIndex(value: unknown): PublicReleaseIndex {
  const index = record(value, "Public release index is invalid.");
  if (index.schema_version !== "public-release-index.v2") throw new Error("Public release index schema is unsupported.");
  if (!Array.isArray(index.releases)) throw new Error("Public release index entries are invalid.");
  const releases = index.releases.map((item): PublicRelease => {
    const row = record(item, "Public release entry is invalid.");
    const catalog = stringValue(row.catalog, "Public release catalog is missing.") as PublicCatalog;
    const status = stringValue(row.status, "Public release status is missing.") as ReleaseStatus;
    const freshness = stringValue(row.freshness, "Public release freshness is missing.") as ReleaseFreshness;
    if (!catalogs.has(catalog) || !statuses.has(status) || !freshnessStates.has(freshness)) throw new Error("Public release entry contains an unsupported value.");
    if (!Array.isArray(row.limitations) || row.limitations.length === 0) throw new Error("Public release limitations are required.");
    const release_id = nullableString(row.release_id, "Public release ID is invalid.");
    const manifest_hash = nullableString(row.manifest_hash, "Public release manifest hash is invalid.");
    const observed_at = nullableString(row.observed_at, "Public release observation time is invalid.");
    if (manifest_hash !== null && !/^[a-f0-9]{64}$/.test(manifest_hash)) throw new Error("Public release manifest hash is invalid.");
    if (status === "available" && (!release_id || !manifest_hash || !observed_at)) throw new Error("Available public releases require identity and observation time.");
    return {
      catalog,
      status,
      release_id,
      manifest_hash,
      observed_at,
      freshness,
      limitations: row.limitations.map((limitation) => stringValue(limitation, "Public release limitation is invalid."))
    };
  });
  if (new Set(releases.map((release) => release.catalog)).size !== releases.length) throw new Error("Public release catalogs must be unique.");
  return {
    schema_version: "public-release-index.v2",
    generated_at: stringValue(index.generated_at, "Public release index generation time is missing."),
    releases
  };
}

export const publicReleaseIndex = parsePublicReleaseIndex(rawIndex);

export function releaseFor(catalog: PublicCatalog): PublicRelease {
  const release = publicReleaseIndex.releases.find((item) => item.catalog === catalog);
  if (!release) throw new Error(`Public release index does not declare ${catalog}.`);
  return release;
}
