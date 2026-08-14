import { describe, expect, it } from "vitest";
import { investorCatalog } from "../investors/catalog";
import { buildCompanyOwnership, tickerSlug } from "./ownership";

describe("company ownership projection", () => {
  it("derives company pages only from available released manager rows", () => {
    const companies = buildCompanyOwnership(investorCatalog);
    const nvidia = companies.find((company) => company.ticker === "NVDA");

    expect(nvidia).toBeDefined();
    expect(nvidia?.positions.every(({ manager }) => manager.status === "available")).toBe(true);
    expect(nvidia?.tracked_disclosed_value_usd).toBe(
      nvidia?.positions.reduce((total, { holding }) => total + holding.value_usd, 0)
    );
    expect(nvidia?.reporting_manager_count).toBe(new Set(nvidia?.positions.map(({ manager }) => manager.slug)).size);
  });

  it("keeps the projection scoped instead of claiming total institutional ownership", () => {
    const companies = buildCompanyOwnership(investorCatalog);
    expect(companies.every((company) => company.tracked_disclosed_value_usd >= 0)).toBe(true);
    expect(companies.some((company) => company.reporting_manager_count > 1)).toBe(true);
  });

  it("normalizes punctuation in ticker routes", () => {
    expect(tickerSlug("BRK.B")).toBe("brk-b");
  });
});
