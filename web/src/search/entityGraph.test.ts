import { describe, expect, it } from "vitest";
import { searchEntityGraph, searchReleasedEntities } from "./entityGraph";

describe("released entity graph", () => {
  it("uses unique typed identities bound only to released sources", () => {
    expect(new Set(searchEntityGraph.map((entity) => entity.id)).size).toBe(searchEntityGraph.length);
    expect(searchEntityGraph.length).toBeGreaterThan(20);
    for (const entity of searchEntityGraph) {
      expect(entity.sources.length).toBeGreaterThan(0);
      expect(entity.sources.every((source) => source.releaseId && source.observedAt)).toBe(true);
    }
  });

  it("matches exact identifiers deterministically without narrative similarity", () => {
    expect(searchReleasedEntities("NVDA")[0]).toMatchObject({ id: "company:NVDA", kind: "Company", symbol: "NVDA" });
    expect(searchReleasedEntities("0001067983").some((entity) => entity.id === "investor:0001067983")).toBe(true);
    expect(searchReleasedEntities("VGT")[0]).toMatchObject({ kind: "ETF", symbol: "VGT" });
    expect(searchReleasedEntities("10Y")[0]).toMatchObject({ id: "rates:10Y", kind: "Rates" });
    expect(searchReleasedEntities("Founders Fund")[0]).toMatchObject({ id: "venture:founders-fund", kind: "Venture firm" });
    expect(searchReleasedEntities("an unrelated narrative idea")).toEqual([]);
  });

  it("retains exact contributing releases for connected company results", () => {
    const nvidia = searchReleasedEntities("NVDA")[0];
    expect(nvidia.sources.map((source) => source.catalog)).toEqual(["investors", "etf_holdings", "policy"]);
    expect(nvidia.description).toMatch(/connected releases/);
  });
});
