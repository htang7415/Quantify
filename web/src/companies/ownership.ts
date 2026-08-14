import type { InvestorCatalog, InvestorManager, Holding } from "../investors/types";

export type CompanyPosition = {
  manager: InvestorManager;
  holding: Holding;
};

export type CompanyOwnership = {
  slug: string;
  ticker: string;
  issuer: string;
  themes: string[];
  tracked_disclosed_value_usd: number;
  reporting_manager_count: number;
  reported_position_count: number;
  positions: CompanyPosition[];
};

export function tickerSlug(ticker: string): string {
  return ticker.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export function buildCompanyOwnership(catalog: InvestorCatalog): CompanyOwnership[] {
  const rows = new Map<string, CompanyPosition[]>();

  for (const manager of catalog.managers) {
    if (manager.status !== "available") continue;
    for (const holding of manager.holdings) {
      if (!holding.ticker) continue;
      const bucket = rows.get(holding.ticker) ?? [];
      bucket.push({ manager, holding });
      rows.set(holding.ticker, bucket);
    }
  }

  const companies = [...rows.entries()].map(([ticker, positions]) => {
    const issuers = positions.map(({ holding }) => holding.issuer);
    const issuer = [...new Set(issuers)].sort((left, right) =>
      issuers.filter((value) => value === right).length - issuers.filter((value) => value === left).length
    )[0];
    const themes = [...new Set(positions.map(({ holding }) => holding.theme).filter((theme): theme is string => Boolean(theme)))].sort();
    return {
      slug: tickerSlug(ticker),
      ticker,
      issuer,
      themes,
      tracked_disclosed_value_usd: positions.reduce((total, { holding }) => total + holding.value_usd, 0),
      reporting_manager_count: new Set(positions.map(({ manager }) => manager.slug)).size,
      reported_position_count: positions.length,
      positions: [...positions].sort((left, right) => right.holding.value_usd - left.holding.value_usd)
    };
  });

  const slugs = new Set<string>();
  for (const company of companies) {
    if (!company.slug || slugs.has(company.slug)) {
      throw new Error(`Company ownership contains an ambiguous ticker slug: ${company.ticker}`);
    }
    slugs.add(company.slug);
  }

  return companies.sort((left, right) => right.tracked_disclosed_value_usd - left.tracked_disclosed_value_usd);
}
