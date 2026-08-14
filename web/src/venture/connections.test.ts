import { describe, expect, it } from "vitest";
import { ventureCatalog } from "./catalog";
import { buildVentureCompanies, buildVentureOverlaps, overlapFor } from "./connections";

describe("venture released connections", () => {
  it("groups only exact released company IDs", () => {
    const companies = buildVentureCompanies(ventureCatalog);
    const openai = companies.find((company) => company.companyId === "openai");
    expect(openai?.relationships.map((row) => row.firm.firm_id)).toEqual(["andreessen-horowitz", "founders-fund", "khosla-ventures"]);
    expect(openai?.sector).toBe("ai");
  });

  it("computes symmetric pair overlap without a similarity score", () => {
    const overlaps = buildVentureOverlaps(ventureCatalog);
    const row = overlapFor(overlaps, "founders-fund", "khosla-ventures");
    expect(row?.sharedCompanyIds).toEqual(["openai", "stripe"]);
    expect(overlapFor(overlaps, "khosla-ventures", "founders-fund")).toEqual(row);
    expect(overlaps).toHaveLength(6);
  });
});
