import { SiteNav } from "./SiteNav";
import { buildCompanyOwnership, tickerSlug } from "./companies/ownership";
import { displayName, holdingChangeText, money, quarter, readableDate, sentenceCase } from "./format";
import { CatalogFooter } from "./investors/InvestorPages";
import { investorCatalog } from "./investors/catalog";
import { blsMacroCatalog, macroFreshness, macroMetric } from "./macro/catalog";
import { rate, ratesFreshness, treasuryRatesCatalog } from "./rates/catalog";
import { releaseFor } from "./releases/catalog";

const companies = buildCompanyOwnership(investorCatalog);
const marketRelease = releaseFor("markets");
const eventRelease = releaseFor("events");
const ratesRelease = releaseFor("rates");
const treasuryState = ratesFreshness();
const macroState = macroFreshness();

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

  return (
    <main className="data-app overview-page">
      <SiteNav active="overview" action={{ label: "Verify a claim", href: "/agent" }} />
      <section className="overview-hero">
        <div>
          <p className="terminal-eyebrow">Research intelligence · released data only</p>
          <h1>See where capital is.<br /><span>Understand the evidence.</span></h1>
          <p>
            Reported positions, company exposure, and official market context—connected in one source-visible research surface.
          </p>
          <div className="overview-actions"><a className="button button-dark" href="/investors">Explore investors</a><a className="button button-light" href="/markets">View markets</a></div>
          <div className="scope-pills" aria-label="Overview release scope">
            <span><i /> {quarter(investorCatalog.report_period)} 13F release</span>
            <span>Public · No sign-in</span>
          </div>
        </div>
        <div className="overview-command" aria-label="Quantify intelligence model">
          <p>Available now</p>
          <strong>Every released layer, one click away.</strong>
          <a href="/investors"><span>Investors</span><b>Open →</b></a>
          <a href="/companies"><span>Companies</span><b>Open →</b></a>
          <a href="/markets/macro"><span>BLS macro · {blsMacroCatalog.observed_period}</span><b className={macroState === "stale" ? "pending" : ""}>{sentenceCase(macroState)} · CPI {macroMetric("headline_cpi_yoy").value_pct.toFixed(1)}%</b></a>
          <a href="/markets/rates"><span>Treasury rates · {treasuryRatesCatalog.observed_at.slice(0, 10)}</span><b className={treasuryState === "stale" ? "pending" : ""}>{ratesRelease.status === "available" ? `${sentenceCase(treasuryState)} · 10Y ${rate("10Y").toFixed(2)}%` : "Release required"}</b></a>
          <div><span>Markets + crypto prices</span><b className="pending">{marketRelease.status === "available" ? "Available" : "Release required"}</b></div>
          <div><span>Intelligence</span><b className="pending">{eventRelease.status === "available" ? "Available" : "Release required"}</b></div>
        </div>
      </section>

      <section className="snapshot-ribbon" aria-label="Current released snapshot">
        <div><span>Reporting managers</span><strong>{availableManagers.length}</strong></div>
        <div><span>Mapped companies</span><strong>{companies.length}</strong></div>
        <div><span>Tracked disclosed value</span><strong>{money(disclosedValue)}</strong></div>
        <div><span>Source fresh through</span><strong>{readableDate(investorCatalog.source_fresh_through)}</strong></div>
      </section>

      <section className="overview-grid page-shell">
        <article className="overview-module-card overview-module-wide">
          <div className="data-section-head">
            <div><p className="terminal-eyebrow">Reported position changes</p><h2>Latest changes</h2></div>
            <a href="/investors">All managers →</a>
          </div>
          <div className="activity-list">
            {activity.map(({ manager, holding }) => (
              <a href={holding.ticker ? `/companies/${tickerSlug(holding.ticker)}` : `/investors/${manager.slug}`} key={`${manager.slug}-${holding.security_id}`}>
                <strong>{holding.ticker ?? holding.cusip}<span>{displayName(holding.issuer)}</span></strong>
                <span>{displayName(manager.firm)}</span>
                <b className={holding.change === "new" || holding.change === "added" ? "positive" : "negative"}>
                  {sentenceCase(holding.change)} · {holdingChangeText(holding)}
                </b>
                <i>{money(holding.value_usd)} disclosed</i>
              </a>
            ))}
          </div>
          <p className="data-note">Changes compare normalized reported share counts between compatible 13F releases. They are not trades observed in real time.</p>
        </article>

        <article className="overview-module-card">
          <div className="data-section-head">
            <div><p className="terminal-eyebrow">Companies</p><h2>Largest positions</h2></div>
            <a href="/companies">Explore →</a>
          </div>
          <div className="company-rank">
            {companies.slice(0, 5).map((company, index) => (
              <a href={`/companies/${company.slug}`} key={company.slug}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{company.ticker}<i>{displayName(company.issuer)}</i></strong>
                <b>{money(company.tracked_disclosed_value_usd)}<i>{company.reporting_manager_count} managers</i></b>
              </a>
            ))}
          </div>
        </article>

        <article className="overview-module-card release-status-card">
          <div className="data-section-head">
            <div><p className="terminal-eyebrow">Market context</p><h2>Active releases</h2></div>
            <a href="/markets">Open →</a>
          </div>
          <p>BLS macro observations, Treasury rates, and delayed filed ETF flows are active. Broad markets and continuous cryptocurrency prices stay blank pending their own approved releases.</p>
          <div className="release-path" aria-label="Market release path">
            <span>Macro · {macroState}</span><span>Rates · {treasuryState}</span><span>ETF flows · released</span><span>ETF holdings · released</span><span>Crypto ETP · released</span>
          </div>
        </article>
      </section>
      <CatalogFooter />
    </main>
  );
}
