export type RouteMetadata = {
  title: string;
  description: string;
  canonicalPath: string;
  indexable: boolean;
};

const defaultDescription =
  "Research released public-company information and verify claims against declared evidence with an inspectable audit trail.";

const exactRoutes: Record<string, Omit<RouteMetadata, "indexable">> = {
  "/": {
    title: "Quantify — Evidence-bound company research",
    description: defaultDescription,
    canonicalPath: "/"
  },
  "/product": {
    title: "Product — Quantify",
    description: "Move from released information to connected intelligence to deterministic claim verification without losing the evidence boundary.",
    canonicalPath: "/product"
  },
  "/coverage": {
    title: "Current coverage — Quantify",
    description: "Inspect the active released catalogs, observation dates, freshness states, limitations, and release identities available to Quantify.",
    canonicalPath: "/coverage"
  },
  "/methodology": {
    title: "Methodology — Quantify",
    description: "See how Quantify binds claims to released evidence and uses deterministic validation to compose every publication verdict.",
    canonicalPath: "/methodology"
  },
  "/agent": {
    title: "Verify a company claim — Quantify",
    description: "Check a bounded company-analysis claim against declared frozen evidence and inspect its verdict, scope, citations, and audit identity.",
    canonicalPath: "/agent"
  },
  "/verify": {
    title: "Verify a company claim — Quantify",
    description: "Check a bounded company-analysis claim against declared frozen evidence and inspect its verdict, scope, citations, and audit identity.",
    canonicalPath: "/agent"
  },
  "/markets": {
    title: "Markets research — Quantify",
    description: "Browse released macro, rates, ETF, and crypto reference data with visible scope, dates, and limitations.",
    canonicalPath: "/markets"
  },
  "/markets/macro": {
    title: "Macro research — Quantify",
    description: "Inspect released macroeconomic observations, calculations, dates, and source limitations.",
    canonicalPath: "/markets/macro"
  },
  "/markets/rates": {
    title: "Rates research — Quantify",
    description: "Inspect the independently released Treasury curve with exact observation dates and source scope.",
    canonicalPath: "/markets/rates"
  },
  "/markets/etfs": {
    title: "ETF research — Quantify",
    description: "Browse released ETF filings, fund flows, holdings, source dates, and limitations.",
    canonicalPath: "/markets/etfs"
  },
  "/markets/crypto": {
    title: "Crypto reference data — Quantify",
    description: "Inspect the released crypto reference layer and its explicit availability boundary.",
    canonicalPath: "/markets/crypto"
  },
  "/investors": {
    title: "Investor research — Quantify",
    description: "Explore released public filings and official-source investor relationships with source dates, scope, and limitations.",
    canonicalPath: "/investors"
  },
  "/investors/compare": {
    title: "Compare reported holdings — Quantify",
    description: "Compare exact released security identifiers across two reporting managers without implying portfolio similarity or suitability.",
    canonicalPath: "/investors/compare"
  },
  "/investors/venture": {
    title: "Venture relationships — Quantify",
    description: "Browse released official-source venture relationships without converting them into ownership or portfolio claims.",
    canonicalPath: "/investors/venture"
  },
  "/investors/venture/companies": {
    title: "Venture company relationships — Quantify",
    description: "Inspect exact company identifiers in the released venture relationship catalog.",
    canonicalPath: "/investors/venture/companies"
  },
  "/investors/venture/overlap": {
    title: "Venture relationship overlap — Quantify",
    description: "Inspect exact pair overlap in the released venture relationship catalog without a similarity score.",
    canonicalPath: "/investors/venture/overlap"
  },
  "/companies": {
    title: "Company research — Quantify",
    description: "Browse released public-company records and open evidence-bound research views.",
    canonicalPath: "/companies"
  },
  "/intelligence": {
    title: "Research intelligence — Quantify",
    description: "Inspect exact earnings, policy, ownership, and entity connections from compatible active releases.",
    canonicalPath: "/intelligence"
  },
  "/intelligence/earnings": {
    title: "Released earnings — Quantify",
    description: "Inspect exact released company earnings facts without estimates or market-direction claims.",
    canonicalPath: "/intelligence/earnings"
  },
  "/intelligence/policy": {
    title: "Released policy intelligence — Quantify",
    description: "Inspect typed policy actions, scope, effective dates, official sources, and released entity connections.",
    canonicalPath: "/intelligence/policy"
  },
  "/intelligence/releases": {
    title: "Release operations — Quantify",
    description: "Inspect the public release index, freshness states, limitations, and release identities.",
    canonicalPath: "/intelligence/releases"
  }
};

const dynamicRoutes: Array<{ pattern: RegExp; title: string; description: string }> = [
  { pattern: /^\/markets\/etfs\/[a-z0-9-]+$/, title: "ETF research — Quantify", description: exactRoutes["/markets/etfs"].description },
  { pattern: /^\/investors\/venture\/[a-z0-9-]+$/, title: "Venture firm research — Quantify", description: exactRoutes["/investors/venture"].description },
  { pattern: /^\/investors\/[a-z0-9-]+$/, title: "Investor research — Quantify", description: exactRoutes["/investors"].description },
  { pattern: /^\/companies\/[a-z0-9-]+$/, title: "Company research — Quantify", description: exactRoutes["/companies"].description }
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
    title: "Page not found — Quantify",
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
  upsertMeta("property", "og:site_name", "Quantify");
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
