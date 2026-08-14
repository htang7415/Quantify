import { describe, expect, it } from "vitest";
import { etfFlowCatalog, etfFreshness } from "./catalog";

describe("ETF flow catalog", () => {
  it("binds exact SEC flows to the active release", () => {
    expect(etfFlowCatalog.funds.map((fund) => fund.ticker)).toEqual(["SPY", "QQQ", "VGT", "IWM", "SMH"]);
    expect(etfFlowCatalog.funds.find((fund) => fund.ticker === "SMH")?.three_month_net_flow_usd).toBe(1618731645.5);
    expect(etfFlowCatalog.funds.find((fund) => fund.ticker === "VGT")?.report_date).toBe("2026-02-28");
    expect(etfFlowCatalog.funds.find((fund) => fund.ticker === "VGT")?.months).toEqual(["2025-12", "2026-01", "2026-02"]);
  });
  it("reports freshness from the declared deadline", () => {
    expect(etfFreshness(new Date("2026-08-13T00:00:00Z"))).toBe("current");
    expect(etfFreshness(new Date("2026-11-01T00:00:00Z"))).toBe("stale");
  });
});
