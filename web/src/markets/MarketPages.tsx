import { SectionConnections } from "../SectionConnections";
import { DataCard, ResearchFooter, ResearchHero, ResearchSubnav, TableScroll, UnavailableState } from "../ResearchUI";
import { SiteNav } from "../SiteNav";
import { publicBrandText } from "../brand";
import { cryptoExposureCatalog } from "../crypto/catalog";
import { etfFlowCatalog, etfFreshness } from "../etfs/catalog";
import { etfHoldingsCatalog, etfHoldingsFund } from "../etfs/holdingsCatalog";
import { displayName, money, quarter, readableDate, sentenceCase } from "../format";
import { blsMacroCatalog, macroFreshness, macroMetric } from "../macro/catalog";
import { rate, ratesFreshness, treasuryRatesCatalog } from "../rates/catalog";
import { releaseFor } from "../releases/catalog";

const marketRelease = releaseFor("markets");
const macroRelease = releaseFor("macro");
const cryptoRelease = releaseFor("crypto");
const ratesRelease = releaseFor("rates");
const etfFlowRelease = releaseFor("etf_flows");
const etfHoldingsRelease = releaseFor("etf_holdings");
const cryptoExposureRelease = releaseFor("crypto_exposure");
const treasuryState = ratesFreshness();
const macroState = macroFreshness();
const etfState = etfFreshness();

const sections = [
  { label: "Macro", status: macroRelease.status === "available" ? `${sentenceCase(macroState)} release` : "Release required", available: macroRelease.status === "available" },
  { label: "Rates", status: ratesRelease.status === "available" ? `${sentenceCase(treasuryState)} release` : "Release required", available: ratesRelease.status === "available" },
  { label: "ETFs", status: etfFlowRelease.status === "available" && etfHoldingsRelease.status === "available" ? `${sentenceCase(etfState)} filed flows + holdings` : "Complete release required", available: etfFlowRelease.status === "available" && etfHoldingsRelease.status === "available" },
  { label: "Sectors", status: "Release required", available: false },
  { label: "Crypto", status: cryptoExposureRelease.status === "available" ? "Reported ETP exposure available" : "Release required", available: cryptoExposureRelease.status === "available" },
  { label: "Commodities", status: "Release required", available: false }
];

function sectionIdentity(label: string): string {
  if (label === "Macro") return macroRelease.release_id ?? "Not released";
  if (label === "Rates") return ratesRelease.release_id ?? "Not released";
  if (label === "Crypto") return cryptoExposureRelease.release_id ?? "Not released";
  if (label === "ETFs") return `${etfFlowRelease.release_id ?? "Flows not released"} · ${etfHoldingsRelease.release_id ?? "Holdings not released"}`;
  return "No values published";
}

function MarketNav() {
  return <SiteNav active="markets" action={{ label: "Verify a claim", href: "/agent" }} subnav={<ResearchSubnav group="research" active="markets" />} />;
}

function MarketSectionNav({ active }: { active: "overview" | "macro" | "rates" | "etfs" | "crypto" }) {
  return <ResearchSubnav group="markets" active={active} />;
}

function sectionHref(label: string): string | undefined {
  if (label === "Macro") return "/markets/macro";
  if (label === "Rates") return "/markets/rates";
  if (label === "ETFs") return "/markets/etfs";
  if (label === "Crypto") return "/markets/crypto";
  return undefined;
}

function sectionPrimary(label: string): string {
  if (label === "Macro") return `${macroMetric("headline_cpi_yoy").value_pct.toFixed(1)}%`;
  if (label === "Rates") return `${rate("10Y").toFixed(2)}%`;
  if (label === "Crypto") return "13F";
  if (label === "ETFs") return "N-PORT";
  return "—";
}

function MarketFooter({ context = "overview" }: { context?: "overview" | "crypto" }) {
  if (context === "crypto") return <ResearchFooter
    details={[{ label: "Release ID", value: cryptoExposureCatalog.release_id }, { label: "Manifest", value: cryptoExposureCatalog.manifest_hash }, { label: "Investor release", value: cryptoExposureCatalog.investor_release_id }]}
    limitations={[...cryptoExposureCatalog.limitations, ...cryptoRelease.limitations]}
    observed={quarter(cryptoExposureCatalog.report_period)}
    source={cryptoExposureCatalog.source}
    status="ETP exposure available · Market data unavailable"
  />;
  return <ResearchFooter
    details={[{ label: "Macro release", value: macroRelease.release_id ?? "Not released" }, { label: "Rates release", value: ratesRelease.release_id ?? "Not released" }, { label: "ETF releases", value: `${etfFlowRelease.release_id ?? "Flows unavailable"} · ${etfHoldingsRelease.release_id ?? "Holdings unavailable"}` }]}
    limitations={[...marketRelease.limitations, ...cryptoRelease.limitations]}
    observed={`BLS ${macroPeriod(blsMacroCatalog.observed_period)} · Treasury ${readableDate(treasuryRatesCatalog.observed_at.slice(0, 10))} · ETF through ${readableDate(etfFlowCatalog.observed_through)}`}
    source="BLS · U.S. Treasury · SEC N-PORT"
    status="Macro, rates, and filed ETFs available · Broad market unavailable"
  />;
}

export function MarketsPage() {
  return (
    <main className="data-app markets-page">
      <MarketNav />
      <ResearchHero
        aside={<a className="rates-preview-panel" href="/markets/rates"><span>U.S. Treasury · {readableDate(treasuryRatesCatalog.observed_at.slice(0, 10))} · {treasuryState}</span><div><b>2Y<i>{rate("2Y").toFixed(2)}%</i></b><b>10Y<i>{rate("10Y").toFixed(2)}%</i></b><b>30Y<i>{rate("30Y").toFixed(2)}%</i></b></div><strong>Open yield curve →</strong></a>}
        className="market-data-hero"
        description="Official macro, rates, and filed ETF data—dated, sourced, and separated from unreleased market layers."
        eyebrow="Markets · released data"
        scope={[{ label: "Macro + rates + filed ETF data available", available: true }, { label: marketRelease.status === "available" ? "Broad market release available" : "Broad market release unavailable", available: marketRelease.status === "available" }]}
        scopeLabel="Market research scope"
        title={<>Market context.<br />Source visible.</>}
      />
      <MarketSectionNav active="overview" />
      <SectionConnections items={[
        { label: "Companies", detail: "Open filed ETF holdings by issuer", href: "/companies" },
        { label: "Investors", detail: "Trace crypto-linked manager positions", href: "/investors" },
        { label: "Intelligence", detail: "Connect official earnings and policy", href: "/intelligence" }
      ]} />
      <section className="release-grid page-shell" aria-labelledby="market-release-title">
        <div className="data-section-head"><div><p className="terminal-eyebrow">Release status</p><h2 id="market-release-title">Market releases</h2></div></div>
        <div className="market-layer-grid">
          {sections.map((section) => <DataCard href={section.available ? sectionHref(section.label) : undefined} key={section.label} label="Market data" meta={sectionIdentity(section.label)} primary={sectionPrimary(section.label)} state={section.status} title={section.label} />)}
        </div>
      </section>
      <section className="methodology-panel page-shell"><p className="terminal-eyebrow">Publication path</p><div className="methodology-steps"><span><b>01</b>Approved source</span><span><b>02</b>Exact methodology</span><span><b>03</b>Freshness + correction</span><span><b>04</b>Immutable release</span></div></section>
      <MarketFooter />
    </main>
  );
}

function signedMoney(value: number): string {
  if (value === 0) return "$0";
  return `${value > 0 ? "+" : "−"}${money(Math.abs(value))}`;
}

function monthLabel(value: string): string {
  return new Date(`${value}-01T00:00:00Z`).toLocaleDateString("en-US", { month: "short", timeZone: "UTC" });
}

export function EtfPage() {
  const freshness = etfFreshness();
  const netTotal = etfFlowCatalog.funds.reduce((total, fund) => total + fund.three_month_net_flow_usd, 0);
  return <main className="data-app etf-page">
    <MarketNav />
    <ResearchHero description={<>Three months of SEC Form N-PORT sales, reinvestments, and redemptions for {etfFlowCatalog.funds.length} funds—without substituting changes in net assets for flows.</>} eyebrow="Markets / ETFs / filed flows" scope={[{ label: sentenceCase(freshness), available: true }, `Observed through ${readableDate(etfFlowCatalog.observed_through)}`, "Delayed filing view"]} title="Filed fund flows. Exact inputs." />
    <MarketSectionNav active="etfs" />
    <section className="etf-flow-section page-shell" aria-labelledby="etf-flow-title">
      <div className="data-section-head"><div><p className="terminal-eyebrow">SEC Form N-PORT · Item B.6</p><h2 id="etf-flow-title">Three-month filed flows</h2></div><span className={`release-badge freshness-${freshness}`}>{signedMoney(netTotal)} selected universe</span></div>
      <TableScroll className="holdings-scroll" label="Filed ETF fund flows"><table className="holdings-table etf-flow-table"><thead><tr><th>Fund</th><th>Category</th><th>Oldest filed month</th><th>Middle filed month</th><th>Latest filed month</th><th>3 months</th><th>Net assets</th><th>Source</th></tr></thead><tbody>{etfFlowCatalog.funds.map((fund) => { const detail = etfHoldingsFund(fund.ticker); return <tr key={fund.fund_id}><td>{detail ? <a href={`/markets/etfs/${detail.slug}`}><strong>{fund.ticker}</strong><span>{fund.name}</span></a> : <><strong>{fund.ticker}</strong><span>{fund.name}</span></>}</td><td>{fund.category}<span>Report {readableDate(fund.report_date)} · filed {readableDate(fund.filed_date)}</span></td>{fund.monthly_flows.map((flow) => <td className={flow.net_flow_usd > 0 ? "positive" : flow.net_flow_usd < 0 ? "negative" : ""} key={flow.month}>{signedMoney(flow.net_flow_usd)}<span>{monthLabel(flow.month)}</span></td>)}<td className={fund.three_month_net_flow_usd > 0 ? "positive" : fund.three_month_net_flow_usd < 0 ? "negative" : ""}><strong>{signedMoney(fund.three_month_net_flow_usd)}</strong></td><td>{money(fund.net_assets_usd)}</td><td><a className="table-source-link" href={fund.source_url} target="_blank" rel="noreferrer">N-PORT ↗</a></td></tr>; })}</tbody></table></TableScroll>
      <p className="data-note">{etfFlowCatalog.methodology}</p>
    </section>
    <section className="etf-method page-shell"><div><p className="terminal-eyebrow">Calculation boundary</p><h2>Sales + reinvestment − redemptions.</h2></div><div>{etfFlowCatalog.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}</div></section>
    <ResearchFooter details={[{ label: "Release ID", value: etfFlowCatalog.release_id }, { label: "Manifest", value: etfFlowCatalog.manifest_hash }, { label: "Fresh until", value: etfFlowCatalog.fresh_until.replace("T", " ").replace("Z", " UTC") }]} disclaimer="Research data only. No flow forecast, price prediction, trade recommendation, or personalized investment advice." limitations={etfFlowCatalog.limitations} links={<a href={etfFlowCatalog.dataset_url}>Official SEC dataset ↗</a>} methodology={etfFlowCatalog.methodology} observed={readableDate(etfFlowCatalog.observed_through)} source={`SEC Form N-PORT · ${etfFlowCatalog.dataset_period}`} status={`${sentenceCase(freshness)} · Delayed filing view`} />
  </main>;
}

export function EtfDetailPage({ slug }: { slug: string }) {
  const fund = etfHoldingsFund(slug);
  if (!fund) return <main className="data-app"><MarketNav /><UnavailableState action={{ label: "Return to ETFs", href: "/markets/etfs" }} eyebrow="404 / ETF not released" reason="ETF detail pages exist only for funds in the current reviewed holdings release." title="No holdings release here." /></main>;
  const flow = etfFlowCatalog.funds.find((item) => item.ticker === fund.ticker);
  if (!flow) throw new Error("ETF holdings detail is missing its flow record.");
  return <main className="data-app etf-detail-page">
    <MarketNav />
    <div className="detail-shell">
      <a className="back-link" href="/markets/etfs">← All ETFs</a>
      <header className="company-detail-head etf-detail-head"><div><p className="terminal-eyebrow">ETF holdings / SEC Form N-PORT</p><h1><span>{fund.ticker}</span>{fund.name}</h1><p>Delayed filed snapshot · report {readableDate(fund.report_date)}</p></div><span className={`release-badge freshness-${etfFreshness()}`}>{sentenceCase(etfFreshness())}</span></header>
      <section className="overview-module" aria-label={`${fund.ticker} filed overview`}>
        <div className="overview-metric"><strong>{money(fund.net_assets_usd)}</strong><span>Filed net assets</span></div>
        <div className="overview-metric"><strong>{signedMoney(flow.three_month_net_flow_usd)}</strong><span>Three-month filed flow</span></div>
        <div className="overview-metric"><strong>{fund.top_ten_concentration_pct.toFixed(1)}%</strong><span>Top-ten concentration</span></div>
        <div className="overview-metric"><strong>{fund.total_holding_rows}</strong><span>Total filed holding rows</span></div>
      </section>
      <p className="company-scope-note">Libration publishes only the ten largest reviewed rows here. Total row count describes the filing; it does not mean all rows are included in this public release.</p>

      <section className="terminal-module" aria-labelledby="etf-holdings-title">
        <div className="module-head"><div><span>01</span><h2 id="etf-holdings-title">Top filed positions</h2></div><p>Filed percentage descending</p></div>
        <TableScroll className="holdings-scroll" label={`${fund.ticker} top filed positions`} stickyColumn={2}><table className="holdings-table etf-position-table"><thead><tr><th>Rank</th><th>Company</th><th>Value</th><th>Filed weight</th><th>Shares</th><th>Country</th><th>Source</th></tr></thead><tbody>{fund.holdings.map((holding) => <tr key={holding.holding_id}><td>{holding.rank.toString().padStart(2, "0")}</td><td>{holding.ticker ? <a href={`/companies/${holding.ticker.toLowerCase()}`}><strong>{holding.ticker}</strong><span>{displayName(holding.issuer_name)}</span></a> : <><strong>—</strong><span>{displayName(holding.issuer_name)} · ticker unmapped</span></>}</td><td>{money(holding.currency_value)}</td><td><strong>{holding.filed_percentage.toFixed(2)}%</strong></td><td>{Math.round(holding.balance).toLocaleString("en-US")}</td><td>{holding.investment_country}</td><td><a className="table-source-link" href={fund.source_url} target="_blank" rel="noreferrer">N-PORT ↗</a></td></tr>)}</tbody></table></TableScroll>
        <p className="data-note">{publicBrandText(etfHoldingsCatalog.methodology)}</p>
      </section>

      <section className="terminal-module" aria-labelledby="etf-comparison-title">
        <div className="module-head"><div><span>02</span><h2 id="etf-comparison-title">ETF comparison</h2></div><p>Fund-specific report dates retained</p></div>
        <TableScroll className="holdings-scroll" label="Filed ETF comparison"><table className="holdings-table etf-comparison-table"><thead><tr><th>Fund</th><th>Three-month filed flow</th><th>Top position</th><th>Top position weight</th><th>Top-ten concentration</th><th>Report date</th></tr></thead><tbody>{etfHoldingsCatalog.funds.map((item) => { const itemFlow = etfFlowCatalog.funds.find((row) => row.ticker === item.ticker); if (!itemFlow) return null; const top = item.holdings[0]; return <tr key={item.fund_id}><td><a href={`/markets/etfs/${item.slug}`}><strong>{item.ticker}</strong><span>{item.name}</span></a></td><td className={itemFlow.three_month_net_flow_usd > 0 ? "positive" : itemFlow.three_month_net_flow_usd < 0 ? "negative" : ""}>{signedMoney(itemFlow.three_month_net_flow_usd)}</td><td>{top.ticker ?? displayName(top.issuer_name)}</td><td>{top.filed_percentage.toFixed(2)}%</td><td>{item.top_ten_concentration_pct.toFixed(1)}%</td><td>{readableDate(item.report_date)}</td></tr>; })}</tbody></table></TableScroll>
      </section>

      <section className="etf-method etf-detail-boundary"><div><p className="terminal-eyebrow">Publication boundary</p><h2>Filed positions, not current exposure.</h2></div><div>{etfHoldingsCatalog.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}</div></section>
    </div>
    <ResearchFooter details={[{ label: "Release ID", value: etfHoldingsCatalog.release_id }, { label: "Manifest", value: etfHoldingsCatalog.manifest_hash }, { label: "Filed", value: readableDate(fund.filed_date) }]} disclaimer="Research data only. No current exposure estimate, flow attribution, recommendation, or personalized investment advice." limitations={etfHoldingsCatalog.limitations} links={<a href={fund.source_url} target="_blank" rel="noreferrer">Official filing ↗</a>} methodology={publicBrandText(etfHoldingsCatalog.methodology)} observed={readableDate(fund.report_date)} source={`SEC Form N-PORT · ${fund.ticker}`} status={`${sentenceCase(etfFreshness())} · Top-ten reviewed rows`} />
  </main>;
}

function macroPeriod(period: string): string {
  return new Date(`${period}-01T00:00:00Z`).toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
}

export function MacroPage() {
  const freshness = macroFreshness();
  return (
    <main className="data-app macro-page">
      <MarketNav />
      <ResearchHero aside={<a className="source-button" href={blsMacroCatalog.terms_url} target="_blank" rel="noreferrer">BLS data terms ↗</a>} className="macro-hero" description="Headline inflation, core inflation, and unemployment from a frozen U.S. Bureau of Labor Statistics release—dated, reproducible, and without a forecast." eyebrow="Markets / macro / official release" scope={[{ label: `${blsMacroCatalog.observations.length} released observations`, available: true }, `${sentenceCase(freshness)} · ${macroPeriod(blsMacroCatalog.observed_period)}`]} title="Macro signals. Exact scope." />
      <MarketSectionNav active="macro" />
      <section className="macro-metric-grid page-shell" aria-labelledby="macro-metrics-title">
      <div className="data-section-head"><div><p className="terminal-eyebrow">BLS observations</p><h2 id="macro-metrics-title">Released observations</h2></div><span className={`release-badge freshness-${freshness}`}>{sentenceCase(freshness)}</span></div>
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
        <div><p className="terminal-eyebrow">Calculation trace</p><h2 id="macro-method-title">No hidden inputs.</h2><p>{publicBrandText(blsMacroCatalog.methodology)}</p></div>
        <div className="macro-input-list">
          {blsMacroCatalog.observations.map((metric) => <article key={metric.metric_id}><strong>{metric.label}</strong><span>{metric.inputs.map((item) => `${item.period} · ${item.value}`).join("  /  ")}</span></article>)}
        </div>
        <p className="bls-disclaimer">{blsMacroCatalog.disclaimer}</p>
      </section>
      <ResearchFooter details={[{ label: "Release ID", value: blsMacroCatalog.release_id }, { label: "Manifest", value: blsMacroCatalog.manifest_hash }, { label: "Fresh until", value: blsMacroCatalog.fresh_until.replace("T", " ").replace("Z", " UTC") }]} disclaimer="Research data only. No macro forecast, price prediction, trade recommendation, or personalized investment advice." limitations={blsMacroCatalog.limitations.map((limitation) => publicBrandText(limitation))} observed={macroPeriod(blsMacroCatalog.observed_period)} source="U.S. Bureau of Labor Statistics" status={sentenceCase(freshness)} />
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
      <ResearchHero aside={<a className="source-button" href={treasuryRatesCatalog.source_url} target="_blank" rel="noreferrer">U.S. Treasury source ↗</a>} className="rates-hero" description="Exact daily par yields published by the U.S. Treasury, with one deterministic 2s10s calculation and no forecast." eyebrow="Markets / rates / official release" scope={[{ label: sentenceCase(freshness), available: true }, `Observed ${readableDate(treasuryRatesCatalog.observed_at.slice(0, 10))}`]} title="U.S. Treasury curve." />
      <MarketSectionNav active="rates" />
      <section className="rates-metric-ribbon page-shell" aria-label="Key Treasury rates">
        <div><span>2 year</span><strong>{rate("2Y").toFixed(2)}%</strong></div>
        <div><span>10 year</span><strong>{rate("10Y").toFixed(2)}%</strong></div>
        <div><span>30 year</span><strong>{rate("30Y").toFixed(2)}%</strong></div>
        <div><span>2s10s</span><strong>{spread ? `${spread.value_pp > 0 ? "+" : ""}${spread.value_pp.toFixed(2)} pp` : "—"}</strong></div>
      </section>
      <section className="yield-curve-section page-shell" aria-labelledby="yield-curve-title">
        <div className="data-section-head"><div><p className="terminal-eyebrow">Official par yields</p><h2 id="yield-curve-title">Yield curve</h2></div><span className={`release-badge freshness-${freshness}`}>{sentenceCase(freshness)}</span></div>
        <div className="yield-curve-chart" role="img" aria-label={`U.S. Treasury yield curve observed ${treasuryRatesCatalog.observed_at.slice(0, 10)}`}>
          {treasuryRatesCatalog.curve.map((point) => <div key={point.maturity}><span><i style={{ height: `${(point.yield_pct / maxYield) * 100}%` }} /></span><b>{point.yield_pct.toFixed(2)}%</b><small>{point.maturity}</small></div>)}
        </div>
        <div className="rates-methodology"><div><span>Observed</span><strong>{treasuryRatesCatalog.observed_at.slice(0, 10)}</strong></div><div><span>Published</span><strong>{treasuryRatesCatalog.published_at.replace("T", " ").replace("Z", " UTC")}</strong></div><div><span>Fresh until</span><strong>{treasuryRatesCatalog.fresh_until.replace("T", " ").replace("Z", " UTC")}</strong></div></div>
        <p className="data-note">{treasuryRatesCatalog.methodology}</p>
      </section>
      <ResearchFooter details={[{ label: "Release ID", value: treasuryRatesCatalog.release_id }, { label: "Manifest", value: treasuryRatesCatalog.manifest_hash }, { label: "Fresh until", value: treasuryRatesCatalog.fresh_until.replace("T", " ").replace("Z", " UTC") }]} disclaimer="Research data only. No rate forecast, price prediction, trade recommendation, or personalized investment advice." limitations={treasuryRatesCatalog.limitations} observed={readableDate(treasuryRatesCatalog.observed_at.slice(0, 10))} source="U.S. Department of the Treasury" status={sentenceCase(freshness)} />
    </main>
  );
}

export function CryptoPage() {
  const positions = cryptoExposureCatalog.assets.flatMap((asset) => asset.positions.map((position) => ({ asset, position })));
  return (
    <main className="data-app crypto-page">
      <MarketNav />
      <ResearchHero aside={<div className="crypto-orbit" aria-label="Planned crypto intelligence connections"><strong>BTC · ETH</strong><span>Market</span><span>Funds</span><span>Network</span><span>Policy</span></div>} className="crypto-hero" description="A narrow BTC and ETH surface connects released crypto-linked ETP positions. Continuous-market prices, flows, and network metrics remain unavailable." eyebrow="Markets / cryptocurrency" scope={[{ label: `ETP exposure · ${quarter(cryptoExposureCatalog.report_period)}`, available: true }, { label: "Crypto market data unavailable", available: false }]} title="Crypto data, when it can be traced." />
      <MarketSectionNav active="crypto" />
      <section className="crypto-assets page-shell" aria-labelledby="crypto-assets-title">
        <div className="data-section-head"><div><p className="terminal-eyebrow">Initial scope</p><h2 id="crypto-assets-title">BTC + ETH</h2></div><span className="release-badge">ETP exposure released</span></div>
        <div className="crypto-card-grid">
          {cryptoExposureCatalog.assets.map((asset) => (
            <article className="crypto-asset-card" key={asset.symbol}>
              <div><strong>{asset.symbol}</strong><span>{asset.name}</span></div><i>Native asset · {asset.network}</i>
              <dl><div><dt>Spot price</dt><dd>—</dd></div><div><dt>Reported ETP value</dt><dd>{money(asset.reported_etp_value_usd)}</dd></div><div><dt>Managers</dt><dd>{asset.reporting_manager_count}</dd></div></dl>
              <p>{asset.positions.length ? `${asset.positions.length} released ETP ${asset.positions.length === 1 ? "position" : "positions"} · market data unavailable.` : "No ETP position in the tracked manager release · market data unavailable."}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="crypto-position-section page-shell" aria-labelledby="crypto-positions-title">
        <div className="module-head"><div><span>01</span><h2 id="crypto-positions-title">Reported ETP exposure</h2></div><p>Tracked managers · SEC 13F · not fund flows</p></div>
        {positions.length ? <TableScroll className="holdings-scroll" label="Reported crypto-linked ETP exposure"><table className="holdings-table crypto-position-table">
          <thead><tr><th>Asset / ETP</th><th>Reporting manager</th><th>Value</th><th>Portfolio weight</th><th>Shares</th><th>QoQ shares</th><th>Sources</th></tr></thead>
          <tbody>{positions.map(({ asset, position }) => <tr key={`${asset.asset_id}-${position.manager_slug}-${position.cusip}`}>
            <td><strong>{asset.symbol} / {position.fund_ticker}</strong><span>{position.fund_name}</span></td>
            <td><a href={`/investors/${position.manager_slug}`}><strong>{displayName(position.manager_firm)}</strong><span>{displayName(position.reporting_manager_name)}</span></a></td>
            <td>{money(position.value_usd)}</td>
            <td>{position.portfolio_weight_pct.toFixed(2)}%</td>
            <td>{Math.round(position.shares).toLocaleString("en-US")}</td>
            <td>{sentenceCase(position.change)}{position.share_delta_pct === null ? "" : ` · ${position.share_delta_pct > 0 ? "+" : ""}${position.share_delta_pct.toFixed(1)}%`}</td>
            <td><a className="table-source-link" href={position.filing_source_url} target="_blank" rel="noreferrer">13F ↗</a><a className="table-source-link" href={position.identity_source_url} target="_blank" rel="noreferrer">Identity ↗</a></td>
          </tr>)}</tbody>
        </table></TableScroll> : <p className="empty-filter">No crypto-linked ETP positions appear in the tracked manager release.</p>}
        <p className="company-scope-note">An ETP position is a reported security holding. It is not direct token ownership, an ETF flow, a wallet attribution, or evidence of investment intent.</p>
      </section>
      <section className="crypto-controls page-shell"><div><p className="terminal-eyebrow">Crypto-specific controls</p><h2>Continuous markets need a stricter contract.</h2></div><div className="control-list"><span>Stable asset + network identity</span><span>Composite price methodology</span><span>Separate continuous-market freshness</span><span>Wrapped and bridged asset policy</span><span>Chain finality and revision handling</span><span>ETF flows ≠ token ownership</span></div></section>
      <MarketFooter context="crypto" />
    </main>
  );
}
