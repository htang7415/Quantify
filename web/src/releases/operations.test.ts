import { describe, expect, it } from "vitest";
import { publicReleaseIndex } from "./catalog";
import { releaseCatalogLabel, releaseNeedsAttention, summarizeReleaseOperations } from "./operations";

describe("release operations projection", () => {
  it("derives exact public counts without operational assumptions", () => {
    const summary = summarizeReleaseOperations();
    expect(summary.total).toBe(publicReleaseIndex.releases.length);
    expect(summary.available + summary.unavailable).toBe(summary.total);
    expect(summary.current).toBe(4);
    expect(summary.attention).toBe(0);
  });

  it("marks only stale, revoked, and source-review entries for attention", () => {
    const release = publicReleaseIndex.releases.find((item) => item.catalog === "rates")!;
    expect(releaseNeedsAttention(release)).toBe(false);
    expect(releaseNeedsAttention({ ...release, freshness: "stale" })).toBe(true);
    expect(releaseNeedsAttention({ ...release, status: "source_review" })).toBe(true);
    expect(releaseNeedsAttention({ ...release, status: "revoked" })).toBe(true);
  });

  it("uses concise sentence-case catalog labels", () => {
    expect(releaseCatalogLabel("etf_holdings")).toBe("ETF holdings");
    expect(releaseCatalogLabel("crypto_exposure")).toBe("Crypto exposure");
  });
});

