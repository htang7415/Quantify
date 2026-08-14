import { publicReleaseIndex } from "./catalog";
import type { PublicCatalog, PublicRelease, PublicReleaseIndex } from "./types";

const catalogLabels: Record<PublicCatalog, string> = {
  investors: "Investors",
  venture: "Venture capital",
  markets: "Markets",
  macro: "Macro",
  rates: "Rates",
  etf_flows: "ETF flows",
  etf_holdings: "ETF holdings",
  crypto: "Crypto market",
  crypto_exposure: "Crypto exposure",
  earnings: "Earnings",
  policy: "Policy",
  events: "High-impact events"
};

export type ReleaseOperationsSummary = {
  total: number;
  available: number;
  unavailable: number;
  current: number;
  attention: number;
};

export function releaseCatalogLabel(catalog: PublicCatalog): string {
  return catalogLabels[catalog];
}

export function releaseNeedsAttention(release: PublicRelease): boolean {
  return release.status === "source_review" || release.status === "revoked" || release.freshness === "stale";
}

export function summarizeReleaseOperations(index: PublicReleaseIndex = publicReleaseIndex): ReleaseOperationsSummary {
  return {
    total: index.releases.length,
    available: index.releases.filter((release) => release.status === "available").length,
    unavailable: index.releases.filter((release) => release.status === "unavailable").length,
    current: index.releases.filter((release) => release.status === "available" && release.freshness === "current").length,
    attention: index.releases.filter(releaseNeedsAttention).length
  };
}
