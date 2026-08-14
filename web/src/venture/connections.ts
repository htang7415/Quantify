import type { VentureCatalog, VentureFirm, VentureRelationship, VentureSector } from "./types";

export type VentureCompanyConnection = {
  companyId: string;
  companyName: string;
  sector: VentureSector;
  relationships: Array<{ firm: VentureFirm; relationship: VentureRelationship }>;
};

export type VentureOverlap = {
  left: VentureFirm;
  right: VentureFirm;
  sharedCompanyIds: string[];
  sharedCompanies: VentureCompanyConnection[];
};

export function buildVentureCompanies(catalog: VentureCatalog): VentureCompanyConnection[] {
  const companies = new Map<string, VentureCompanyConnection>();
  for (const firm of catalog.firms) {
    for (const relationship of firm.relationships) {
      const existing = companies.get(relationship.company_id);
      if (existing && (existing.companyName !== relationship.company_name || existing.sector !== relationship.sector)) {
        throw new Error(`Venture company identity conflicts: ${relationship.company_id}`);
      }
      const company = existing ?? {
        companyId: relationship.company_id,
        companyName: relationship.company_name,
        sector: relationship.sector,
        relationships: []
      };
      company.relationships.push({ firm, relationship });
      companies.set(relationship.company_id, company);
    }
  }
  return [...companies.values()]
    .map((company) => ({ ...company, relationships: [...company.relationships].sort((left, right) => left.firm.name.localeCompare(right.firm.name)) }))
    .sort((left, right) => right.relationships.length - left.relationships.length || left.companyName.localeCompare(right.companyName));
}

export function buildVentureOverlaps(catalog: VentureCatalog): VentureOverlap[] {
  const companies = buildVentureCompanies(catalog);
  const byFirm = new Map(catalog.firms.map((firm) => [firm.firm_id, new Set(firm.relationships.map((row) => row.company_id))]));
  const overlaps: VentureOverlap[] = [];
  catalog.firms.forEach((left, leftIndex) => {
    catalog.firms.slice(leftIndex + 1).forEach((right) => {
      const rightIds = byFirm.get(right.firm_id) ?? new Set<string>();
      const sharedCompanyIds = [...(byFirm.get(left.firm_id) ?? new Set<string>())].filter((id) => rightIds.has(id)).sort();
      overlaps.push({
        left,
        right,
        sharedCompanyIds,
        sharedCompanies: sharedCompanyIds.map((id) => companies.find((company) => company.companyId === id)).filter((company): company is VentureCompanyConnection => Boolean(company))
      });
    });
  });
  return overlaps.sort((left, right) => right.sharedCompanyIds.length - left.sharedCompanyIds.length || left.left.name.localeCompare(right.left.name) || left.right.name.localeCompare(right.right.name));
}

export function overlapFor(overlaps: VentureOverlap[], leftId: string, rightId: string): VentureOverlap | null {
  return overlaps.find((row) =>
    (row.left.firm_id === leftId && row.right.firm_id === rightId)
    || (row.left.firm_id === rightId && row.right.firm_id === leftId)
  ) ?? null;
}
