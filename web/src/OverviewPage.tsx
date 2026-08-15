import { CommercialFooter } from "./CommercialFooter";
import { SiteNav } from "./SiteNav";
import { buildCompanyOwnership } from "./companies/ownership";
import { money, quarter, sentenceCase } from "./format";
import { investorCatalog } from "./investors/catalog";
import { publicReleaseIndex, releaseFor } from "./releases/catalog";

const companies = buildCompanyOwnership(investorCatalog);
const availableManagers = investorCatalog.managers.filter((manager) => manager.status === "available");
const disclosedValue = availableManagers.reduce(
  (total, manager) => total + (manager.disclosed_portfolio_value_usd ?? 0),
  0
);
const availableReleases = publicReleaseIndex.releases.filter((release) => release.status === "available");
const policyRelease = releaseFor("policy");
const ratesRelease = releaseFor("rates");
const macroRelease = releaseFor("macro");

const verificationSample = {
  claim: "Microsoft revenue increased from fiscal 2023 to fiscal 2024.",
  verdict: "Verified",
  current: 245_122_000_000,
  previous: 211_915_000_000,
  currentEvidenceId: "msft-revenue-fy2024",
  previousEvidenceId: "msft-revenue-fy2023",
  accession: "0000950170-24-087843",
  sourceUrl: "https://www.sec.gov/Archives/edgar/data/789019/000095017024087843/msft-20240630.htm",
  snapshotHash: "d6515f4a192db2dafdf0ae198d9d2e65eda61904df92d142e4d21cbf89424292",
  auditHash: "75b9cf2d09839c6aea69050bbe0ae490df946aafc459a57049fdea6df790722e"
} as const;

function shortHash(value: string): string {
  return `${value.slice(0, 10)}…${value.slice(-6)}`;
}

function VerificationStage() {
  return (
    <article className="product-stage signal-surface" aria-label="Versioned verification sample">
      <header>
        <div><span className="agent-orb" aria-hidden="true" /><strong>Libration · Verification sample</strong></div>
        <span className="stage-state"><i /> Released scope</span>
      </header>
      <div className="stage-query">
        <span>Microsoft · FY2024 10-K · SEC filing scope</span>
        <p>{verificationSample.claim}</p>
      </div>
      <div className="stage-verdict">
        <div>
          <span>Verification result</span>
          <strong>{verificationSample.verdict}</strong>
          <small>The released filing supports this claim.</small>
        </div>
        <b aria-label="Verified">✓</b>
      </div>
      <dl className="stage-evidence">
        <div><dt>FY2024 revenue</dt><dd>{money(verificationSample.current)}</dd></div>
        <div><dt>FY2023 revenue</dt><dd>{money(verificationSample.previous)}</dd></div>
        <div><dt>Counterevidence</dt><dd>None in scope</dd></div>
      </dl>
      <details className="stage-details">
        <summary>Evidence and audit details</summary>
        <div>
          <a href={verificationSample.sourceUrl}>SEC accession {verificationSample.accession} ↗</a>
          <span>Evidence {verificationSample.previousEvidenceId} · {verificationSample.currentEvidenceId}</span>
          <span>Snapshot {shortHash(verificationSample.snapshotHash)}</span>
          <span>Audit {shortHash(verificationSample.auditHash)}</span>
          <span>Limit: declared frozen Microsoft FY2024 10-K scope only.</span>
        </div>
      </details>
    </article>
  );
}

export function OverviewPage() {
  return (
    <main className="data-app commercial-home">
      <SiteNav active="overview" action={{ label: "Verify a claim", href: "/agent" }} />

      <section className="commercial-hero page-shell">
        <div className="commercial-hero-copy">
          <p className="terminal-eyebrow">AI research for investors</p>
          <h1>See more of<br /><span>what matters.</span></h1>
          <p>For investors, analysts, and curious learners: explore released company and market research, trace the sources, and verify factual claims.</p>
          <div className="overview-actions">
            <a className="button button-dark" href="/companies">Explore companies <span aria-hidden="true">→</span></a>
            <a className="button button-light" href="/agent">Verify a claim</a>
          </div>
          <div className="commercial-proofline" aria-label="Product boundaries">
            <span><i /> {availableReleases.length} of {publicReleaseIndex.releases.length} catalogs released</span>
            <span>AI research answers not public</span>
            <span>No trading or predictions</span>
          </div>
        </div>
        <VerificationStage />
      </section>

      <section className="research-grid-section" id="research" aria-labelledby="research-grid-title">
        <div className="page-shell">
          <div className="commercial-section-head split-head">
            <div><p className="terminal-eyebrow">Released research</p><h2 id="research-grid-title">Start with the evidence.</h2></div>
            <p>Every view states its source, observation time, scope, release identity, and limits.</p>
          </div>
          <div className="research-entry-grid research-entry-grid-compact">
            <a href="/companies">
              <span>Companies</span><strong>Connect reported holdings, filed ETF exposure, earnings, and policy.</strong>
              <small>{companies.length} exact issuer mappings · released connections only</small><b>Open companies →</b>
            </a>
            <a href="/markets">
              <span>Markets</span><strong>Read official macro, Treasury rates, and filed ETF data.</strong>
              <small>{macroRelease.freshness} macro · {ratesRelease.freshness} rates</small><b>Open markets →</b>
            </a>
            <a href="/investors">
              <span>Investors</span><strong>Compare reporting managers and disclosed 13F holdings.</strong>
              <small>{availableManagers.length} managers · {quarter(investorCatalog.report_period)} · {money(disclosedValue)} tracked value</small><b>Open investors →</b>
            </a>
            <a href="/intelligence/policy">
              <span>Policy</span><strong>Trace reviewed official actions to named companies.</strong>
              <small>{sentenceCase(policyRelease.status)} release · no predicted impact</small><b>Open policy →</b>
            </a>
          </div>
        </div>
      </section>

      <section className="agent-principle home-trust page-shell signal-surface" aria-labelledby="home-trust-title">
        <div>
          <div><p className="signal-kicker">How Libration works</p><h2 id="home-trust-title">Ask clearly. See what supports the result.</h2></div>
          <p>Libration works from released data, keeps sources visible, and refuses unsupported results.</p>
        </div>
        <div className="agent-principle-grid">
          <article><span>01 · Question</span><strong>Ask one clear research question or claim.</strong></article>
          <article><span>02 · Scope</span><strong>Choose the company, date, and released scope.</strong></article>
          <article><span>03 · Evidence</span><strong>Inspect the facts and sources used.</strong></article>
          <article><span>04 · Result</span><strong>Get a cited view or verification result.</strong></article>
        </div>
        <div className="home-trust-actions">
          <p>Unavailable data stays unavailable. Broader AI research answers are not public yet.</p>
          <a className="button signal-button" href="/methodology">Read the methodology →</a>
        </div>
      </section>

      <section className="commercial-cta page-shell">
        <p className="terminal-eyebrow">Current Agent task · Verification</p>
        <h2>Check one claim.</h2>
        <p>Verify a supported Microsoft or Apple factual claim against a declared frozen evidence release.</p>
        <a className="button button-dark" href="/agent">Verify a claim →</a>
      </section>

      <CommercialFooter />
    </main>
  );
}
