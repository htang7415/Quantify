import { useMemo, useState } from "react";
import { ResearchFooter, ResearchSubnav, TableScroll } from "../ResearchUI";
import { SectionConnections } from "../SectionConnections";
import { SiteNav } from "../SiteNav";
import { publicBrandText } from "../brand";
import { tickerSlug } from "../companies/ownership";
import { displayName, holdingChangeText, money, quarter, readableDate, sentenceCase } from "../format";
import { investorCatalog } from "./catalog";
import { compareInvestors } from "./comparison";
import type { ChangeKind, HistorySeries, Holding, InvestorManager } from "./types";

function securityLabel(holding: Pick<Holding, "ticker" | "cusip">): string {
  return holding.ticker ?? holding.cusip;
}

function TerminalNav() {
  return <SiteNav active="investors" action={{ label: "Verify a claim", href: "/agent" }} subnav={<ResearchSubnav group="research" active="investors" />} />;
}

function ChangeMark({ holding, compact = false }: { holding: Holding; compact?: boolean }) {
  const direction = holding.change === "added" || holding.change === "new" ? "up" : holding.change === "reduced" || holding.change === "exited" ? "down" : "flat";
  return (
    <span className={`change-mark change-${direction}`} aria-label={`${holding.change}: ${holdingChangeText(holding, compact)}`}>
      <b aria-hidden="true">{direction === "up" ? "▲" : direction === "down" ? "▼" : "—"}</b> {holdingChangeText(holding, compact)}
    </span>
  );
}

function InvestorCard({ manager }: { manager: InvestorManager }) {
  if (manager.status !== "available") {
    return (
      <a className="investor-card investor-card-review" href={`/investors/${manager.slug}`}>
        <div className="investor-card-head">
          <div><p>{displayName(manager.firm)}</p><span>{manager.person ?? displayName(manager.reporting_manager_name)}</span></div>
          <strong>Source review</strong>
        </div>
        <div className="review-grid" aria-hidden="true"><span /><span /><span /><span /></div>
        <p className="card-review-copy">Derived metrics withheld. The filing remains linked for direct review.</p>
        <span className="card-open">Open filing status ↗</span>
      </a>
    );
  }
  const signal = manager.changes.find((item) => item.change === "new") ?? manager.changes[0];
  return (
    <a className="investor-card" href={`/investors/${manager.slug}`}>
      <div className="investor-card-head">
        <div><p>{displayName(manager.firm)}</p><span>{manager.person ?? displayName(manager.reporting_manager_name)}</span></div>
        <strong>{manager.primary_theme}</strong>
      </div>
      <div className="card-metrics">
        <div><b>{money(manager.disclosed_portfolio_value_usd)}</b><span>Disclosed value</span></div>
        <div><b>{manager.holdings_count}</b><span>Positions</span></div>
        <div><b>{quarter(manager.latest_filing.report_period)}</b><span>13F period</span></div>
      </div>
      <div className="card-holdings" aria-label={`${manager.firm} top five holdings`}>
        {manager.holdings.slice(0, 5).map((holding) => (
          <span key={holding.security_id}><b>{securityLabel(holding)}</b><i>{holding.weight_pct.toFixed(1)}%</i></span>
        ))}
      </div>
      <div className="card-signal">
        {signal ? <><ChangeMark holding={signal} compact /><span>{securityLabel(signal)}</span></> : <span>No share change</span>}
        <span>Top 5 · {manager.top_five_concentration_pct?.toFixed(1)}%</span>
      </div>
    </a>
  );
}

export function InvestorDashboard() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const categories = ["All", ...new Set(investorCatalog.managers.map((manager) => manager.category))];
  const managers = investorCatalog.managers.filter((manager) => {
    const matchesQuery = `${manager.firm} ${manager.person ?? ""} ${manager.primary_theme}`.toLowerCase().includes(query.toLowerCase());
    return matchesQuery && (category === "All" || manager.category === category);
  });
  const available = investorCatalog.managers.filter((manager) => manager.status === "available");
  const disclosedValue = available.reduce((total, manager) => total + (manager.disclosed_portfolio_value_usd ?? 0), 0);

  return (
    <main className="investor-app">
      <TerminalNav />
      <section className="terminal-hero">
        <div>
          <nav className="investor-universe-tabs" aria-label="Investor universe">
            <a className="active" aria-current="page" href="/investors">Public markets</a>
            <a href="/investors/venture">Venture capital</a>
          </nav>
          <p className="terminal-eyebrow">Investor filings · {quarter(investorCatalog.report_period)}</p>
          <h1>Follow the money.<br /><span>Read the changes.</span></h1>
          <p>Reported positions, portfolio weights, and quarter-over-quarter share changes from frozen SEC filings.</p>
          <div className="scope-pills" aria-label="Investor catalog access and scope">
            <span><i /> SEC 13F · Frozen</span>
            <span>Public · No sign-in</span>
          </div>
        </div>
        <dl className="market-strip">
          <div><dt>Managers</dt><dd>{investorCatalog.managers.length.toString().padStart(2, "0")}</dd></div>
          <div><dt>Published</dt><dd>{available.length.toString().padStart(2, "0")}</dd></div>
          <div><dt>Disclosed value</dt><dd>{money(disclosedValue)}</dd></div>
          <div><dt>Source through</dt><dd>{readableDate(investorCatalog.source_fresh_through)}</dd></div>
        </dl>
      </section>

      <SectionConnections items={[
        { label: "Companies", detail: "Open a security across reporting managers", href: "/companies" },
        { label: "Markets", detail: "Trace filed ETF and crypto-linked exposure", href: "/markets" },
        { label: "Intelligence", detail: "Read released earnings and policy records", href: "/intelligence" }
      ]} />

      <section className="investor-index" aria-labelledby="investor-index-title">
        <div className="index-toolbar">
          <div><p className="terminal-eyebrow">Public markets</p><h2 id="investor-index-title">Tracked managers</h2></div>
          <div className="index-actions"><a className="compare-link" href="/investors/compare">Compare managers</a><label className="terminal-search"><span>Search</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Manager or theme" /></label></div>
        </div>
        <div className="category-tabs" aria-label="Filter investor category">
          {categories.map((item) => <button className={item === category ? "active" : ""} type="button" key={item} onClick={() => setCategory(item)}>{item}</button>)}
        </div>
        <div className="investor-grid">
          {managers.map((manager) => <InvestorCard manager={manager} key={manager.slug} />)}
        </div>
        {managers.length === 0 && <p className="empty-filter">No managers match this filter.</p>}
      </section>

      <CatalogFooter />
    </main>
  );
}

function comparisonChange(holding: Holding | null): string {
  if (!holding) return "Not reported";
  if (holding.change === "new" || holding.change === "unchanged") return sentenceCase(holding.change);
  return `${sentenceCase(holding.change)} · ${holdingChangeText(holding, true)}`;
}

export function InvestorComparisonPage() {
  const managers = investorCatalog.managers.filter((manager) => manager.status === "available");
  if (managers.length < 2) throw new Error("Investor comparison requires at least two released managers.");
  const [leftSlug, setLeftSlug] = useState(managers[0].slug);
  const [rightSlug, setRightSlug] = useState(managers[1].slug);
  const left = managers.find((manager) => manager.slug === leftSlug) ?? managers[0];
  const right = managers.find((manager) => manager.slug === rightSlug) ?? managers[1];
  const comparison = useMemo(() => compareInvestors(left, right), [left, right]);

  const selectLeft = (slug: string) => {
    setLeftSlug(slug);
    if (slug === rightSlug) setRightSlug(managers.find((manager) => manager.slug !== slug)?.slug ?? rightSlug);
  };
  const selectRight = (slug: string) => {
    setRightSlug(slug);
    if (slug === leftSlug) setLeftSlug(managers.find((manager) => manager.slug !== slug)?.slug ?? leftSlug);
  };

  return <main className="investor-app comparison-page">
    <TerminalNav />
    <div className="detail-shell">
      <a className="back-link" href="/investors">← All managers</a>
      <header className="comparison-head">
        <div><p className="terminal-eyebrow">Exact 13F security IDs · {quarter(investorCatalog.report_period)}</p><h1>Compare reported portfolios.</h1><p>See shared positions, disclosed weights, concentration, and reported share changes—without inferring trades or intent.</p></div>
        <span className="release-badge">{investorCatalog.release_id}</span>
      </header>

      <section className="comparison-controls" aria-label="Select reporting managers">
        <label><span>First reporting manager</span><select aria-label="First reporting manager" value={leftSlug} onChange={(event) => selectLeft(event.target.value)}>{managers.map((manager) => <option value={manager.slug} key={manager.slug}>{displayName(manager.firm)}</option>)}</select></label>
        <span aria-hidden="true">versus</span>
        <label><span>Second reporting manager</span><select aria-label="Second reporting manager" value={rightSlug} onChange={(event) => selectRight(event.target.value)}>{managers.map((manager) => <option value={manager.slug} key={manager.slug}>{displayName(manager.firm)}</option>)}</select></label>
      </section>

      <section className="comparison-manager-grid" aria-label="Reporting manager overview">
        {[comparison.left, comparison.right].map((manager) => <article key={manager.slug}>
          <div><p>{displayName(manager.firm)}</p><span>{manager.person ?? displayName(manager.reporting_manager_name)}</span></div>
          <dl><div><dt>Disclosed value</dt><dd>{money(manager.disclosed_portfolio_value_usd)}</dd></div><div><dt>Positions</dt><dd>{manager.holdings_count}</dd></div><div><dt>Top-5 concentration</dt><dd>{manager.top_five_concentration_pct?.toFixed(1)}%</dd></div></dl>
          <a href={manager.latest_filing.source_url} target="_blank" rel="noreferrer">SEC filing ↗</a>
        </article>)}
      </section>

      <section className="comparison-ribbon" aria-label="Exact position comparison summary">
        <div><span>Shared positions</span><strong>{comparison.sharedPositions}</strong></div>
        <div><span>{displayName(left.firm)} only</span><strong>{comparison.leftOnlyPositions}</strong></div>
        <div><span>{displayName(right.firm)} only</span><strong>{comparison.rightOnlyPositions}</strong></div>
        <div><span>Report period</span><strong>{quarter(left.latest_filing.report_period)}</strong></div>
      </section>

      <section className="terminal-module comparison-table-section" aria-labelledby="comparison-table-title">
        <div className="module-head"><div><span>01</span><h2 id="comparison-table-title">Position comparison</h2></div><p>Shared first · largest disclosed weight next</p></div>
        <TableScroll className="holdings-scroll" label="Reported portfolio comparison"><table className="holdings-table comparison-table"><thead><tr><th>Security</th><th>{displayName(left.firm)} weight</th><th>{displayName(right.firm)} weight</th><th>Weight gap</th><th>{displayName(left.firm)} QoQ shares</th><th>{displayName(right.firm)} QoQ shares</th><th>Match</th></tr></thead><tbody>{comparison.rows.map((row) => <tr key={row.securityId}><td>{row.ticker ? <a className="security-entity-link" href={`/companies/${tickerSlug(row.ticker)}`}><strong>{row.ticker}</strong><span>{displayName(row.issuer)} · CUSIP {row.cusip}</span></a> : <><strong>{row.cusip}</strong><span>{displayName(row.issuer)} · CUSIP {row.cusip}</span></>}</td><td>{row.left ? <><strong>{row.left.weight_pct.toFixed(2)}%</strong><span>{money(row.left.value_usd)}</span></> : "—"}</td><td>{row.right ? <><strong>{row.right.weight_pct.toFixed(2)}%</strong><span>{money(row.right.value_usd)}</span></> : "—"}</td><td className={row.weightGapPp > 0 ? "positive" : row.weightGapPp < 0 ? "negative" : ""}>{row.weightGapPp > 0 ? "+" : ""}{row.weightGapPp.toFixed(2)} pp<span>First minus second</span></td><td>{comparisonChange(row.left)}</td><td>{comparisonChange(row.right)}</td><td><span className={row.shared ? "comparison-match shared" : "comparison-match"}>{row.shared ? "Exact shared ID" : "One manager only"}</span></td></tr>)}</tbody></table></TableScroll>
        <p className="data-note">Shared means the same released security ID appears in both latest released holdings tables. It is not a similarity score, trade observation, or account-level portfolio comparison.</p>
      </section>
    </div>
    <CatalogFooter />
  </main>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="overview-metric"><strong>{value}</strong><span>{label}</span></div>;
}

function HoldingsTable({ manager }: { manager: InvestorManager }) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"weight" | "value" | "change">("weight");
  const holdings = useMemo(() => {
    const filtered = manager.holdings.filter((holding) => `${holding.issuer} ${holding.ticker ?? ""} ${holding.cusip}`.toLowerCase().includes(query.toLowerCase()));
    return [...filtered].sort((left, right) => sort === "weight" ? right.weight_pct - left.weight_pct : sort === "value" ? right.value_usd - left.value_usd : Math.abs(right.weight_delta_pp) - Math.abs(left.weight_delta_pp));
  }, [manager.holdings, query, sort]);
  return (
    <section className="terminal-module" id="holdings" aria-labelledby="holdings-title">
      <div className="module-head">
        <div><span>02</span><h2 id="holdings-title">Holdings</h2></div>
        <div className="table-controls">
          <input aria-label="Search holdings" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search ticker or issuer" />
          <select aria-label="Sort holdings" value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}>
            <option value="weight">Portfolio weight ↓</option><option value="value">Disclosed value ↓</option><option value="change">Weight change ↓</option>
          </select>
        </div>
      </div>
      <TableScroll className="holdings-scroll" label={`${displayName(manager.firm)} reported holdings`}>
        <table className="holdings-table">
          <thead><tr><th>Security</th><th>Instrument</th><th>Value</th><th>Weight</th><th>Shares</th><th>QoQ shares</th></tr></thead>
          <tbody>{holdings.map((holding) => (
            <tr key={holding.security_id}>
              <td>{holding.ticker ? <a className="security-entity-link" href={`/companies/${tickerSlug(holding.ticker)}`}><strong>{holding.ticker}</strong><span>{displayName(holding.issuer)}</span></a> : <><strong>{holding.cusip}</strong><span>{displayName(holding.issuer)}</span></>}</td>
              <td>{holding.put_call ? `${sentenceCase(holding.put_call)} option` : sentenceCase(holding.instrument_type)}<span>CUSIP {holding.cusip}</span></td>
              <td>{money(holding.value_usd)}</td>
              <td><strong>{holding.weight_pct.toFixed(2)}%</strong><span className={holding.weight_delta_pp > 0 ? "positive" : holding.weight_delta_pp < 0 ? "negative" : ""}>{holding.weight_delta_pp > 0 ? "+" : ""}{holding.weight_delta_pp.toFixed(2)} pp</span></td>
              <td>{Math.round(holding.shares).toLocaleString("en-US")}</td>
              <td><ChangeMark holding={holding} compact /></td>
            </tr>
          ))}</tbody>
        </table>
      </TableScroll>
    </section>
  );
}

function ChangesModule({ manager }: { manager: InvestorManager }) {
  const kinds: Array<Exclude<ChangeKind, "unchanged">> = ["new", "added", "reduced", "exited"];
  return (
    <section className="terminal-module" id="changes" aria-labelledby="changes-title">
      <div className="module-head"><div><span>03</span><h2 id="changes-title">Changes</h2></div><p>Share-count comparison · previous quarter</p></div>
      <div className="change-columns">
        {kinds.map((kind) => {
          const rows = manager.changes.filter((holding) => holding.change === kind).slice(0, 5);
          return <article key={kind} className={`change-column change-column-${kind}`}><h3>{sentenceCase(kind)}</h3>{rows.length ? rows.map((holding) => <div key={holding.security_id}>{holding.ticker ? <a className="security-entity-link" href={`/companies/${tickerSlug(holding.ticker)}`}><b>{holding.ticker}</b><i>{displayName(holding.issuer)}</i></a> : <span><b>{holding.cusip}</b><i>{displayName(holding.issuer)}</i></span>}<strong>{kind === "new" ? money(holding.value_usd) : holdingChangeText(holding)}</strong></div>) : <p>None reported</p>}</article>;
        })}
      </div>
    </section>
  );
}

function AllocationModule({ manager }: { manager: InvestorManager }) {
  const rows = manager.allocation.filter((item) => item.weight_pct >= 0.01).slice(0, 6);
  return (
    <section className="terminal-module allocation-module" id="allocation" aria-labelledby="allocation-title">
      <div className="module-head"><div><span>04</span><h2 id="allocation-title">Allocation</h2></div><p>Classification coverage · {manager.classification_coverage_pct.toFixed(1)}%</p></div>
      <div className="allocation-bars">{rows.map((row) => <div key={row.label}><span><b>{row.label}</b><i>{row.weight_pct.toFixed(1)}%</i></span><div><i style={{ width: `${Math.max(row.weight_pct, 0.5)}%` }} /></div></div>)}</div>
      <p className="module-note">Themes are versioned display metadata. Unclassified securities remain explicit and do not receive inferred categories.</p>
    </section>
  );
}

function Sparkline({ series }: { series: HistorySeries }) {
  const width = 180;
  const height = 42;
  const max = Math.max(...series.points.map((point) => point.weight_pct), 1);
  const points = series.points.map((point, index) => `${(index / Math.max(series.points.length - 1, 1)) * width},${height - (point.weight_pct / max) * (height - 5)}`).join(" ");
  return <svg className="history-spark" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${series.ticker ?? series.issuer} portfolio weight history`}><polyline points={points} /></svg>;
}

function HistoryModule({ manager }: { manager: InvestorManager }) {
  return (
    <section className="terminal-module" id="history" aria-labelledby="history-title">
      <div className="module-head"><div><span>05</span><h2 id="history-title">History</h2></div><p>Top positions in latest released filing · five quarters</p></div>
      <div className="history-table">{manager.history.map((series) => {
        const first = series.points[0]?.weight_pct ?? 0;
        const last = series.points.at(-1)?.weight_pct ?? 0;
        return <div key={series.security_id}><strong>{series.ticker ?? series.security_id.split("|")[0]}<span>{displayName(series.issuer)}</span></strong><div className="history-points">{series.points.map((point) => <span key={point.period}><b>{quarter(point.period).replace(" 20", "'")}</b><i>{point.weight_pct.toFixed(1)}%</i></span>)}</div><Sparkline series={series} /><span className={last > first ? "positive" : last < first ? "negative" : ""}>{last > first ? "↑" : last < first ? "↓" : "—"}</span></div>;
      })}</div>
    </section>
  );
}

function SourceReview({ manager }: { manager: InvestorManager }) {
  return (
    <section className="source-review-page">
      <p className="terminal-eyebrow">Source review required</p>
      <h1>{displayName(manager.firm)}</h1>
      <p>{manager.status_reason}</p>
      <dl><div><dt>Reporting manager</dt><dd>{displayName(manager.reporting_manager_name)}</dd></div><div><dt>Period</dt><dd>{quarter(manager.latest_filing.report_period)}</dd></div><div><dt>Accession</dt><dd>{manager.latest_filing.accession}</dd></div></dl>
      <a className="source-button" href={manager.latest_filing.source_url} target="_blank" rel="noreferrer">Open SEC filing ↗</a>
    </section>
  );
}

export function InvestorDetail({ slug }: { slug: string }) {
  const manager = investorCatalog.managers.find((item) => item.slug === slug);
  if (!manager) return <InvestorNotFound />;
  return (
    <main className="investor-app investor-detail-app">
      <TerminalNav />
      <div className="detail-shell">
        <a className="back-link" href="/investors">← All managers</a>
        {manager.status !== "available" ? <SourceReview manager={manager} /> : <>
          <header className="investor-detail-head">
            <div><p className="terminal-eyebrow">{manager.category}</p><h1>{manager.person && <span>{manager.person}</span>}{displayName(manager.firm)}</h1><p>{manager.primary_theme}</p></div>
            <a className="source-button" href={manager.latest_filing.source_url} target="_blank" rel="noreferrer">SEC filing ↗</a>
          </header>
          <section className="overview-module" aria-label="Investor overview">
            <Metric label="Disclosed portfolio value" value={money(manager.disclosed_portfolio_value_usd)} />
            <Metric label="Reported positions" value={String(manager.holdings_count)} />
            <Metric label="Top-5 concentration" value={`${manager.top_five_concentration_pct?.toFixed(1)}%`} />
            <Metric label="Latest filing" value={quarter(manager.latest_filing.report_period)} />
          </section>
          <div className="filing-line"><span>Filed {readableDate(manager.latest_filing.filed_date)}</span><span>CIK {manager.reporting_manager_cik}</span><span>{manager.latest_filing.accession}</span></div>
          <HoldingsTable manager={manager} />
          <ChangesModule manager={manager} />
          <AllocationModule manager={manager} />
          <HistoryModule manager={manager} />
        </>}
      </div>
      <CatalogFooter />
    </main>
  );
}

function InvestorNotFound() {
  return <main className="investor-app"><TerminalNav /><section className="source-review-page"><p className="terminal-eyebrow">404 / Manager not found</p><h1>No disclosed portfolio here.</h1><a className="source-button" href="/investors">Return to investors</a></section></main>;
}

export function CatalogFooter() {
  const available = investorCatalog.managers.filter((manager) => manager.status === "available").length;
  return <ResearchFooter
    details={[{ label: "Release ID", value: investorCatalog.release_id }, { label: "Manifest", value: investorCatalog.manifest_hash }, { label: "Report period", value: investorCatalog.report_period }]}
    limitations={investorCatalog.limitations.map((limitation) => publicBrandText(limitation))}
    observed={`Source through ${readableDate(investorCatalog.source_fresh_through)}`}
    source={investorCatalog.source}
    status={`${available} of ${investorCatalog.managers.length} managers available`}
  />;
}
