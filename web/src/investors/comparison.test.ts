import { describe, expect, it } from "vitest";
import { investorCatalog } from "./catalog";
import { compareInvestors } from "./comparison";

describe("investor comparison", () => {
  const altimeter = investorCatalog.managers.find((manager) => manager.slug === "altimeter-capital")!;
  const pershing = investorCatalog.managers.find((manager) => manager.slug === "pershing-square")!;

  it("joins only exact released security IDs", () => {
    const comparison = compareInvestors(altimeter, pershing);
    const shared = comparison.rows.filter((row) => row.shared);
    expect(shared.length).toBe(comparison.sharedPositions);
    expect(shared.map((row) => row.ticker)).toEqual(["META", "AMZN", "UBER", "MSFT"]);
    expect(shared.every((row) => row.left?.security_id === row.right?.security_id)).toBe(true);
  });

  it("keeps each manager's disclosed values and share changes separate", () => {
    const comparison = compareInvestors(altimeter, pershing);
    const amazon = comparison.rows.find((row) => row.ticker === "AMZN")!;
    expect(amazon.left?.value_usd).toBeGreaterThan(0);
    expect(amazon.right?.value_usd).toBeGreaterThan(0);
    expect(amazon.weightGapPp).toBeCloseTo(amazon.left!.weight_pct - amazon.right!.weight_pct, 8);
  });

  it("rejects the same manager or a source-review manager", () => {
    const review = investorCatalog.managers.find((manager) => manager.status === "source_review")!;
    expect(() => compareInvestors(altimeter, altimeter)).toThrow(/different reporting managers/);
    expect(() => compareInvestors(altimeter, review)).toThrow(/two available reporting managers/);
  });
});
