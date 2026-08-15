import { useMemo, useState } from "react";
import { ResearchFooter, ResearchSubnav, TableScroll } from "../ResearchUI";
import { SectionConnections } from "../SectionConnections";
import { SiteNav } from "../SiteNav";
import { readableDate, sentenceCase } from "../format";
import { ventureCatalog, ventureFirm } from "./catalog";
import { buildVentureCompanies, buildVentureOverlaps, overlapFor } from "./connections";
import type { VentureFirm } from "./types";

function VentureNav() {
  return <SiteNav active="investors" action={{ label: "Verify a claim", href: "/agent" }} subnav={<ResearchSubnav group="research" active="investors" />} />;
}

function UniverseTabs({ active }: { active: "public" | "venture" }) {
  return <nav className="investor-universe-tabs" aria-label="Investor universe">
    <a className={active === "public" ? "active" : ""} aria-current={active === "public" ? "page" : undefined} href="/investors">Public markets</a>
    <a className={active === "venture" ? "active" : ""} aria-current={active === "venture" ? "page" : undefined} href="/investors/venture">Venture capital</a>
  </nav>;
}

function VentureCard({ firm }: { firm: VentureFirm }) {
  const leadingSector = firm.sector_counts[0];
  const knownYears = firm.relationships.filter((row) => row.first_partnered_year !== null).length;
  return <a className="investor-card venture-card" href={`/investors/venture/${firm.firm_id}`}>
    <div className="investor-card-head"><div><p>{firm.name}</p><span>{firm.strategy_labels.join(" · ")}</span></div><strong>Venture firm</strong></div>
    <div className="card-metrics">
      <div><b>{firm.tracked_relationship_count}</b><span>Relationships</span></div>
      <div><b>{firm.sector_counts.length}</b><span>Sectors</span></div>
      <div><b>{knownYears}</b><span>Years disclosed</span></div>
    </div>
    <div className="card-holdings" aria-label={`${firm.name} tracked companies`}>{firm.relationships.slice(0, 5).map((row) => <span key={row.company_id}><b>{row.company_name}</b></span>)}</div>
    <div className="card-signal"><span>{leadingSector ? `${sentenceCase(leadingSector.sector)} · ${leadingSector.company_count}` : "No released sectors"}</span><span>Official sources ↗</span></div>
  </a>;
}

function VentureTools({ active }: { active: "firms" | "companies" | "overlap" }) {
  return <nav className="venture-tools category-tabs" aria-label="Venture research views">
    <a className={active === "firms" ? "active" : ""} aria-current={active === "firms" ? "page" : undefined} href="/investors/venture">Firms</a>
    <a className={active === "companies" ? "active" : ""} aria-current={active === "companies" ? "page" : undefined} href="/investors/venture/companies">Companies</a>
    <a className={active === "overlap" ? "active" : ""} aria-current={active === "overlap" ? "page" : undefined} href="/investors/venture/overlap">Overlap</a>
  </nav>;
}

function VentureFooter() {
  return <ResearchFooter
    details={[{ label: "Release ID", value: ventureCatalog.release_id }, { label: "Manifest", value: ventureCatalog.manifest_hash }, { label: "Source manifest", value: ventureCatalog.source_manifest_hash }]}
    limitations={ventureCatalog.limitations}
    methodology={ventureCatalog.methodology}
    observed={readableDate(ventureCatalog.observed_at.slice(0, 10))}
    source="Official venture-firm pages"
    status={`${ventureCatalog.firms.length} firms · Frozen review`}
  />;
}

export function VentureDashboard() {
  const [query, setQuery] = useState("");
  const firms = useMemo(() => ventureCatalog.firms.filter((firm) => {
    const index = [firm.name, ...firm.strategy_labels, ...firm.relationships.flatMap((row) => [row.company_name, row.sector])].join(" ").toLowerCase();
    return index.includes(query.trim().toLowerCase());
  }), [query]);
  const relationships = ventureCatalog.firms.reduce((sum, firm) => sum + firm.tracked_relationship_count, 0);
  const uniqueCompanies = new Set(ventureCatalog.firms.flatMap((firm) => firm.relationships.map((row) => row.company_id))).size;

  return <main className="investor-app venture-page">
    <VentureNav />
    <section className="terminal-hero venture-hero">
      <div><UniverseTabs active="venture" /><p className="terminal-eyebrow">Private markets · Official sources</p><h1>Follow the firms.<br /><span>Read the relationships.</span></h1><p>Firm-to-company relationships from frozen official pages. Unknown timing, stage, role, ownership, and value remain undisclosed.</p><div className="scope-pills" aria-label="Venture catalog access and scope"><span><i /> Official pages · Frozen</span><span>Public · No sign-in</span></div></div>
      <dl className="market-strip venture-snapshot" aria-label="Venture catalog snapshot">
        <div><dt>Tracked firms</dt><dd>{ventureCatalog.firms.length.toString().padStart(2, "0")}</dd></div>
        <div><dt>Relationships</dt><dd>{relationships}</dd></div>
        <div><dt>Unique companies</dt><dd>{uniqueCompanies}</dd></div>
        <div><dt>Source through</dt><dd>{readableDate(ventureCatalog.source_fresh_through)}</dd></div>
      </dl>
    </section>

    <SectionConnections items={[
      { label: "Companies", detail: "Open one company across tracked venture firms", href: "/investors/venture/companies" },
      { label: "Overlap", detail: "Compare exact released company IDs between firms", href: "/investors/venture/overlap" },
      { label: "Public markets", detail: "Return to disclosed 13F holdings and changes", href: "/investors" }
    ]} />

    <section className="investor-index venture-index" aria-labelledby="venture-index-title">
      <div className="index-toolbar"><div><p className="terminal-eyebrow">Bounded release</p><h2 id="venture-index-title">Tracked venture firms</h2></div><label className="terminal-search"><span>Search</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Firm, company, or sector" /></label></div>
      <VentureTools active="firms" />
      <p className="venture-scope">{ventureCatalog.scope}</p>
      <div className="investor-grid venture-grid">{firms.map((firm) => <VentureCard firm={firm} key={firm.firm_id} />)}</div>
      {firms.length === 0 && <p className="empty-filter">No released relationship matches this search.</p>}
    </section>
    <VentureFooter />
  </main>;
}

export function VentureCompaniesPage() {
  const companies = useMemo(() => buildVentureCompanies(ventureCatalog), []);
  const [query, setQuery] = useState("");
  const [sector, setSector] = useState("all");
  const sectors = [...new Set(companies.map((company) => company.sector))].sort();
  const visible = companies.filter((company) => {
    const index = [company.companyName, company.companyId, company.sector, ...company.relationships.map((row) => row.firm.name)].join(" ").toLowerCase();
    return index.includes(query.trim().toLowerCase()) && (sector === "all" || company.sector === sector);
  });
  const connected = companies.filter((company) => company.relationships.length > 1).length;
  return <main className="investor-app venture-page venture-intelligence-page">
    <VentureNav />
    <header className="venture-intelligence-hero page-shell">
      <div><a className="back-link" href="/investors/venture">← Venture capital</a><p className="terminal-eyebrow">Exact released company IDs</p><h1>One company.<br /><span>Every tracked firm.</span></h1><p>Explore firm relationships already present in the active Venture release. No public-company mapping, ownership, or investment value is inferred.</p></div>
      <dl aria-label="Venture company connection summary"><div><dt>Companies</dt><dd>{companies.length}</dd></div><div><dt>Multi-firm</dt><dd>{connected}</dd></div><div><dt>Relationships</dt><dd>{companies.reduce((sum, company) => sum + company.relationships.length, 0)}</dd></div></dl>
    </header>
    <section className="venture-intelligence-shell page-shell" aria-labelledby="venture-company-index-title">
      <VentureTools active="companies" />
      <div className="venture-company-toolbar"><div><p className="terminal-eyebrow">Released connections</p><h2 id="venture-company-index-title">Company relationship index</h2></div><div><label><span>Search</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Company or firm" /></label><label><span>Sector</span><select value={sector} onChange={(event) => setSector(event.target.value)}><option value="all">All sectors</option>{sectors.map((item) => <option value={item} key={item}>{sentenceCase(item)}</option>)}</select></label></div></div>
      <div className="venture-company-grid">{visible.map((company, index) => <article className="venture-company-card" key={company.companyId}>
        <header><span>{String(index + 1).padStart(2, "0")}</span><b>{company.relationships.length} {company.relationships.length === 1 ? "firm" : "firms"}</b></header>
        <div><p>{sentenceCase(company.sector)}</p><h3>{company.companyName}</h3><code>{company.companyId}</code></div>
        <ul>{company.relationships.map(({ firm, relationship }) => <li key={firm.firm_id}><a href={`/investors/venture/${firm.firm_id}`}><strong>{firm.name}</strong><span>{relationship.first_partnered_year ?? "Year undisclosed"}</span></a><a href={relationship.source_url} target="_blank" rel="noreferrer" aria-label={`${company.companyName} source from ${firm.name}`}>↗</a></li>)}</ul>
      </article>)}</div>
      {visible.length === 0 && <p className="empty-filter">No released company relationship matches this filter.</p>}
      <p className="data-note">Firm counts use exact company IDs inside {ventureCatalog.release_id}. They do not establish ownership, syndication, co-investment timing, or total portfolio coverage.</p>
    </section>
    <VentureFooter />
  </main>;
}

export function VentureOverlapPage() {
  const overlaps = useMemo(() => buildVentureOverlaps(ventureCatalog), []);
  const [leftId, setLeftId] = useState(ventureCatalog.firms[0].firm_id);
  const [rightId, setRightId] = useState(ventureCatalog.firms[1].firm_id);
  const selected = overlapFor(overlaps, leftId, rightId);
  const selectLeft = (id: string) => {
    setLeftId(id);
    if (id === rightId) setRightId(ventureCatalog.firms.find((firm) => firm.firm_id !== id)?.firm_id ?? rightId);
  };
  const selectRight = (id: string) => {
    setRightId(id);
    if (id === leftId) setLeftId(ventureCatalog.firms.find((firm) => firm.firm_id !== id)?.firm_id ?? leftId);
  };
  const count = (left: VentureFirm, right: VentureFirm) => left.firm_id === right.firm_id ? left.tracked_relationship_count : overlapFor(overlaps, left.firm_id, right.firm_id)?.sharedCompanyIds.length ?? 0;
  return <main className="investor-app venture-page venture-intelligence-page">
    <VentureNav />
    <header className="venture-intelligence-hero venture-overlap-hero page-shell">
      <div><a className="back-link" href="/investors/venture">← Venture capital</a><p className="terminal-eyebrow">Exact company ID intersection</p><h1>Overlap,<br /><span>without a score.</span></h1><p>Compare only identical company IDs in the active released sample. No similarity, conviction, allocation, or co-investment inference.</p></div>
      <div className="venture-overlap-signal"><span>Largest pair</span><strong>{overlaps[0]?.sharedCompanyIds.length ?? 0}</strong><p>{overlaps[0] ? `${overlaps[0].left.name} · ${overlaps[0].right.name}` : "No pair available"}</p></div>
    </header>
    <section className="venture-intelligence-shell page-shell" aria-labelledby="venture-overlap-title">
      <VentureTools active="overlap" />
      <div className="venture-overlap-controls"><div><p className="terminal-eyebrow">Pair explorer</p><h2 id="venture-overlap-title">Tracked relationship overlap</h2></div><div><label><span>First firm</span><select value={leftId} onChange={(event) => selectLeft(event.target.value)}>{ventureCatalog.firms.map((firm) => <option value={firm.firm_id} key={firm.firm_id}>{firm.name}</option>)}</select></label><span>with</span><label><span>Second firm</span><select value={rightId} onChange={(event) => selectRight(event.target.value)}>{ventureCatalog.firms.map((firm) => <option value={firm.firm_id} key={firm.firm_id}>{firm.name}</option>)}</select></label></div></div>
      <section className="venture-overlap-result" aria-label="Selected tracked relationship overlap"><div><span>Shared released companies</span><strong>{selected?.sharedCompanyIds.length ?? 0}</strong></div><div>{selected?.sharedCompanies.length ? selected.sharedCompanies.map((company) => <a href="/investors/venture/companies" key={company.companyId}><b>{company.companyName}</b><span>{sentenceCase(company.sector)}</span></a>) : <p>No identical released company IDs in this pair.</p>}</div></section>
      <section className="venture-matrix" aria-labelledby="venture-matrix-title"><div className="module-head"><div><span>02</span><h2 id="venture-matrix-title">Exact overlap matrix</h2></div><p>Diagonal = each firm's tracked count</p></div><TableScroll className="venture-matrix-scroll" label="Exact venture relationship overlap matrix"><table><thead><tr><th>Firm</th>{ventureCatalog.firms.map((firm) => <th key={firm.firm_id}>{firm.name}</th>)}</tr></thead><tbody>{ventureCatalog.firms.map((left) => <tr key={left.firm_id}><th><a href={`/investors/venture/${left.firm_id}`}>{left.name}</a></th>{ventureCatalog.firms.map((right) => <td className={left.firm_id === right.firm_id ? "diagonal" : count(left, right) > 0 ? "connected" : ""} key={right.firm_id}>{count(left, right)}</td>)}</tr>)}</tbody></table></TableScroll></section>
      <p className="data-note">Overlap means the same released company ID appears for both firms. It is not proof of the same financing round, current ownership, portfolio similarity, or coordinated activity.</p>
    </section>
    <VentureFooter />
  </main>;
}

export function VentureDetail({ firmId }: { firmId: string }) {
  const firm = ventureFirm(firmId);
  if (!firm) return <main className="investor-app venture-page"><VentureNav /><section className="source-review-page"><p className="terminal-eyebrow">404 / Venture firm not found</p><h1>No released firm here.</h1><a className="source-button" href="/investors/venture">Return to venture capital</a></section></main>;
  const knownYears = firm.relationships.filter((row) => row.first_partnered_year !== null).length;
  const maxSectorCount = Math.max(...firm.sector_counts.map((row) => row.company_count), 1);
  return <main className="investor-app venture-page">
    <VentureNav />
    <div className="venture-detail-shell">
      <a className="back-link" href="/investors/venture">← All venture firms</a>
      <header className="venture-detail-head"><div><p className="terminal-eyebrow">Venture capital · Bounded public record</p><h1>{firm.name}</h1><p>{firm.strategy_labels.join(" · ")}</p></div><a className="source-button" href={firm.source_url} target="_blank" rel="noreferrer">Official firm source ↗</a></header>
      <dl className="venture-detail-metrics" aria-label={`${firm.name} released relationship summary`}>
        <div><dt>Tracked relationships</dt><dd>{firm.tracked_relationship_count}</dd></div>
        <div><dt>Tracked sectors</dt><dd>{firm.sector_counts.length}</dd></div>
        <div><dt>Partnered year disclosed</dt><dd>{knownYears} / {firm.tracked_relationship_count}</dd></div>
        <div><dt>Source through</dt><dd>{readableDate(ventureCatalog.source_fresh_through)}</dd></div>
      </dl>
      <section className="terminal-module venture-relationships" aria-labelledby="venture-relationships-title">
        <div className="module-head"><div><span>01</span><h2 id="venture-relationships-title">Released relationships</h2></div><p>Exact source per row</p></div>
        <TableScroll className="holdings-scroll" label={`${firm.name} released relationships`}><table className="holdings-table venture-table"><thead><tr><th>Company</th><th>Sector</th><th>First partnered</th><th>Stage</th><th>Role</th><th>Follow-on</th><th>Source</th></tr></thead><tbody>{firm.relationships.map((row) => <tr key={row.company_id}><td><strong>{row.company_name}</strong><span>{row.company_id}</span></td><td>{sentenceCase(row.sector)}</td><td>{row.first_partnered_year ?? "Undisclosed"}</td><td>{sentenceCase(row.stage)}</td><td>{sentenceCase(row.participation_role)}</td><td>{sentenceCase(row.follow_on_status)}</td><td><a className="venture-source-link" href={row.source_url} target="_blank" rel="noreferrer">Official source ↗</a></td></tr>)}</tbody></table></TableScroll>
      </section>
      <section className="terminal-module venture-sectors" aria-labelledby="venture-sectors-title">
        <div className="module-head"><div><span>02</span><h2 id="venture-sectors-title">Tracked sectors</h2></div><p>Company count · Not capital weighted</p></div>
        <div className="venture-sector-bars">{firm.sector_counts.map((row) => <div key={row.sector}><span>{sentenceCase(row.sector)}</span><i><b style={{ width: `${(row.company_count / maxSectorCount) * 100}%` }} /></i><strong>{row.company_count}</strong></div>)}</div>
        <p className="data-note">Sector labels are versioned Libration classifications for this released sample. They do not describe allocation, investment value, ownership, or returns.</p>
      </section>
    </div>
    <VentureFooter />
  </main>;
}
