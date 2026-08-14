import { SectionConnections } from "../SectionConnections";
import { SiteNav } from "../SiteNav";
import { buildCompanyOwnership } from "../companies/ownership";
import { earningsCatalog } from "../earnings/catalog";
import { directionalPercent, money, readableDate, sentenceCase } from "../format";
import { investorCatalog } from "../investors/catalog";
import { policyEventCatalog } from "../policy/catalog";
import type { PolicyEvent } from "../policy/types";
import { releaseFor } from "../releases/catalog";

const eventRelease = releaseFor("events");
const earningsRelease = releaseFor("earnings");
const policyRelease = releaseFor("policy");
const releasedCompanySlugs = new Map(buildCompanyOwnership(investorCatalog).map((company) => [company.ticker, company.slug]));

export function IntelligencePage() {
  const earningsAvailable = earningsRelease.status === "available";
  const policyAvailable = policyRelease.status === "available";
  const availableLabels = [earningsAvailable ? "Earnings" : null, policyAvailable ? "policy" : null].filter((label): label is string => label !== null);
  const coverage = [
    earningsAvailable ? `reported earnings for ${earningsCatalog.companies.length} companies` : null,
    policyAvailable ? `${policyEventCatalog.events.length} official policy actions` : null
  ].filter((item): item is string => item !== null);
  const layers = [
    ["Earnings", `Exact reported revenue and diluted EPS for ${earningsCatalog.companies.length} released companies, with comparable prior-year facts.`, "/intelligence/earnings", "Available", earningsAvailable],
    ["Policy", `Authority, action, effective date, named scope, and official source for ${policyEventCatalog.events.length} released actions.`, "/intelligence/policy", "Available", policyAvailable],
    ["Release operations", "Every declared public catalog, freshness state, release ID, and manifest hash.", "/intelligence/releases", "Inspect releases", true],
    ["High-impact events", "What happened, why it may matter, and exact released connections.", "", "Release required", false],
    ["Daily brief", "Only after every factual statement can bind to an eligible release field.", "", "Release required", false]
  ] as const;
  return (
    <main className="data-app intelligence-page">
      <SiteNav active="intelligence" action={{ label: "Verify a claim", href: "/agent" }} />
      <section className="data-hero page-shell">
        <div><p className="terminal-eyebrow">Released intelligence · provenance</p><h1><span>What happened.</span>{" "}<span>What changed.</span>{" "}<span>What is connected.</span></h1><p>{coverage.length ? `Current released coverage: ${coverage.join("; ")}.` : "No earnings or policy catalog is currently released."} High-impact narrative events remain unavailable until independently released.</p><div className="scope-pills"><span><i /> {availableLabels.length ? `${availableLabels.join(" + ")} available` : "No intelligence catalog available"}</span><span>Narrative events unavailable</span></div></div>
      </section>
      <SectionConnections items={[
        { label: "Companies", detail: "Open exact earnings and named policy scope", href: "/companies" },
        { label: "Markets", detail: "Read rates, ETF, and crypto context", href: "/markets" },
        { label: "Investors", detail: "Trace released reporting-manager positions", href: "/investors" }
      ]} />
      <nav className="market-subnav page-shell" aria-label="Intelligence sections"><a className="active" href="/intelligence">All intelligence</a><a href="/intelligence/earnings">Earnings</a><a href="/intelligence/policy">Policy</a><a href="/intelligence/releases">Release operations</a></nav>
      <section className="intelligence-empty-grid page-shell">
        {layers.map(([title, copy, href, status, available], index) => <article className={available ? "intelligence-layer-available" : ""} key={title}><span>0{index + 1}</span><h2>{title}</h2><p>{copy}</p>{available && href ? <a href={href}>{status} →</a> : <i>{status === "Available" ? "Release required" : status}</i>}</article>)}
      </section>
      <footer className="catalog-footer market-catalog-footer"><div><strong>Intelligence boundary</strong><span>Reported earnings and policy actions are active; narrative event releases remain unavailable.</span></div><div><p>{earningsRelease.limitations[0]} {policyRelease.limitations[0]}</p><p>{eventRelease.limitations[0]} Narrative retrieval may provide context later, but it cannot establish a fact, entity connection, or market direction.</p></div><p>Research data only. No price predictions, trade recommendations, or personalized investment advice.</p></footer>
    </main>
  );
}

function categoryLabel(category: PolicyEvent["category"]): string {
  if (category === "monetary_policy") return "Monetary policy";
  if (category === "financial_regulation") return "Financial regulation";
  return "Trade / export controls";
}

function PolicyDetails({ event }: { event: PolicyEvent }) {
  const details = event.details;
  if (details.kind === "fomc_decision") return <>
    <div className="policy-primary-value"><span>Federal funds target</span><strong>{details.target_range_low_pct.toFixed(2)}–{details.target_range_high_pct.toFixed(2)}%</strong><b>Maintained · {details.vote_for}–{details.vote_against} vote</b></div>
    <div className="policy-facts"><span><b>Next scheduled meeting</b>{details.next_meeting_start} → {details.next_meeting_end}</span><a href={details.calendar_source_url} target="_blank" rel="noreferrer">FOMC calendar ↗</a><a href={details.implementation_source_url} target="_blank" rel="noreferrer">Implementation note ↗</a></div>
  </>;
  if (details.kind === "joint_data_standards") return <>
    <div className="policy-primary-value"><span>Rule status</span><strong>Final</strong><b>Effective {event.effective_at}</b></div>
    <div className="policy-facts"><span><b>Issuing agencies</b>{details.agencies.length} federal financial regulators</span><span><b>Release numbers</b>{details.release_numbers.join(" · ")}</span><span><b>At effective date</b>No reporting-requirement change without further agency action</span></div>
  </>;
  const conditionLabels: Record<string, string> = {
    commercial_availability: "Commercial availability",
    us_supply_capacity: "U.S. supply capacity",
    recipient_security_procedures: "Recipient security procedures",
    independent_us_testing: "Independent U.S. testing"
  };
  return <>
    <div className="policy-primary-value"><span>License review</span><strong>Case by case</strong><b>If conditions are met</b></div>
    <div className="policy-facts"><span><b>Named products</b>{details.named_products.join(" · ")}</span><span><b>Destinations</b>{details.destinations.join(" · ")}</span><span><b>Required condition set</b>{details.conditions.map((condition) => conditionLabels[condition]).join(" · ")}</span><span><b>Federal Register</b>{details.federal_register_citation}</span></div>
  </>;
}

export function PolicyPage() {
  return (
    <main className="data-app policy-page">
      <SiteNav active="intelligence" action={{ label: "Verify a claim", href: "/agent" }} />
      <section className="data-hero policy-hero page-shell">
        <div><p className="terminal-eyebrow">Intelligence / policy / official actions</p><h1>Action, scope, effective date.</h1><p>Typed official policy records—without speeches, news noise, market-implied probabilities, or certain price-direction claims.</p><div className="scope-pills"><span><i /> {policyEventCatalog.events.length} reviewed actions</span><span>Observed through {readableDate(policyEventCatalog.observed_at.slice(0, 10))}</span></div></div>
      </section>
      <nav className="market-subnav page-shell" aria-label="Intelligence sections"><a href="/intelligence">All intelligence</a><a href="/intelligence/earnings">Earnings</a><a className="active" href="/intelligence/policy">Policy</a><a href="/intelligence/releases">Release operations</a></nav>
      <section className="policy-event-section page-shell" aria-labelledby="policy-events-title">
        <div className="data-section-head"><div><p className="terminal-eyebrow">Official records</p><h2 id="policy-events-title">Released policy actions</h2></div><span className="release-badge">No market direction</span></div>
        <div className="policy-event-list">
          {policyEventCatalog.events.map((event, index) => <article className="policy-event-card" key={event.event_id}>
            <header><span>{String(index + 1).padStart(2, "0")} / {categoryLabel(event.category)}</span><b className={event.status === "active" ? "policy-status-active" : ""}>{sentenceCase(event.status)}</b></header>
            <div className="policy-event-title"><div><p>{event.authority_name}</p><h3>{event.title}</h3></div><dl><div><dt>Published</dt><dd>{event.published_at}</dd></div><div><dt>Effective</dt><dd>{event.effective_at}</dd></div><div><dt>Document</dt><dd>{event.source_document_id}</dd></div></dl></div>
            <div className="policy-detail-grid"><PolicyDetails event={event} /></div>
            {event.details.kind === "advanced_computing_export_rule" && <nav className="policy-company-links" aria-label={`${event.title} connected companies`}><span>Connected companies</span>{event.details.related_company_tickers.map((ticker) => { const slug = releasedCompanySlugs.get(ticker); return slug ? <a href={`/companies/${slug}`} key={ticker}>{ticker} →</a> : null; })}</nav>}
            <footer><a href={event.source_url} target="_blank" rel="noreferrer">Official source ↗</a><code>{event.source_sha256}</code></footer>
          </article>)}
        </div>
        <p className="data-note">{policyEventCatalog.methodology}</p>
      </section>
      <section className="earnings-boundary page-shell"><div><p className="terminal-eyebrow">Publication boundary</p><h2>Affected scope is not predicted impact.</h2></div><div>{policyEventCatalog.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}</div></section>
      <footer className="catalog-footer market-catalog-footer"><div><strong>Scope / {policyEventCatalog.release_id}</strong><span>Federal Reserve · SEC · Federal Register</span><code>{policyEventCatalog.manifest_hash}</code></div><div><p>Retrieved {policyEventCatalog.retrieved_at.replace("T", " ").replace("Z", " UTC")}</p><p>{policyEventCatalog.scope}</p></div><p>Research data only. No policy forecast, price prediction, trade recommendation, or personalized investment advice.</p></footer>
    </main>
  );
}

export function EarningsPage() {
  return (
    <main className="data-app earnings-page">
      <SiteNav active="intelligence" action={{ label: "Verify a claim", href: "/agent" }} />
      <section className="data-hero earnings-hero page-shell">
        <div><p className="terminal-eyebrow">Intelligence / reported earnings / SEC</p><h1>Reported results. Nothing invented.</h1><p>Exact quarterly revenue and diluted EPS from one frozen SEC Company Facts release, with comparable year-over-year inputs from the same filing accession.</p><div className="scope-pills"><span><i /> {earningsCatalog.companies.map((company) => company.ticker).join(" + ")}</span><span>Filed through {readableDate(earningsCatalog.observed_at.slice(0, 10))}</span></div></div>
      </section>
      <nav className="market-subnav page-shell" aria-label="Intelligence sections"><a href="/intelligence">All intelligence</a><a className="active" href="/intelligence/earnings">Earnings</a><a href="/intelligence/policy">Policy</a><a href="/intelligence/releases">Release operations</a></nav>
      <section className="earnings-company-grid page-shell" aria-labelledby="earnings-release-title">
        <div className="data-section-head"><div><p className="terminal-eyebrow">Frozen SEC release</p><h2 id="earnings-release-title">Latest comparable quarters</h2></div><span className="release-badge">Reported · 10-Q</span></div>
        <div className="earnings-card-grid">
          {earningsCatalog.companies.map((company) => <article className="earnings-card" key={company.ticker}>
            <header><div><strong>{company.ticker}</strong><span>{company.name}</span></div><b>FY{company.fiscal_year} {company.fiscal_period}</b></header>
            <div className="earnings-metrics"><div><span>Revenue</span><strong>{money(company.revenue.value)}</strong><b>{directionalPercent(company.revenue.yoy_change_pct)} YoY</b></div><div><span>Diluted EPS</span><strong>${company.diluted_eps.value.toFixed(2)}</strong><b>{directionalPercent(company.diluted_eps.yoy_change_pct)} YoY</b></div></div>
            <dl><div><dt>Period</dt><dd>{company.period_start} → {company.period_end}</dd></div><div><dt>Filed</dt><dd>{company.filed_at}</dd></div><div><dt>Accession</dt><dd>{company.accession}</dd></div></dl>
            <footer><a href={`/companies/${company.slug}`}>Company →</a><a href={company.filing_url} target="_blank" rel="noreferrer">SEC filing ↗</a><a href={company.companyfacts_url} target="_blank" rel="noreferrer">Company Facts ↗</a></footer>
          </article>)}
        </div>
        <p className="data-note">{earningsCatalog.methodology}</p>
      </section>
      <section className="earnings-boundary page-shell"><div><p className="terminal-eyebrow">Publication boundary</p><h2>Reported facts, not an earnings call.</h2></div><div>{earningsCatalog.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}</div></section>
      <footer className="catalog-footer market-catalog-footer"><div><strong>Scope / {earningsCatalog.release_id}</strong><span>SEC Company Facts · frozen</span><code>{earningsCatalog.manifest_hash}</code></div><div><p>Source retrieved {earningsCatalog.source_retrieved_at.replace("T", " ").replace("Z", " UTC")}</p><p>{earningsCatalog.scope}</p></div><p>Research data only. No estimates, forecasts, price predictions, trade recommendations, or personalized investment advice.</p></footer>
    </main>
  );
}
