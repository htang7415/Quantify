import { describe, expect, it } from "vitest";
import { blsMacroCatalog, macroFreshness, macroMetric, parseBlsMacroCatalog } from "./catalog";

describe("BLS macro catalog contract", () => {
  it("publishes bounded official observations and deterministic CPI rates", () => {
    expect(blsMacroCatalog.observed_period).toBe("2026-07");
    expect(macroMetric("headline_cpi_yoy").value_pct).toBe(3.4);
    expect(macroMetric("core_cpi_yoy").value_pct).toBe(2.5);
    expect(macroMetric("unemployment_rate").value_pct).toBe(4.1);
  });

  it("computes release freshness at render time", () => {
    expect(macroFreshness(new Date("2026-08-13T00:00:00Z"))).toBe("current");
    expect(macroFreshness(new Date("2026-09-15T00:00:00Z"))).toBe("stale");
  });

  it("rejects coercible strings and nonofficial source hosts", () => {
    expect(() => parseBlsMacroCatalog({ ...blsMacroCatalog, observations: blsMacroCatalog.observations.map((item) => ({ ...item, value_pct: "3.4" })) })).toThrow("value is invalid");
    expect(() => parseBlsMacroCatalog({ ...blsMacroCatalog, observations: blsMacroCatalog.observations.map((item, index) => ({ ...item, source_url: index === 0 ? "https://example.com/cpi" : item.source_url })) })).toThrow("official API host");
  });
});
