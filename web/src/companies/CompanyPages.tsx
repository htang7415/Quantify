import { useState } from "react";
import { SiteNav } from "../SiteNav";
import { earningsForTicker } from "../earnings/catalog";
import { policyEventsForTicker } from "../policy/catalog";
import { holdingChangeText, money, quarter } from "../format";
import { CatalogFooter } from "../investors/InvestorPages";
import { investorCatalog } from "../investors/catalog";
import { buildCompanyOwnership } from "./ownership";

const companies = buildCompanyOwnership(investorCatalog);

function CompanyNav() {
  return <SiteNav active="companies" action={{ label: "Verify a claim", href: "/agent" }} />;
}

export function CompanyIndex() {
  const [query, setQuery] = useState("");
  const matches = companies.filter((company) =>
    `${company.ticker} ${company.issuer} ${company.themes.join(" ")}`.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <main className="data-app company-index-page">
      <CompanyNav />
      <section className="data-hero page-shell">
        <div>
          <p className="terminal-eyebrow">Company ownership / {quarter(investorCatalog.report_period)}</p>
          <h1>Ownership, from the filings up.</h1>
          <p>Connect each mapped security to the reporting managers in Quantify's frozen 13F release.</p>
          <div className="scope-pills"><span><i /> DERIVED FROM RELEASE</span><span>NOT TOTAL INSTITUTIONAL OWNERSHIP</span></div>
        </div>
        <label className="terminal-search"><span>Search companies</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ticker, issuer, or theme" /></label>
      </section>
      <section className="company-directory page-shell" aria-labelledby="company-directory-title">
        <div className="data-section-head"><div><p className="terminal-eyebrow">Released mappings</p><h2 id="company-directory-title">{matches.length} companies</h2></div></div>
        <div className="company-card-grid">
          {matches.map((company) => (
            <a className="company-card" href={`/companies/${company.slug}`} key={company.slug}>
              <div><strong>{company.ticker}</strong><span>{company.themes[0] ?? "Unclassified"}</span></div>
              <h3>{company.issuer}</h3>
              <dl>
                <div><dt>Tracked disclosed value</dt><dd>{money(company.tracked_disclosed_value_usd)}</dd></div>
                <div><dt>Reporting managers</dt><dd>{company.reporting_manager_count}</dd></div>
              </dl>
              <span className="card-open">OPEN OWNERSHIP →</span>
            </a>
          ))}
        </div>
        {matches.length === 0 && <p className="empty-filter">No released company mapping matches this search.</p>}
      </section>
      <CatalogFooter />
    </main>
  );
}

export function CompanyDetail({ slug }: { slug: string }) {
  const company = companies.find((item) => item.slug === slug);
  if (!company) return <CompanyNotFound />;
  const earnings = earningsForTicker(company.ticker);
  const policyEvents = policyEventsForTicker(company.ticker);
  return (
    <main className="data-app company-detail-page">
      <CompanyNav />
      <div className="detail-shell">
        <a className="back-link" href="/companies">← All companies</a>
        <header className="company-detail-head">
          <div><p className="terminal-eyebrow">Reported ownership view</p><h1><span>{company.ticker}</span>{company.issuer}</h1><p>{company.themes.join(" · ") || "Unclassified"}</p></div>
          <span className="release-badge">{quarter(investorCatalog.report_period)} · FROZEN</span>
        </header>
        <section className="overview-module" aria-label="Company ownership overview">
          <div className="overview-metric"><strong>{money(company.tracked_disclosed_value_usd)}</strong><span>Sum across tracked managers</span></div>
          <div className="overview-metric"><strong>{company.reporting_manager_count}</strong><span>Reporting managers</span></div>
          <div className="overview-metric"><strong>{company.reported_position_count}</strong><span>Reported security rows</span></div>
          <div className="overview-metric"><strong>{quarter(investorCatalog.report_period)}</strong><span>13F report period</span></div>
        </section>
        <p className="company-scope-note">This is a deterministic view of Quantify's tracked 13F rows—not market capitalization, total institutional ownership, beneficial ownership, or live fund activity.</p>

        <section className="terminal-module" aria-labelledby="company-managers-title">
          <div className="module-head"><div><span>01</span><h2 id="company-managers-title">Reporting managers</h2></div><p>Sorted by disclosed position value</p></div>
          <div className="holdings-scroll">
            <table className="holdings-table company-manager-table">
              <thead><tr><th>Manager</th><th>Security</th><th>Value</th><th>Portfolio weight</th><th>Shares</th><th>QoQ shares</th><th>Source</th></tr></thead>
              <tbody>{company.positions.map(({ manager, holding }) => (
                <tr key={`${manager.slug}-${holding.security_id}`}>
                  <td><a href={`/investors/${manager.slug}`}><strong>{manager.firm}</strong><span>{manager.reporting_manager_name}</span></a></td>
                  <td>{holding.instrument_type}<span>CUSIP {holding.cusip}</span></td>
                  <td>{money(holding.value_usd)}</td>
                  <td><strong>{holding.weight_pct.toFixed(2)}%</strong><span>{holding.weight_delta_pp > 0 ? "+" : ""}{holding.weight_delta_pp.toFixed(2)} pp</span></td>
                  <td>{Math.round(holding.shares).toLocaleString("en-US")}</td>
                  <td className={holding.change === "new" || holding.change === "added" ? "positive" : holding.change === "reduced" ? "negative" : ""}>{holding.change.toUpperCase()} · {holdingChangeText(holding, true)}</td>
                  <td><a className="table-source-link" href={manager.latest_filing.source_url} target="_blank" rel="noreferrer">SEC ↗</a></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </section>

        {earnings && <section className="terminal-module company-earnings-module" aria-labelledby="company-earnings-title">
          <div className="module-head"><div><span>02</span><h2 id="company-earnings-title">Reported earnings</h2></div><p>SEC 10-Q · exact comparable facts</p></div>
          <div className="company-earnings-grid"><div><span>Revenue</span><strong>{money(earnings.revenue.value)}</strong><b>↑ {earnings.revenue.yoy_change_pct.toFixed(1)}% YoY</b></div><div><span>Diluted EPS</span><strong>${earnings.diluted_eps.value.toFixed(2)}</strong><b>↑ {earnings.diluted_eps.yoy_change_pct.toFixed(1)}% YoY</b></div><div><span>Fiscal period</span><strong>FY{earnings.fiscal_year} {earnings.fiscal_period}</strong><b>Filed {earnings.filed_at}</b></div><div><span>SEC source</span><strong>{earnings.form}</strong><a href={earnings.filing_url} target="_blank" rel="noreferrer">{earnings.accession} ↗</a></div></div>
          <p className="company-scope-note">Reported results only. No estimates, surprise labels, guidance interpretation, future earnings date, or price reaction.</p>
        </section>}

        {policyEvents.length > 0 && <section className="terminal-module company-policy-module" aria-labelledby="company-policy-title">
          <div className="module-head"><div><span>03</span><h2 id="company-policy-title">Named policy scope</h2></div><p>Official record · not predicted impact</p></div>
          {policyEvents.map((event) => <article className="company-policy-event" key={event.event_id}><div><span>{event.authority_name}</span><strong>{event.title}</strong><p>{event.details.kind === "advanced_computing_export_rule" ? event.details.named_products.join(" · ") : event.source_document_id}</p></div><div><span>Effective</span><strong>{event.effective_at}</strong><a href={event.source_url} target="_blank" rel="noreferrer">Official source ↗</a></div></article>)}
          <p className="company-scope-note">The official rule expressly names a product associated with this ticker. This connection does not establish revenue exposure, financial impact, or price direction.</p>
        </section>}

        <section className="connection-panel" aria-labelledby="company-connections-title">
          <div><p className="terminal-eyebrow">Connected intelligence</p><h2 id="company-connections-title">More forces, when released.</h2></div>
          <div className="connection-grid">
            <span><b>Investors</b><i className="available">Available</i></span>
            <span><b>ETF exposure</b><i>Release required</i></span>
            <span><b>Earnings</b><i className={earnings ? "available" : ""}>{earnings ? "Available" : "Not in current release"}</i></span>
            <span><b>Policy + events</b><i className={policyEvents.length ? "available" : ""}>{policyEvents.length ? "Named policy available" : "No named policy in release"}</i></span>
          </div>
        </section>
      </div>
      <CatalogFooter />
    </main>
  );
}

function CompanyNotFound() {
  return <main className="data-app"><CompanyNav /><section className="source-review-page"><p className="terminal-eyebrow">404 / Company not found</p><h1>No released company mapping here.</h1><p>Company pages are created only from exact ticker mappings in the current frozen investor catalog.</p><a className="source-button" href="/companies">Return to companies</a></section></main>;
}
