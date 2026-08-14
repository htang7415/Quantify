import { SiteNav } from "../SiteNav";
import { cryptoExposureCatalog } from "../crypto/catalog";
import { money, quarter, readableDate } from "../format";
import { blsMacroCatalog, macroFreshness, macroMetric } from "../macro/catalog";
import { rate, ratesFreshness, treasuryRatesCatalog } from "../rates/catalog";
import { releaseFor } from "../releases/catalog";

const marketRelease = releaseFor("markets");
const macroRelease = releaseFor("macro");
const cryptoRelease = releaseFor("crypto");
const ratesRelease = releaseFor("rates");
const treasuryState = ratesFreshness();
const macroState = macroFreshness();

const sections = [
  { label: "Macro", status: `${macroState === "current" ? "Current" : "Stale"} release`, available: true },
  { label: "Rates", status: `${treasuryState === "current" ? "Current" : "Stale"} release`, available: true },
  { label: "ETFs", status: "Release required", available: false },
  { label: "Sectors", status: "Release required", available: false },
  { label: "Crypto", status: "ETP exposure available", available: true },
  { label: "Commodities", status: "Release required", available: false }
];

function MarketNav() {
  return <SiteNav active="markets" action={{ label: "Verify a claim", href: "/agent" }} />;
}

function MarketFooter() {
  return <footer className="catalog-footer market-catalog-footer"><div><strong>Market data boundary</strong><span>Official BLS macro and Treasury rates are independently released.</span></div><div><p>{marketRelease.limitations[0]} {cryptoRelease.limitations[0]}</p></div><p>Research data only. No price predictions, trade recommendations, or personalized investment advice.</p></footer>;
}

export function MarketsPage() {
  return (
    <main className="data-app markets-page">
      <MarketNav />
      <section className="data-hero market-data-hero page-shell">
        <div><p className="terminal-eyebrow">Markets / release-governed</p><h1>Context without the noise.</h1><p>Macro, rates, ETFs, sectors, crypto, and commodities share one source-visible market surface. Official BLS observations and Treasury rates are active bounded layers.</p><div className="scope-pills"><span><i /> MACRO + RATES AVAILABLE</span><span>BROADER MARKET RELEASE PENDING</span></div></div>
        <a className="rates-preview-panel" href="/markets/rates"><span>U.S. Treasury · {readableDate(treasuryRatesCatalog.observed_at.slice(0, 10))} · {treasuryState}</span><div><b>2Y<i>{rate("2Y").toFixed(2)}%</i></b><b>10Y<i>{rate("10Y").toFixed(2)}%</i></b><b>30Y<i>{rate("30Y").toFixed(2)}%</i></b></div><strong>Open yield curve →</strong></a>
      </section>
      <nav className="market-subnav page-shell" aria-label="Market sections">
        {sections.map((section) => <a className={section.available ? "crypto-link" : ""} href={section.label === "Macro" ? "/markets/macro" : section.label === "Crypto" ? "/markets/crypto" : section.label === "Rates" ? "/markets/rates" : `/markets#${section.label.toLowerCase()}`} key={section.label}>{section.label}</a>)}
      </nav>
      <section className="release-grid page-shell" aria-labelledby="market-release-title">
        <div className="data-section-head"><div><p className="terminal-eyebrow">Release status</p><h2 id="market-release-title">Six bounded market layers</h2></div></div>
        <div className="market-layer-grid">
          {sections.map((section) => <article className={section.available ? "market-layer-available" : ""} id={section.label.toLowerCase()} key={section.label}><span>{section.label === "Macro" ? `${macroMetric("headline_cpi_yoy").value_pct.toFixed(1)}%` : section.label === "Rates" ? `${rate("10Y").toFixed(2)}%` : section.label === "Crypto" ? "13F" : "—"}</span><h3>{section.label}</h3><p>{section.status}</p><i>{section.label === "Macro" ? macroRelease.release_id : section.label === "Rates" ? ratesRelease.release_id : section.label === "Crypto" ? releaseFor("crypto_exposure").release_id : "No values published"}</i></article>)}
        </div>
      </section>
      <section className="methodology-panel page-shell"><p className="terminal-eyebrow">Publication path</p><div className="methodology-steps"><span><b>01</b>Approved source</span><span><b>02</b>Exact methodology</span><span><b>03</b>Freshness + correction</span><span><b>04</b>Immutable release</span></div></section>
      <MarketFooter />
    </main>
  );
}

function macroPeriod(period: string): string {
  return new Date(`${period}-01T00:00:00Z`).toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
}

export function MacroPage() {
  const freshness = macroFreshness();
  return (
    <main className="data-app macro-page">
      <MarketNav />
      <section className="data-hero macro-hero page-shell">
        <div><p className="terminal-eyebrow">Markets / macro / official release</p><h1>Three signals. Exact scope.</h1><p>Headline inflation, core inflation, and unemployment from a frozen U.S. Bureau of Labor Statistics release—dated, reproducible, and without a forecast.</p><div className="scope-pills"><span><i /> {freshness.toUpperCase()}</span><span>PERIOD {macroPeriod(blsMacroCatalog.observed_period).toUpperCase()}</span></div></div>
        <a className="source-button" href={blsMacroCatalog.terms_url} target="_blank" rel="noreferrer">BLS data terms ↗</a>
      </section>
      <nav className="market-subnav page-shell" aria-label="Market sections"><a href="/markets">All markets</a><a className="active" href="/markets/macro">Macro</a><a href="/markets/rates">Rates</a><a href="/markets/crypto">Crypto</a></nav>
      <section className="macro-metric-grid page-shell" aria-labelledby="macro-metrics-title">
        <div className="data-section-head"><div><p className="terminal-eyebrow">BLS observations</p><h2 id="macro-metrics-title">Current release</h2></div><span className={`release-badge freshness-${freshness}`}>{freshness}</span></div>
        <div className="macro-card-grid">
          {blsMacroCatalog.observations.map((metric) => <article className="macro-metric-card" key={metric.metric_id}>
            <div><span>{metric.label}</span><a href={metric.source_url} target="_blank" rel="noreferrer">{metric.series_id} ↗</a></div>
            <strong>{metric.value_pct.toFixed(1)}%</strong>
            <p>{metric.derivation === "year_over_year_percent_change" ? "Year over year · NSA" : "Published rate · SA"}</p>
            <footer><span>{macroPeriod(metric.period)}</span><b className={metric.change_pp > 0 ? "macro-change-up" : metric.change_pp < 0 ? "macro-change-down" : ""}>{metric.change_pp > 0 ? "↑" : metric.change_pp < 0 ? "↓" : "→"} {Math.abs(metric.change_pp).toFixed(1)} pp vs {macroPeriod(metric.previous_period)}</b></footer>
          </article>)}
        </div>
      </section>
      <section className="macro-methodology page-shell" aria-labelledby="macro-method-title">
        <div><p className="terminal-eyebrow">Calculation trace</p><h2 id="macro-method-title">No hidden inputs.</h2><p>{blsMacroCatalog.methodology}</p></div>
        <div className="macro-input-list">
          {blsMacroCatalog.observations.map((metric) => <article key={metric.metric_id}><strong>{metric.label}</strong><span>{metric.inputs.map((item) => `${item.period} · ${item.value}`).join("  /  ")}</span></article>)}
        </div>
        <p className="bls-disclaimer">{blsMacroCatalog.disclaimer}</p>
      </section>
      <footer className="catalog-footer market-catalog-footer"><div><strong>Scope / {blsMacroCatalog.release_id}</strong><span>U.S. Bureau of Labor Statistics</span><code>{blsMacroCatalog.manifest_hash}</code></div><div><p>Retrieved {blsMacroCatalog.retrieved_at.replace("T", " ").replace("Z", " UTC")}</p><p>Fresh until {blsMacroCatalog.fresh_until.replace("T", " ").replace("Z", " UTC")}</p>{blsMacroCatalog.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}</div><p>Research data only. No macro forecast, price prediction, trade recommendation, or personalized investment advice.</p></footer>
    </main>
  );
}

export function RatesPage() {
  const freshness = ratesFreshness();
  const spread = treasuryRatesCatalog.spreads.find((item) => item.name === "2s10s");
  const maxYield = Math.max(...treasuryRatesCatalog.curve.map((point) => point.yield_pct));
  return (
    <main className="data-app rates-page">
      <MarketNav />
      <section className="data-hero rates-hero page-shell">
        <div><p className="terminal-eyebrow">Markets / rates / official release</p><h1>U.S. Treasury curve.</h1><p>Exact daily par yields published by the U.S. Treasury, with one deterministic 2s10s calculation and no forecast.</p><div className="scope-pills"><span><i /> {freshness.toUpperCase()}</span><span>OBSERVED {readableDate(treasuryRatesCatalog.observed_at.slice(0, 10)).toUpperCase()}</span></div></div>
        <a className="source-button" href={treasuryRatesCatalog.source_url} target="_blank" rel="noreferrer">U.S. Treasury source ↗</a>
      </section>
      <nav className="market-subnav page-shell" aria-label="Market sections"><a href="/markets">All markets</a><a href="/markets/macro">Macro</a><a className="active" href="/markets/rates">Rates</a><a href="/markets/crypto">Crypto</a></nav>
      <section className="rates-metric-ribbon page-shell" aria-label="Key Treasury rates">
        <div><span>2 year</span><strong>{rate("2Y").toFixed(2)}%</strong></div>
        <div><span>10 year</span><strong>{rate("10Y").toFixed(2)}%</strong></div>
        <div><span>30 year</span><strong>{rate("30Y").toFixed(2)}%</strong></div>
        <div><span>2s10s</span><strong>{spread ? `${spread.value_pp > 0 ? "+" : ""}${spread.value_pp.toFixed(2)} pp` : "—"}</strong></div>
      </section>
      <section className="yield-curve-section page-shell" aria-labelledby="yield-curve-title">
        <div className="data-section-head"><div><p className="terminal-eyebrow">Official par yields</p><h2 id="yield-curve-title">Yield curve</h2></div><span className={`release-badge freshness-${freshness}`}>{freshness}</span></div>
        <div className="yield-curve-chart" role="img" aria-label={`U.S. Treasury yield curve observed ${treasuryRatesCatalog.observed_at.slice(0, 10)}`}>
          {treasuryRatesCatalog.curve.map((point) => <div key={point.maturity}><span><i style={{ height: `${(point.yield_pct / maxYield) * 100}%` }} /></span><b>{point.yield_pct.toFixed(2)}%</b><small>{point.maturity}</small></div>)}
        </div>
        <div className="rates-methodology"><div><span>Observed</span><strong>{treasuryRatesCatalog.observed_at.slice(0, 10)}</strong></div><div><span>Published</span><strong>{treasuryRatesCatalog.published_at.replace("T", " ").replace("Z", " UTC")}</strong></div><div><span>Fresh until</span><strong>{treasuryRatesCatalog.fresh_until.replace("T", " ").replace("Z", " UTC")}</strong></div></div>
        <p className="data-note">{treasuryRatesCatalog.methodology}</p>
      </section>
      <footer className="catalog-footer market-catalog-footer"><div><strong>Scope / {treasuryRatesCatalog.release_id}</strong><span>U.S. Department of the Treasury</span><code>{treasuryRatesCatalog.manifest_hash}</code></div><div>{treasuryRatesCatalog.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}</div><p>Research data only. No rate forecast, price prediction, trade recommendation, or personalized investment advice.</p></footer>
    </main>
  );
}

export function CryptoPage() {
  const positions = cryptoExposureCatalog.assets.flatMap((asset) => asset.positions.map((position) => ({ asset, position })));
  return (
    <main className="data-app crypto-page">
      <MarketNav />
      <section className="data-hero crypto-hero page-shell">
        <div><p className="terminal-eyebrow">Markets / cryptocurrency</p><h1>Crypto data, when it can be traced.</h1><p>A narrow BTC and ETH surface now connects released crypto-linked ETP positions. Continuous-market prices, flows, and network metrics remain unavailable.</p><div className="scope-pills"><span><i /> ETP EXPOSURE · {quarter(cryptoExposureCatalog.report_period)}</span><span>NO ACTIVE CRYPTO MARKET RELEASE</span></div></div>
        <div className="crypto-orbit" aria-label="Planned crypto intelligence connections"><strong>BTC · ETH</strong><span>Market</span><span>Funds</span><span>Network</span><span>Policy</span></div>
      </section>
      <nav className="market-subnav page-shell" aria-label="Market sections"><a href="/markets">All markets</a><a href="/markets/macro">Macro</a><a href="/markets/rates">Rates</a><a className="active" href="/markets/crypto">Crypto</a></nav>
      <section className="crypto-assets page-shell" aria-labelledby="crypto-assets-title">
        <div className="data-section-head"><div><p className="terminal-eyebrow">Initial scope</p><h2 id="crypto-assets-title">BTC + ETH</h2></div><span className="release-badge">ETP EXPOSURE RELEASED</span></div>
        <div className="crypto-card-grid">
          {cryptoExposureCatalog.assets.map((asset) => (
            <article className="crypto-asset-card" key={asset.symbol}>
              <div><strong>{asset.symbol}</strong><span>{asset.name}</span></div><i>Native asset · {asset.network}</i>
              <dl><div><dt>Spot price</dt><dd>—</dd></div><div><dt>Reported ETP value</dt><dd>{money(asset.reported_etp_value_usd)}</dd></div><div><dt>Managers</dt><dd>{asset.reporting_manager_count}</dd></div></dl>
              <p>{asset.positions.length ? `${asset.positions.length} released ETP position · market data unavailable.` : "No ETP position in the tracked manager release · market data unavailable."}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="crypto-position-section page-shell" aria-labelledby="crypto-positions-title">
        <div className="module-head"><div><span>01</span><h2 id="crypto-positions-title">Reported ETP exposure</h2></div><p>Tracked managers · SEC 13F · not fund flows</p></div>
        {positions.length ? <div className="holdings-scroll"><table className="holdings-table crypto-position-table">
          <thead><tr><th>Asset / ETP</th><th>Reporting manager</th><th>Value</th><th>Portfolio weight</th><th>Shares</th><th>QoQ shares</th><th>Sources</th></tr></thead>
          <tbody>{positions.map(({ asset, position }) => <tr key={`${asset.asset_id}-${position.manager_slug}-${position.cusip}`}>
            <td><strong>{asset.symbol} / {position.fund_ticker}</strong><span>{position.fund_name}</span></td>
            <td><a href={`/investors/${position.manager_slug}`}><strong>{position.manager_firm}</strong><span>{position.reporting_manager_name}</span></a></td>
            <td>{money(position.value_usd)}</td>
            <td>{position.portfolio_weight_pct.toFixed(2)}%</td>
            <td>{Math.round(position.shares).toLocaleString("en-US")}</td>
            <td>{position.change.toUpperCase()}{position.share_delta_pct === null ? "" : ` · ${position.share_delta_pct > 0 ? "+" : ""}${position.share_delta_pct.toFixed(1)}%`}</td>
            <td><a className="table-source-link" href={position.filing_source_url} target="_blank" rel="noreferrer">13F ↗</a><a className="table-source-link" href={position.identity_source_url} target="_blank" rel="noreferrer">Identity ↗</a></td>
          </tr>)}</tbody>
        </table></div> : <p className="empty-filter">No crypto-linked ETP positions appear in the tracked manager release.</p>}
        <p className="company-scope-note">An ETP position is a reported security holding. It is not direct token ownership, an ETF flow, a wallet attribution, or evidence of investment intent.</p>
      </section>
      <section className="crypto-controls page-shell"><div><p className="terminal-eyebrow">Crypto-specific controls</p><h2>Continuous markets need a stricter contract.</h2></div><div className="control-list"><span>Stable asset + network identity</span><span>Composite price methodology</span><span>Separate continuous-market freshness</span><span>Wrapped and bridged asset policy</span><span>Chain finality and revision handling</span><span>ETF flows ≠ token ownership</span></div></section>
      <MarketFooter />
    </main>
  );
}
