import { describe, expect, it } from "vitest";
import { earningsCatalog, earningsForTicker, parseEarningsCatalog } from "./catalog";

describe("earnings catalog contract", () => {
  it("publishes exact comparable AAPL and MSFT facts", () => {
    expect(earningsForTicker("AAPL")?.revenue.value).toBe(111_184_000_000);
    expect(earningsForTicker("AAPL")?.diluted_eps.yoy_change_pct).toBe(21.8);
    expect(earningsForTicker("MSFT")?.revenue.yoy_change_pct).toBe(18.3);
    expect(earningsForTicker("NVDA")).toBeNull();
  });

  it("rejects coercible metric strings and non-SEC sources", () => {
    expect(() => parseEarningsCatalog({ ...earningsCatalog, companies: earningsCatalog.companies.map((company) => ({ ...company, revenue: { ...company.revenue, value: "111184000000" } })) })).toThrow("value is invalid");
    expect(() => parseEarningsCatalog({ ...earningsCatalog, companies: earningsCatalog.companies.map((company, index) => ({ ...company, filing_url: index === 0 ? "https://example.com/filing" : company.filing_url })) })).toThrow("filing URL is invalid");
  });
});
