export type RouteMetadata = {
  title: string;
  description: string;
  canonicalPath: string;
  indexable: boolean;
};

const defaultDescription =
  "Explore released investment data and intelligence, inspect evidence-bound analysis, and verify claims with a declared scope and audit trail.";

const exactRoutes: Record<string, Omit<RouteMetadata, "indexable">> = {
  "/": {
    title: "Libration — Evidence-bound AI investment research",
    description: "Explore released company, ownership, earnings, macro, rates, and policy data; connect typed intelligence; and verify claims against declared evidence.",
    canonicalPath: "/"
  },
  "/product": {
    title: "Product — Libration",
    description: "See how Libration separates released data, typed intelligence, cited analysis, and deterministic claim verification in one research system.",
    canonicalPath: "/product"
  },
  "/coverage": {
    title: "Current coverage — Libration",
    description: "Inspect the active released catalogs, observation dates, freshness states, limitations, and release identities available to Libration.",
    canonicalPath: "/coverage"
  },
  "/methodology": {
    title: "Methodology — Libration",
    description: "See how Libration binds claims to released evidence and uses deterministic validation to compose every publication verdict.",
    canonicalPath: "/methodology"
  },
  "/agent": {
    title: "Libration Agent — Verify a company claim",
    description: "Configure a bounded company-analysis task and inspect its released evidence, deterministic verdict, scope, limitations, and audit identity.",
    canonicalPath: "/agent"
  },
  "/verify": {
    title: "Libration Agent — Verify a company claim",
    description: "Configure a bounded company-analysis task and inspect its released evidence, deterministic verdict, scope, limitations, and audit identity.",
    canonicalPath: "/agent"
  },
  "/markets": {
    title: "Markets research — Libration",
    description: "Browse released macro, rates, ETF, and crypto reference data with visible scope, dates, and limitations.",
    canonicalPath: "/markets"
  },
  "/markets/macro": {
    title: "Macro research — Libration",
    description: "Inspect released macroeconomic observations, calculations, dates, and source limitations.",
    canonicalPath: "/markets/macro"
  },
  "/markets/rates": {
    title: "Rates research — Libration",
    description: "Inspect the independently released Treasury curve with exact observation dates and source scope.",
    canonicalPath: "/markets/rates"
  },
  "/markets/etfs": {
    title: "ETF research — Libration",
    description: "Browse released ETF filings, fund flows, holdings, source dates, and limitations.",
    canonicalPath: "/markets/etfs"
  },
  "/markets/crypto": {
    title: "Crypto reference data — Libration",
    description: "Inspect the released crypto reference layer and its explicit availability boundary.",
    canonicalPath: "/markets/crypto"
  },
  "/investors": {
    title: "Investor research — Libration",
    description: "Explore released public filings and official-source investor relationships with source dates, scope, and limitations.",
    canonicalPath: "/investors"
  },
  "/investors/compare": {
    title: "Compare reported holdings — Libration",
    description: "Compare exact released security identifiers across two reporting managers without implying portfolio similarity or suitability.",
    canonicalPath: "/investors/compare"
  },
  "/investors/venture": {
    title: "Venture relationships — Libration",
    description: "Browse released official-source venture relationships without converting them into ownership or portfolio claims.",
    canonicalPath: "/investors/venture"
  },
  "/investors/venture/companies": {
    title: "Venture company relationships — Libration",
    description: "Inspect exact company identifiers in the released venture relationship catalog.",
    canonicalPath: "/investors/venture/companies"
  },
  "/investors/venture/overlap": {
    title: "Venture relationship overlap — Libration",
    description: "Inspect exact pair overlap in the released venture relationship catalog without a similarity score.",
    canonicalPath: "/investors/venture/overlap"
  },
  "/companies": {
    title: "Company research — Libration",
    description: "Browse released public-company records and open evidence-bound research views.",
    canonicalPath: "/companies"
  },
  "/intelligence": {
    title: "Research intelligence — Libration",
    description: "Inspect exact earnings, policy, ownership, and entity connections from compatible active releases.",
    canonicalPath: "/intelligence"
  },
  "/intelligence/earnings": {
    title: "Released earnings — Libration",
    description: "Inspect exact released company earnings facts without estimates or market-direction claims.",
    canonicalPath: "/intelligence/earnings"
  },
  "/intelligence/policy": {
    title: "Released policy intelligence — Libration",
    description: "Inspect typed policy actions, scope, effective dates, official sources, and released entity connections.",
    canonicalPath: "/intelligence/policy"
  },
  "/intelligence/releases": {
    title: "Release operations — Libration",
    description: "Inspect the public release index, freshness states, limitations, and release identities.",
    canonicalPath: "/intelligence/releases"
  }
};

const dynamicRoutes: Array<{ pattern: RegExp; title: string; description: string }> = [
  { pattern: /^\/markets\/etfs\/[a-z0-9-]+$/, title: "ETF research — Libration", description: exactRoutes["/markets/etfs"].description },
  { pattern: /^\/investors\/venture\/[a-z0-9-]+$/, title: "Venture firm research — Libration", description: exactRoutes["/investors/venture"].description },
  { pattern: /^\/investors\/[a-z0-9-]+$/, title: "Investor research — Libration", description: exactRoutes["/investors"].description },
  { pattern: /^\/companies\/[a-z0-9-]+$/, title: "Company research — Libration", description: exactRoutes["/companies"].description }
];

function normalizePath(rawPath: string): string {
  const path = rawPath.split(/[?#]/, 1)[0].replace(/\/+$/, "");
  return path || "/";
}

export function metadataForPath(rawPath: string): RouteMetadata {
  const path = normalizePath(rawPath);
  const exact = exactRoutes[path];
  if (exact) return { ...exact, indexable: true };

  const dynamic = dynamicRoutes.find(({ pattern }) => pattern.test(path));
  if (dynamic) {
    return {
      title: dynamic.title,
      description: dynamic.description,
      canonicalPath: path,
      indexable: true
    };
  }

  return {
    title: "Page not found — Libration",
    description: defaultDescription,
    canonicalPath: path,
    indexable: false
  };
}

function upsertMeta(attribute: "name" | "property", key: string, content: string) {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[${attribute}="${key}"]`);
  if (!element) {
    element = document.createElement("meta");
    element.setAttribute(attribute, key);
    document.head.append(element);
  }
  element.content = content;
}

function canonicalOrigin(): string {
  const configured = import.meta.env.VITE_QUANTIFY_PUBLIC_ORIGIN?.trim();
  if (configured) {
    try {
      return new URL(configured).origin;
    } catch {
      // Invalid public configuration must not replace the current safe origin.
    }
  }
  return window.location.origin;
}

export function applyRouteMetadata(rawPath: string): RouteMetadata {
  const metadata = metadataForPath(rawPath);
  const canonicalUrl = new URL(metadata.canonicalPath, `${canonicalOrigin()}/`).toString();

  document.title = metadata.title;
  upsertMeta("name", "description", metadata.description);
  upsertMeta("name", "robots", "noindex,nofollow");
  upsertMeta("property", "og:type", "website");
  upsertMeta("property", "og:site_name", "Libration");
  upsertMeta("property", "og:title", metadata.title);
  upsertMeta("property", "og:description", metadata.description);
  upsertMeta("property", "og:url", canonicalUrl);
  upsertMeta("name", "twitter:card", "summary");
  upsertMeta("name", "twitter:title", metadata.title);
  upsertMeta("name", "twitter:description", metadata.description);

  let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!canonical) {
    canonical = document.createElement("link");
    canonical.rel = "canonical";
    document.head.append(canonical);
  }
  canonical.href = canonicalUrl;
  return metadata;
}
