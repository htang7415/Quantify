export type PublicCatalog = "investors" | "markets" | "macro" | "rates" | "etf_flows" | "crypto" | "crypto_exposure" | "earnings" | "policy" | "events";
export type ReleaseStatus = "available" | "unavailable" | "source_review" | "revoked";
export type ReleaseFreshness = "current" | "stale" | "not_applicable" | "unknown";

export type PublicRelease = {
  catalog: PublicCatalog;
  status: ReleaseStatus;
  release_id: string | null;
  manifest_hash: string | null;
  observed_at: string | null;
  freshness: ReleaseFreshness;
  limitations: string[];
};

export type PublicReleaseIndex = {
  schema_version: "public-release-index.v1";
  generated_at: string;
  releases: PublicRelease[];
};
