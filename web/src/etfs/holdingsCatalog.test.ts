import { describe, expect, it } from "vitest";
import { etfExposuresForTicker, etfHoldingsCatalog, etfHoldingsFund } from "./holdingsCatalog";

describe("ETF holdings catalog", () => {
  it("binds the reviewed top-ten rows to the active release", () => {
    expect(etfHoldingsCatalog.funds.map((fund) => fund.ticker)).toEqual(["QQQ", "SMH", "VGT"]);
    expect(etfHoldingsFund("vgt")?.holdings).toHaveLength(10);
    expect(etfHoldingsFund("vgt")?.holdings[0].ticker).toBe("NVDA");
    expect(etfHoldingsFund("vgt")?.top_ten_concentration_pct).toBeCloseTo(57.369031484468, 8);
  });

  it("connects companies only through exact reviewed ticker mappings", () => {
    expect(etfExposuresForTicker("NVDA").map(({ fund }) => fund.ticker)).toEqual(["SMH", "VGT", "QQQ"]);
    expect(etfExposuresForTicker("AMD")).toEqual([]);
  });
});
