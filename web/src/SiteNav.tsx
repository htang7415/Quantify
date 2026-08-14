type NavAction =
  | { label: string; href: string; onClick?: never }
  | { label: string; onClick: () => void; href?: never };

export type NavSection = "overview" | "markets" | "investors" | "companies" | "intelligence" | "agent";

const links: Array<{ section: Exclude<NavSection, "agent">; label: string; href: string }> = [
  { section: "overview", label: "Overview", href: "/" },
  { section: "markets", label: "Markets", href: "/markets" },
  { section: "investors", label: "Investors", href: "/investors" },
  { section: "companies", label: "Companies", href: "/companies" },
  { section: "intelligence", label: "Intelligence", href: "/intelligence" }
];

export function SiteNav({ active, action }: { active: NavSection; action: NavAction }) {
  return (
    <nav className="site-nav" aria-label="Primary navigation">
      <a className="site-brand" href="/" aria-label="Quantify home">
        <span className="site-brand-mark">Q</span>
        <span>Quantify</span>
      </a>
      <div className="site-nav-links">
        {links.map((link) => (
          <a className={active === link.section ? "active" : ""} href={link.href} key={link.section}>
            {link.label}
          </a>
        ))}
      </div>
      {action.href ? (
        <a className="site-nav-action" href={action.href}>{action.label}</a>
      ) : (
        <button className="site-nav-action" type="button" onClick={action.onClick}>{action.label}</button>
      )}
    </nav>
  );
}
