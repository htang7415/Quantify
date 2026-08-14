import { describe, expect, it } from "vitest";
import { parseTreasuryRatesCatalog, rate, ratesFreshness, treasuryRatesCatalog } from "./catalog";

describe("Treasury rates catalog contract", () => {
  it("loads exact curve observations and the deterministic spread", () => {
    expect(rate("2Y")).toBe(4.15);
    expect(rate("10Y")).toBe(4.63);
    expect(treasuryRatesCatalog.spreads[0]).toEqual({ name: "2s10s", value_pp: 0.48, derived_from: ["2Y", "10Y"] });
  });

  it("computes visible freshness from the release deadline", () => {
    expect(ratesFreshness(new Date("2026-08-14T00:00:00Z"))).toBe("current");
    expect(ratesFreshness(new Date("2026-08-17T00:00:00Z"))).toBe("stale");
  });

  it("rejects nonofficial source URLs", () => {
    expect(() => parseTreasuryRatesCatalog({ ...treasuryRatesCatalog, source_url: "https://example.com/rates" })).toThrow("source URL is invalid");
  });
});
