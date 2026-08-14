import { GlobalSearch } from "./search/GlobalSearch";

type NavAction =
  | { label: string; href: string; onClick?: never }
  | { label: string; onClick: () => void; href?: never };

export type NavSection = "overview" | "markets" | "investors" | "companies" | "intelligence" | "agent";

type CommercialSection = "product" | "research" | "intelligence" | "coverage" | "methodology";

const links: Array<{ section: CommercialSection; label: string; href: string }> = [
  { section: "research", label: "Research", href: "/" },
  { section: "product", label: "Product", href: "/product" },
  { section: "intelligence", label: "Intelligence", href: "/intelligence" },
  { section: "coverage", label: "Coverage", href: "/coverage" },
  { section: "methodology", label: "Methodology", href: "/methodology" }
];

export type SiteNavSection = NavSection | "product" | "coverage" | "methodology";

function commercialSection(active: SiteNavSection): CommercialSection | null {
  if (active === "product" || active === "coverage" || active === "methodology" || active === "intelligence") return active;
  if (["overview", "markets", "investors", "companies"].includes(active)) return "research";
  return null;
}

export function SiteNav({ active, action }: { active: SiteNavSection; action: NavAction }) {
  const selected = commercialSection(active);
  return (
    <>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <nav className="site-nav" aria-label="Primary navigation">
        <a className="site-brand" href="/" aria-label="Quantify home">
          <span className="site-brand-mark">Q</span>
          <span>Quantify</span>
        </a>
        <div className="site-nav-links">
          {links.map((link) => (
            <a
              aria-current={selected === link.section ? "page" : undefined}
              className={selected === link.section ? "active" : ""}
              href={link.href}
              key={link.section}
            >
              {link.label}
            </a>
          ))}
        </div>
        <div className="site-nav-tools">
          <GlobalSearch />
          {action.href ? (
            <a className="site-nav-action" href={action.href}>{action.label}</a>
          ) : (
            <button className="site-nav-action" type="button" onClick={action.onClick}>{action.label}</button>
          )}
        </div>
      </nav>
      <span className="skip-target" id="main-content" tabIndex={-1} />
    </>
  );
}
