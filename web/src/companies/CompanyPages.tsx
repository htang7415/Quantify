import { useState } from "react";
import { ResearchFooter, ResearchHero, ResearchSubnav, TableScroll, UnavailableState } from "../ResearchUI";
import { SectionConnections } from "../SectionConnections";
import { SiteNav } from "../SiteNav";
import { earningsCatalog, earningsForTicker } from "../earnings/catalog";
import { etfExposuresForTicker, etfHoldingsCatalog } from "../etfs/holdingsCatalog";
import { policyEventCatalog, policyEventsForTicker } from "../policy/catalog";
import { directionalPercent, displayName, holdingChangeText, money, quarter, readableDate, sentenceCase } from "../format";
import { investorCatalog } from "../investors/catalog";
import { verificationCompanyForTicker } from "../verificationContract";
import { buildCompanyOwnership, type CompanyOwnership } from "./ownership";
import { companyConnections } from "./connections";

const companies = buildCompanyOwnership(investorCatalog);

function CompanyNav() {
  return <SiteNav active="companies" action={{ label: "Verify a claim", href: "/agent" }} subnav={<ResearchSubnav group="research" active="companies" />} />;
}

function CompanyResearchItem({ href, label, state }: { href?: string; label: string; state: string }) {
  const content = <><span>{label}</span><strong>{state}{href ? " →" : ""}</strong></>;
  return href ? <a href={href}>{content}</a> : <span className="is-unavailable">{content}</span>;
}

function CompanyFooter({ company, releasedModules }: { company?: CompanyOwnership; releasedModules?: number }) {
  return <ResearchFooter
    details={[
      { label: "13F release", value: `${investorCatalog.release_id} · ${investorCatalog.manifest_hash}` },
      { label: "ETF release", value: `${etfHoldingsCatalog.release_id} · ${etfHoldingsCatalog.manifest_hash}` },
      { label: "Earnings release", value: `${earningsCatalog.release_id} · ${earningsCatalog.manifest_hash}` },
      { label: "Policy release", value: `${policyEventCatalog.release_id} · ${policyEventCatalog.manifest_hash}` }
    ]}
    limitations={[
      "Company connections are exact ticker mappings across current released catalogs; they are not a complete company profile.",
      "13F values are reported rows, not total ownership or current positions.",
      "ETF exposure contains only reviewed top-ten filed rows.",
      "Earnings and policy appear only where the active releases contain the exact company identity."
    ]}
    observed={`13F ${readableDate(investorCatalog.source_fresh_through)} · N-PORT ${readableDate(etfHoldingsCatalog.observed_at.slice(0, 10))} · Earnings ${readableDate(earningsCatalog.observed_at.slice(0, 10))} · Policy ${readableDate(policyEventCatalog.observed_at.slice(0, 10))}`}
    source="SEC 13F · SEC Form N-PORT · SEC Company Facts · Official policy records"
    status={company && releasedModules ? `${company.ticker} · ${releasedModules} released research ${releasedModules === 1 ? "module" : "modules"}` : `${companies.length} mapped companies · Released connections only`}
  />;
}

export function CompanyIndex() {
  const [query, setQuery] = useState("");
  const matches = companies.filter((company) =>
    `${company.ticker} ${company.issuer} ${company.themes.join(" ")}`.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <main className="data-app company-index-page">
      <CompanyNav />
      <ResearchHero aside={<label className="terminal-search"><span>Search companies</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ticker, issuer, or theme" /></label>} description="Companies derived from the frozen 13F release, with exact links to compatible ETF, earnings, and policy records." eyebrow={`Company research / ${quarter(investorCatalog.report_period)}`} scope={[{ label: "Derived from 13F release", available: true }, { label: "Exact released connections only", available: true }]} scopeLabel="Company research scope" title="Who reports what." />
      <SectionConnections items={[
        { label: "Investors", detail: "Trace exact reporting-manager positions", href: "/investors" },
        { label: "Markets", detail: "Open filed ETF and market context", href: "/markets" },
        { label: "Intelligence", detail: "Read released earnings and policy records", href: "/intelligence" }
      ]} />
      <section className="company-directory page-shell" aria-labelledby="company-directory-title">
        <div className="data-section-head"><div><p className="terminal-eyebrow">Released mappings</p><h2 id="company-directory-title">{matches.length} companies</h2></div></div>
        <div className="company-card-grid">
          {matches.map((company) => {
            const connections = companyConnections(company);
            return <a className="company-card" href={`/companies/${company.slug}`} key={company.slug}>
              <div><strong>{company.ticker}</strong><span>{company.themes[0] ?? "Unclassified"}</span></div>
              <h3>{displayName(company.issuer)}</h3>
              <dl>
                <div><dt>Tracked disclosed value</dt><dd>{money(company.tracked_disclosed_value_usd)}</dd></div>
                <div><dt>Reporting managers</dt><dd>{company.reporting_manager_count}</dd></div>
              </dl>
              <div className="company-card-connections" aria-label={`${company.ticker} released connections`}><span>{connections.etfRows} ETF {connections.etfRows === 1 ? "row" : "rows"}</span><span>{connections.earningsAvailable ? "Earnings" : "No earnings release"}</span><span>{connections.policyEvents} policy {connections.policyEvents === 1 ? "event" : "events"}</span></div>
              <span className="card-open">Open reported positions →</span>
            </a>;
          })}
        </div>
        {matches.length === 0 && <p className="empty-filter">No released company mapping matches this search.</p>}
      </section>
      <CompanyFooter />
    </main>
  );
}

export function CompanyDetail({ slug }: { slug: string }) {
  const company = companies.find((item) => item.slug === slug);
  if (!company) return <CompanyNotFound />;
  const earnings = earningsForTicker(company.ticker);
  const policyEvents = policyEventsForTicker(company.ticker);
  const etfExposures = etfExposuresForTicker(company.ticker);
  const earningsModule = etfExposures.length ? "03" : "02";
  const policyModule = String(2 + (etfExposures.length ? 1 : 0) + (earnings ? 1 : 0)).padStart(2, "0");
  const verificationCompany = verificationCompanyForTicker(company.ticker);
  const releasedModules = 1 + Number(etfExposures.length > 0) + Number(Boolean(earnings)) + Number(policyEvents.length > 0);
  return (
    <main className="data-app company-detail-page">
      <CompanyNav />
      <div className="detail-shell">
        <a className="back-link" href="/companies">← All companies</a>
        <header className="company-detail-head">
          <div><p className="terminal-eyebrow">Company research · released data</p><h1><span>{company.ticker}</span>{displayName(company.issuer)}</h1><p>{company.themes.join(" · ") || "Unclassified"}</p></div>
          <div className="company-detail-actions">
            <span className="release-badge">{quarter(investorCatalog.report_period)} · Frozen</span>
            {verificationCompany ? <><a className="button button-dark button-compact" href={`/agent?company=${verificationCompany.cik}`}>Verify a claim about {company.ticker}</a><small>Company preselected · claim stays empty</small></> : <div className="company-verification-unavailable"><strong>Verification not released for this company</strong><a href="/coverage">Check coverage →</a></div>}
          </div>
        </header>
        <section className="overview-module" aria-label="Reported company position overview">
          <div className="overview-metric"><strong>{money(company.tracked_disclosed_value_usd)}</strong><span>Sum across tracked managers</span></div>
          <div className="overview-metric"><strong>{company.reporting_manager_count}</strong><span>Reporting managers</span></div>
          <div className="overview-metric"><strong>{company.reported_position_count}</strong><span>Reported security rows</span></div>
          <div className="overview-metric"><strong>{quarter(investorCatalog.report_period)}</strong><span>13F report period</span></div>
        </section>
        <p className="company-scope-note">This view covers Libration's tracked 13F rows—not market capitalization, total institutional ownership, beneficial ownership, or live fund activity.</p>
        <nav className="company-module-nav" aria-label={`${company.ticker} research sections`}>
          <CompanyResearchItem href="#company-managers-title" label="Reporting managers" state={`${company.reported_position_count} reported rows`} />
          <CompanyResearchItem href={etfExposures.length ? "#company-etf-title" : undefined} label="ETF exposure" state={etfExposures.length ? `${etfExposures.length} filed top-ten ${etfExposures.length === 1 ? "row" : "rows"}` : "No mapped row in release"} />
          <CompanyResearchItem href={earnings ? "#company-earnings-title" : undefined} label="Earnings" state={earnings ? `FY${earnings.fiscal_year} ${earnings.fiscal_period} filed result` : "Not in current release"} />
          <CompanyResearchItem href={policyEvents.length ? "#company-policy-title" : undefined} label="Policy" state={policyEvents.length ? `${policyEvents.length} named ${policyEvents.length === 1 ? "action" : "actions"}` : "No named policy in release"} />
        </nav>

        <section className="terminal-module" aria-labelledby="company-managers-title">
          <div className="module-head"><div><span>01</span><h2 id="company-managers-title">Reporting managers</h2></div><p>Sorted by disclosed position value</p></div>
          <TableScroll className="holdings-scroll" label={`${company.ticker} reporting managers`}>
            <table className="holdings-table company-manager-table">
              <thead><tr><th>Manager</th><th>Security</th><th>Value</th><th>Portfolio weight</th><th>Shares</th><th>QoQ shares</th><th>Source</th></tr></thead>
              <tbody>{company.positions.map(({ manager, holding }) => (
                <tr key={`${manager.slug}-${holding.security_id}`}>
                  <td><a href={`/investors/${manager.slug}`}><strong>{displayName(manager.firm)}</strong><span>{displayName(manager.reporting_manager_name)}</span></a></td>
                  <td>{sentenceCase(holding.instrument_type)}<span>CUSIP {holding.cusip}</span></td>
                  <td>{money(holding.value_usd)}</td>
                  <td><strong>{holding.weight_pct.toFixed(2)}%</strong><span>{holding.weight_delta_pp > 0 ? "+" : ""}{holding.weight_delta_pp.toFixed(2)} pp</span></td>
                  <td>{Math.round(holding.shares).toLocaleString("en-US")}</td>
                  <td className={holding.change === "new" || holding.change === "added" ? "positive" : holding.change === "reduced" ? "negative" : ""}>{sentenceCase(holding.change)} · {holdingChangeText(holding, true)}</td>
                  <td><a className="table-source-link" href={manager.latest_filing.source_url} target="_blank" rel="noreferrer">SEC ↗</a></td>
                </tr>
              ))}</tbody>
            </table>
          </TableScroll>
        </section>

        {etfExposures.length > 0 && <section className="terminal-module company-etf-module" aria-labelledby="company-etf-title">
          <div className="module-head"><div><span>02</span><h2 id="company-etf-title">ETF exposure</h2></div><p>Top-ten filed rows only</p></div>
          <TableScroll className="holdings-scroll" label={`${company.ticker} filed ETF exposure`}><table className="holdings-table company-etf-table"><thead><tr><th>Fund</th><th>Filed position value</th><th>Filed weight</th><th>Shares</th><th>Report date</th><th>Source</th></tr></thead><tbody>{etfExposures.map(({ fund, holding }) => <tr key={`${fund.fund_id}-${holding.holding_id}`}><td><a href={`/markets/etfs/${fund.slug}`}><strong>{fund.ticker}</strong><span>{fund.name}</span></a></td><td>{money(holding.currency_value)}</td><td><strong>{holding.filed_percentage.toFixed(2)}%</strong></td><td>{Math.round(holding.balance).toLocaleString("en-US")}</td><td>{fund.report_date}</td><td><a className="table-source-link" href={fund.source_url} target="_blank" rel="noreferrer">N-PORT ↗</a></td></tr>)}</tbody></table></TableScroll>
          <p className="company-scope-note">An ETF connection means this exact mapped security appears among the fund's ten largest reviewed Form N-PORT rows. It is not current exposure, complete ETF ownership, or flow attribution.</p>
        </section>}

        {earnings && <section className="terminal-module company-earnings-module" aria-labelledby="company-earnings-title">
          <div className="module-head"><div><span>{earningsModule}</span><h2 id="company-earnings-title">Reported earnings</h2></div><a className="module-connection-link" href="/intelligence/earnings">All earnings →</a></div>
          <div className="company-earnings-grid"><div><span>Revenue</span><strong>{money(earnings.revenue.value)}</strong><b>{directionalPercent(earnings.revenue.yoy_change_pct)} YoY</b></div><div><span>Diluted EPS</span><strong>${earnings.diluted_eps.value.toFixed(2)}</strong><b>{directionalPercent(earnings.diluted_eps.yoy_change_pct)} YoY</b></div><div><span>Fiscal period</span><strong>FY{earnings.fiscal_year} {earnings.fiscal_period}</strong><b>Filed {earnings.filed_at}</b></div><div><span>SEC source</span><strong>{earnings.form}</strong><a href={earnings.filing_url} target="_blank" rel="noreferrer">{earnings.accession} ↗</a></div></div>
          <p className="company-scope-note">Reported results only. No estimates, surprise labels, guidance interpretation, future earnings date, or price reaction.</p>
        </section>}

        {policyEvents.length > 0 && <section className="terminal-module company-policy-module" aria-labelledby="company-policy-title">
          <div className="module-head"><div><span>{policyModule}</span><h2 id="company-policy-title">Named policy scope</h2></div><a className="module-connection-link" href="/intelligence/policy">All policy →</a></div>
          {policyEvents.map((event) => <article className="company-policy-event" key={event.event_id}><div><span>{event.authority_name}</span><strong>{event.title}</strong><p>{event.details.kind === "advanced_computing_export_rule" ? event.details.named_products.join(" · ") : event.source_document_id}</p></div><div><span>Effective</span><strong>{event.effective_at}</strong><a href={event.source_url} target="_blank" rel="noreferrer">Official source ↗</a></div></article>)}
          <p className="company-scope-note">The official rule expressly names a product associated with this ticker. This connection does not establish revenue exposure, financial impact, or price direction.</p>
        </section>}

      </div>
      <CompanyFooter company={company} releasedModules={releasedModules} />
    </main>
  );
}

function CompanyNotFound() {
  return <main className="data-app"><CompanyNav /><UnavailableState action={{ label: "Return to companies", href: "/companies" }} eyebrow="404 / Company not found" reason="Company pages are created only from exact ticker mappings in the current frozen investor catalog." title="No released company mapping here." /></main>;
}
