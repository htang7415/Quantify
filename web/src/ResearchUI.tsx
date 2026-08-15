import { useId, type ReactNode } from "react";

type NavigationGroup = "research" | "intelligence" | "markets";

type NavigationItem = {
  id: string;
  label: string;
  href: string;
};

const navigation: Record<NavigationGroup, NavigationItem[]> = {
  research: [
    { id: "companies", label: "Companies", href: "/companies" },
    { id: "markets", label: "Markets", href: "/markets" },
    { id: "investors", label: "Investors", href: "/investors" }
  ],
  intelligence: [
    { id: "overview", label: "Overview", href: "/intelligence" },
    { id: "earnings", label: "Earnings", href: "/intelligence/earnings" },
    { id: "policy", label: "Policy", href: "/intelligence/policy" },
    { id: "releases", label: "Releases", href: "/intelligence/releases" }
  ],
  markets: [
    { id: "overview", label: "Overview", href: "/markets" },
    { id: "macro", label: "Macro", href: "/markets/macro" },
    { id: "rates", label: "Rates", href: "/markets/rates" },
    { id: "etfs", label: "ETFs", href: "/markets/etfs" },
    { id: "crypto", label: "Crypto", href: "/markets/crypto" }
  ]
};

const navigationLabels: Record<NavigationGroup, string> = {
  research: "Research sections",
  intelligence: "Intelligence sections",
  markets: "Market sections"
};

export function ResearchSubnav({ group, active }: { group: NavigationGroup; active: string }) {
  return (
    <nav className={`research-subnav research-subnav-${group}`} aria-label={navigationLabels[group]}>
      <div className="page-shell">
        {navigation[group].map((item) => (
          <a
            aria-current={active === item.id ? "page" : undefined}
            className={active === item.id ? "active" : ""}
            href={item.href}
            key={item.id}
          >
            {item.label}
          </a>
        ))}
      </div>
    </nav>
  );
}

export type ScopeItem = string | { label: string; available?: boolean };

export function ScopeBar({ items, label = "Research scope" }: { items: ScopeItem[]; label?: string }) {
  return (
    <div className="research-scope" aria-label={label}>
      {items.map((item) => {
        const value = typeof item === "string" ? { label: item } : item;
        return <span className={value.available === false ? "is-unavailable" : ""} key={value.label}>{value.available !== undefined && <i aria-hidden="true" />}{value.label}</span>;
      })}
    </div>
  );
}

export function ResearchHero({
  eyebrow,
  title,
  description,
  scope,
  scopeLabel,
  aside,
  className = ""
}: {
  eyebrow: string;
  title: ReactNode;
  description: ReactNode;
  scope: ScopeItem[];
  scopeLabel?: string;
  aside?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`research-hero data-hero page-shell ${aside ? "has-aside" : ""} ${className}`.trim()}>
      <div className="research-hero-copy">
        <p className="terminal-eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
        <ScopeBar items={scope} label={scopeLabel} />
      </div>
      {aside}
    </section>
  );
}

export function DataCard({
  label,
  title,
  primary,
  meta,
  state,
  href
}: {
  label: string;
  title: string;
  primary: string;
  meta: string;
  state: string;
  href?: string;
}) {
  return (
    <article className={`research-data-card ${href ? "is-available" : "is-unavailable"}`}>
      <header><span>{label}</span><b>{state}</b></header>
      <strong>{primary}</strong>
      <h3>{title}</h3>
      <p>{meta}</p>
      {href ? <a href={href}>Open research →</a> : <span className="research-card-unavailable">Unavailable</span>}
    </article>
  );
}

export function SourceDetails({ title, children, className = "" }: { title: string; children: ReactNode; className?: string }) {
  return (
    <details className={`source-details ${className}`.trim()}>
      <summary>{title}</summary>
      <div>{children}</div>
    </details>
  );
}

export type ResearchFooterDetail = {
  label: string;
  value: ReactNode;
};

export function ResearchFooter({
  source,
  observed,
  status,
  details = [],
  methodology,
  limitations = [],
  links,
  disclaimer = "Research data only. No price predictions, trade recommendations, or personalized investment advice."
}: {
  source: ReactNode;
  observed: ReactNode;
  status: ReactNode;
  details?: ResearchFooterDetail[];
  methodology?: ReactNode;
  limitations?: ReactNode[];
  links?: ReactNode;
  disclaimer?: ReactNode;
}) {
  return (
    <footer className="research-footer">
      <div className="research-footer-shell page-shell">
        <div className="research-footer-summary" aria-label="Research release summary">
          <div><span>Source</span><strong>{source}</strong></div>
          <div><span>Observed</span><strong>{observed}</strong></div>
          <div><span>State</span><strong>{status}</strong></div>
        </div>
        <SourceDetails className="research-footer-details" title="Sources & limits">
          {details.length > 0 && <dl>{details.map((detail) => <div key={detail.label}><dt>{detail.label}</dt><dd>{detail.value}</dd></div>)}</dl>}
          {methodology && <div className="research-footer-method"><strong>Methodology</strong><p>{methodology}</p></div>}
          {limitations.length > 0 && <div className="research-footer-limitations"><strong>Limitations</strong><ul>{limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul></div>}
          {links && <div className="research-footer-links">{links}</div>}
          <p className="research-footer-disclaimer">{disclaimer}</p>
        </SourceDetails>
      </div>
    </footer>
  );
}

export function TableScroll({
  label,
  children,
  className = "",
  stickyColumn = 1
}: {
  label: string;
  children: ReactNode;
  className?: string;
  stickyColumn?: 1 | 2 | false;
}) {
  const instructionId = useId();
  return (
    <div
      aria-describedby={instructionId}
      aria-label={label}
      className={`table-scroll-region ${stickyColumn ? `sticky-column-${stickyColumn}` : ""} ${className}`.trim()}
      role="region"
      tabIndex={0}
    >
      <span className="visually-hidden" id={instructionId}>Scroll horizontally to inspect every column.</span>
      {children}
      <span aria-hidden="true" className="table-scroll-cue">Scroll →</span>
    </div>
  );
}

export function UnavailableState({
  eyebrow,
  title,
  reason,
  action
}: {
  eyebrow: string;
  title: string;
  reason: string;
  action: { label: string; href: string };
}) {
  return (
    <section className="unavailable-state page-shell">
      <p className="terminal-eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <p>{reason}</p>
      <a className="button button-dark" href={action.href}>{action.label}</a>
    </section>
  );
}
