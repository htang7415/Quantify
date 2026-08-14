import { SiteNav } from "./SiteNav";
import { buildCompanyOwnership, tickerSlug } from "./companies/ownership";
import { displayName, holdingChangeText, money, quarter, readableDate, sentenceCase } from "./format";
import { CatalogFooter } from "./investors/InvestorPages";
import { investorCatalog } from "./investors/catalog";
import { macroFreshness } from "./macro/catalog";
import { ratesFreshness } from "./rates/catalog";
import { releaseFor } from "./releases/catalog";
import { ventureCatalog } from "./venture/catalog";

const companies = buildCompanyOwnership(investorCatalog);
const marketRelease = releaseFor("markets");
const eventRelease = releaseFor("events");
const earningsRelease = releaseFor("earnings");
const policyRelease = releaseFor("policy");
const treasuryState = ratesFreshness();
const macroState = macroFreshness();
const availableIntelligence = [
  earningsRelease.status === "available" ? "Earnings" : null,
  policyRelease.status === "available" ? "Policy" : null
].filter((label): label is string => label !== null);

export function OverviewPage() {
  const availableManagers = investorCatalog.managers.filter((manager) => manager.status === "available");
  const disclosedValue = availableManagers.reduce(
    (total, manager) => total + (manager.disclosed_portfolio_value_usd ?? 0),
    0
  );
  const activity = availableManagers
    .flatMap((manager) => manager.changes
      .filter((holding) => holding.change !== "unchanged")
      .map((holding) => ({ manager, holding })))
    .sort((left, right) => right.holding.value_usd - left.holding.value_usd)
    .slice(0, 6);
  const focusCompany = companies[0];

  return (
    <main className="data-app overview-page overview-page-redesign">
      <SiteNav active="overview" action={{ label: "Verify a claim", href: "/agent" }} />

      <section className="overview-hero overview-hero-redesign">
        <div className="overview-hero-copy">
          <p className="terminal-eyebrow">Public-company research · released data only</p>
          <h1><span className="overview-headline-line">See the market.</span>{" "}<span className="overview-headline-line">Keep the evidence</span>{" "}<span className="overview-headline-line">in view.</span></h1>
          <p>
            Follow reported capital, open the companies behind it, and connect official market context without losing the source or scope.
          </p>
          <div className="overview-actions">
            <a className="button button-dark" href="/investors">Explore investors</a>
            <a className="button button-light" href="/companies">Research companies</a>
          </div>
          <div className="scope-pills" aria-label="Overview release scope">
            <span><i /> {quarter(investorCatalog.report_period)} 13F release</span>
            <span>Public · No sign-in</span>
          </div>
        </div>

        <aside className="overview-release-card" aria-label="Current release snapshot">
          <div className="overview-release-card-head">
            <span>Current released view</span>
            <b><i /> Public</b>
          </div>
          <div className="overview-release-value">
            <strong>{money(disclosedValue)}</strong>
            <span>Tracked disclosed value</span>
          </div>
          <div className="overview-release-metrics">
            <div><strong>{availableManagers.length}</strong><span>Reporting managers</span></div>
            <div><strong>{companies.length}</strong><span>Mapped companies</span></div>
          </div>
          <div className="overview-release-card-foot">
            <span>Source fresh through</span>
            <strong>{readableDate(investorCatalog.source_fresh_through)}</strong>
          </div>
        </aside>
      </section>

      <nav className="overview-lens-strip page-shell" aria-label="Research sections">
        <a href="/investors"><span>01</span><strong>Investors</strong><i>Public holdings and venture relationships →</i></a>
        <a href="/companies"><span>02</span><strong>Companies</strong><i>Reported company positions →</i></a>
        <a href="/markets"><span>03</span><strong>Markets</strong><i>Macro, rates, and ETFs →</i></a>
        <a href="/intelligence"><span>04</span><strong>Intelligence</strong><i>Earnings and policy →</i></a>
      </nav>

      <section className="overview-capital page-shell" aria-labelledby="overview-capital-title">
        <div className="overview-section-intro">
          <p className="terminal-eyebrow">Start with capital</p>
          <h2 id="overview-capital-title">What changed in reported portfolios.</h2>
          <p>Latest normalized position changes across the active 13F release, ordered by disclosed position value.</p>
        </div>

        <div className="overview-capital-grid">
          <article className="overview-activity-panel">
            <div className="overview-panel-head">
              <h3>Latest released changes</h3>
              <a href="/investors">All managers →</a>
            </div>
            <div className="overview-activity-list">
              {activity.map(({ manager, holding }) => (
                <a href={holding.ticker ? `/companies/${tickerSlug(holding.ticker)}` : `/investors/${manager.slug}`} key={`${manager.slug}-${holding.security_id}`}>
                  <strong>{holding.ticker ?? holding.cusip}<span>{displayName(holding.issuer)}</span></strong>
                  <span>{displayName(manager.firm)}</span>
                  <b className={holding.change === "new" || holding.change === "added" ? "positive" : "negative"}>
                    {sentenceCase(holding.change)} · {holdingChangeText(holding)}
                  </b>
                  <i>{money(holding.value_usd)}</i>
                </a>
              ))}
            </div>
            <p className="data-note">Reported share-count changes between compatible filings. Not observed trades.</p>
          </article>

          <article className="overview-focus-card">
            <div className="overview-focus-label"><span>Largest mapped disclosed position</span><b>{quarter(investorCatalog.report_period)}</b></div>
            <div className="overview-focus-company">
              <strong>{focusCompany.ticker}</strong>
              <h3>{displayName(focusCompany.issuer)}</h3>
              <p>{money(focusCompany.tracked_disclosed_value_usd)} across {focusCompany.reporting_manager_count} tracked reporting managers.</p>
            </div>
            <div className="overview-focus-managers">
              {focusCompany.positions.slice(0, 3).map(({ manager, holding }) => (
                <a href={`/investors/${manager.slug}`} key={manager.slug}>
                  <span>{displayName(manager.firm)}</span>
                  <strong>{money(holding.value_usd)}</strong>
                </a>
              ))}
            </div>
            <a className="overview-focus-action" href={`/companies/${focusCompany.slug}`}>Open {focusCompany.ticker} research →</a>
          </article>
        </div>
      </section>

      <section className="overview-release-section" aria-labelledby="overview-release-title">
        <div className="page-shell overview-release-layout">
          <div className="overview-release-intro">
            <p className="terminal-eyebrow">Know the boundary</p>
            <h2 id="overview-release-title">Active releases</h2>
            <p>Use what has passed release controls. Unreleased layers stay visibly blank.</p>
            <a href="/intelligence/releases">View release operations →</a>
          </div>
          <div className="overview-release-list" aria-label="Released research coverage">
            <a href="/investors/venture">
              <span>Venture capital</span>
              <strong>{ventureCatalog.firms.length} firms · {ventureCatalog.firms.reduce((sum, firm) => sum + firm.tracked_relationship_count, 0)} tracked relationships</strong>
              <b>Open venture →</b>
            </a>
            <a href="/markets">
              <span>Market context</span>
              <strong>Macro · {sentenceCase(macroState)}</strong>
              <strong>Rates · {sentenceCase(treasuryState)}</strong>
              <b>Open markets →</b>
            </a>
            <a href="/intelligence">
              <span>Official intelligence</span>
              <strong>{availableIntelligence.length ? availableIntelligence.join(" · ") : "Release required"}</strong>
              <b>Open intelligence →</b>
            </a>
            <div>
              <span>Not released</span>
              <strong>Continuous prices · {marketRelease.status === "available" ? "Available" : "Release required"}</strong>
              <strong>Narrative events · {eventRelease.status === "available" ? "Available" : "Release required"}</strong>
              <b>Explicitly unavailable</b>
            </div>
          </div>
        </div>
      </section>

      <section className="overview-verify-band page-shell">
        <div>
          <p className="terminal-eyebrow">Research referee</p>
          <h2>Have a company-analysis claim?</h2>
          <p>Check it against a declared evidence release and receive a deterministic verdict.</p>
        </div>
        <a className="button button-dark" href="/agent">Verify a claim →</a>
      </section>

      <CatalogFooter />
    </main>
  );
}
