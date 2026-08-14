import { describe, expect, it } from "vitest";
import rawCatalog from "../data/vcCatalog.json";
import { parseVentureCatalog, ventureCatalog, ventureFirm } from "./catalog";

describe("venture catalog", () => {
  it("binds a bounded four-firm release to exact official-source relationships", () => {
    expect(ventureCatalog.firms).toHaveLength(4);
    expect(ventureCatalog.firms.reduce((sum, firm) => sum + firm.tracked_relationship_count, 0)).toBe(24);
    expect(ventureFirm("khosla-ventures")?.relationships.find((row) => row.company_id === "openai")?.first_partnered_year).toBe(2019);
    expect(ventureCatalog.firms.flatMap((firm) => firm.relationships).every((row) => /^https:\/\//.test(row.source_url))).toBe(true);
  });

  it("fails closed on added precision fields", () => {
    const invalid = structuredClone(rawCatalog) as unknown as { firms: Array<{ relationships: Array<Record<string, unknown>> }> };
    invalid.firms[0].relationships[0].ownership_pct = 4.2;
    expect(() => parseVentureCatalog(invalid)).toThrow(/fields are invalid/i);
  });

  it("fails closed when compiled sector counts do not match the relationships", () => {
    const invalid = structuredClone(rawCatalog) as unknown as { firms: Array<{ sector_counts: Array<{ company_count: number }> }> };
    invalid.firms[0].sector_counts[0].company_count += 1;
    expect(() => parseVentureCatalog(invalid)).toThrow(/sector counts/i);
  });
});
