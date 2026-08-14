import { useMemo, useState } from "react";
import { SiteNav } from "../SiteNav";
import { holdingChangeText, money, quarter, readableDate } from "../format";
import { investorCatalog } from "./catalog";
import type { ChangeKind, HistorySeries, Holding, InvestorManager } from "./types";

function securityLabel(holding: Pick<Holding, "ticker" | "cusip">): string {
  return holding.ticker ?? holding.cusip;
}

function TerminalNav() {
  return <SiteNav active="investors" action={{ label: "Verify a claim", href: "/agent" }} />;
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
          <div><p>{manager.firm}</p><span>{manager.person ?? manager.reporting_manager_name}</span></div>
          <strong>SOURCE REVIEW</strong>
        </div>
        <div className="review-grid" aria-hidden="true"><span /><span /><span /><span /></div>
        <p className="card-review-copy">Derived metrics withheld. The filing remains linked for direct review.</p>
        <span className="card-open">OPEN FILING STATUS ↗</span>
      </a>
    );
  }
  const signal = manager.changes.find((item) => item.change === "new") ?? manager.changes[0];
  return (
    <a className="investor-card" href={`/investors/${manager.slug}`}>
      <div className="investor-card-head">
        <div><p>{manager.firm}</p><span>{manager.person ?? manager.reporting_manager_name}</span></div>
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
        {signal ? <><ChangeMark holding={signal} compact /><span>{securityLabel(signal)}</span></> : <span>NO SHARE CHANGE</span>}
        <span>TOP 5 · {manager.top_five_concentration_pct?.toFixed(1)}%</span>
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
          <p className="terminal-eyebrow">Elite investor intelligence / {quarter(investorCatalog.report_period)}</p>
          <h1>Follow the money.<br /><span>Read the changes.</span></h1>
          <p>Reported positions, portfolio weights, and quarter-over-quarter share changes from frozen SEC filings.</p>
          <div className="scope-pills" aria-label="Investor catalog access and scope">
            <span><i /> SEC 13F · FROZEN</span>
            <span>PUBLIC · NO SIGN-IN</span>
          </div>
        </div>
        <dl className="market-strip">
          <div><dt>Managers</dt><dd>{investorCatalog.managers.length.toString().padStart(2, "0")}</dd></div>
          <div><dt>Published</dt><dd>{available.length.toString().padStart(2, "0")}</dd></div>
          <div><dt>Disclosed value</dt><dd>{money(disclosedValue)}</dd></div>
          <div><dt>Source through</dt><dd>{readableDate(investorCatalog.source_fresh_through)}</dd></div>
        </dl>
      </section>

      <section className="investor-index" aria-labelledby="investor-index-title">
        <div className="index-toolbar">
          <div><p className="terminal-eyebrow">Public markets</p><h2 id="investor-index-title">Tracked managers</h2></div>
          <label className="terminal-search"><span>Search</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Manager or theme" /></label>
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
      <div className="holdings-scroll">
        <table className="holdings-table">
          <thead><tr><th>Security</th><th>Instrument</th><th>Value</th><th>Weight</th><th>Shares</th><th>QoQ shares</th></tr></thead>
          <tbody>{holdings.map((holding) => (
            <tr key={holding.security_id}>
              <td><strong>{securityLabel(holding)}</strong><span>{holding.issuer}</span></td>
              <td>{holding.put_call ? `${holding.put_call} option` : holding.instrument_type}<span>CUSIP {holding.cusip}</span></td>
              <td>{money(holding.value_usd)}</td>
              <td><strong>{holding.weight_pct.toFixed(2)}%</strong><span className={holding.weight_delta_pp > 0 ? "positive" : holding.weight_delta_pp < 0 ? "negative" : ""}>{holding.weight_delta_pp > 0 ? "+" : ""}{holding.weight_delta_pp.toFixed(2)} pp</span></td>
              <td>{Math.round(holding.shares).toLocaleString("en-US")}</td>
              <td><ChangeMark holding={holding} compact /></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
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
          return <article key={kind} className={`change-column change-column-${kind}`}><h3>{kind}</h3>{rows.length ? rows.map((holding) => <div key={holding.security_id}><span><b>{securityLabel(holding)}</b><i>{holding.issuer}</i></span><strong>{kind === "new" ? money(holding.value_usd) : holdingChangeText(holding)}</strong></div>) : <p>None reported</p>}</article>;
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
      <div className="module-head"><div><span>05</span><h2 id="history-title">History</h2></div><p>Top current positions · five quarters</p></div>
      <div className="history-table">{manager.history.map((series) => {
        const first = series.points[0]?.weight_pct ?? 0;
        const last = series.points.at(-1)?.weight_pct ?? 0;
        return <div key={series.security_id}><strong>{series.ticker ?? series.security_id.split("|")[0]}<span>{series.issuer}</span></strong><div className="history-points">{series.points.map((point) => <span key={point.period}><b>{quarter(point.period).replace(" 20", "'")}</b><i>{point.weight_pct.toFixed(1)}%</i></span>)}</div><Sparkline series={series} /><span className={last > first ? "positive" : last < first ? "negative" : ""}>{last > first ? "↑" : last < first ? "↓" : "—"}</span></div>;
      })}</div>
    </section>
  );
}

function SourceReview({ manager }: { manager: InvestorManager }) {
  return (
    <section className="source-review-page">
      <p className="terminal-eyebrow">Source review required</p>
      <h1>{manager.firm}</h1>
      <p>{manager.status_reason}</p>
      <dl><div><dt>Reporting manager</dt><dd>{manager.reporting_manager_name}</dd></div><div><dt>Period</dt><dd>{quarter(manager.latest_filing.report_period)}</dd></div><div><dt>Accession</dt><dd>{manager.latest_filing.accession}</dd></div></dl>
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
            <div><p className="terminal-eyebrow">{manager.category}</p><h1>{manager.person && <span>{manager.person}</span>}{manager.firm}</h1><p>{manager.primary_theme}</p></div>
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
  return (
    <footer className="catalog-footer">
      <div><strong>Scope / {investorCatalog.release_id}</strong><span>{investorCatalog.source}</span><code>{investorCatalog.manifest_hash}</code></div>
      <div>{investorCatalog.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}</div>
      <p>Research data only. No price predictions, trade recommendations, or personalized investment advice.</p>
    </footer>
  );
}
