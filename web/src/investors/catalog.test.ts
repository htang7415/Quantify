import { describe, expect, it } from "vitest";
import { investorCatalog, parseInvestorCatalog } from "./catalog";

describe("investor catalog contract", () => {
  it("loads one common frozen reporting period for the featured managers", () => {
    expect(investorCatalog.schema_version).toBe("investor-catalog.v1");
    expect(investorCatalog.report_period).toBe("2026-03-31");
    expect(investorCatalog.managers).toHaveLength(8);
    expect(new Set(investorCatalog.managers.map((manager) => manager.latest_filing.report_period))).toEqual(new Set(["2026-03-31"]));
  });

  it("rejects an unsupported catalog schema", () => {
    expect(() => parseInvestorCatalog({ ...investorCatalog, schema_version: "investor-catalog.v2" })).toThrow("unsupported");
  });

  it("keeps source-review managers empty instead of estimating values", () => {
    const manager = investorCatalog.managers.find((item) => item.slug === "duquesne-family-office");
    expect(manager?.status).toBe("source_review");
    expect(manager?.disclosed_portfolio_value_usd).toBeNull();
    expect(manager?.holdings).toEqual([]);
  });

  it("preserves deterministic weight and share-change semantics", () => {
    const manager = investorCatalog.managers.find((item) => item.slug === "altimeter-capital");
    const nvidia = manager?.holdings.find((holding) => holding.ticker === "NVDA");
    expect(nvidia?.weight_pct).toBeGreaterThan(0);
    expect(nvidia?.change).toBe("added");
    expect(nvidia?.share_delta_pct).not.toBeNull();
    expect(manager?.holdings.reduce((sum, holding) => sum + holding.weight_pct, 0)).toBeCloseTo(100, 1);
  });
});
