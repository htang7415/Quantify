import { describe, expect, it } from "vitest";
import { parsePolicyEventCatalog, policyEventCatalog, policyEventsForTicker } from "./catalog";

describe("policy event catalog contract", () => {
  it("publishes three typed official actions and exact company connections", () => {
    expect(policyEventCatalog.events).toHaveLength(3);
    expect(policyEventCatalog.events.find((event) => event.details.kind === "fomc_decision")?.effective_at).toBe("2026-07-30");
    expect(policyEventsForTicker("NVDA")).toHaveLength(1);
    expect(policyEventsForTicker("META")).toHaveLength(0);
  });

  it("rejects coercible rates and nonofficial sources", () => {
    expect(() => parsePolicyEventCatalog({ ...policyEventCatalog, events: policyEventCatalog.events.map((event) => event.details.kind === "fomc_decision" ? { ...event, details: { ...event.details, target_range_low_pct: "3.5" } } : event) })).toThrow("target range is invalid");
    expect(() => parsePolicyEventCatalog({ ...policyEventCatalog, events: policyEventCatalog.events.map((event, index) => index === 0 ? { ...event, source_url: "https://example.com/policy" } : event) })).toThrow("source URL is invalid");
  });
});
