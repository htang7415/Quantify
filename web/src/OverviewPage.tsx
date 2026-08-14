import { AgentSystemMap, ReleaseDataSystem } from "./AgentSystem";
import { CommercialFooter } from "./CommercialFooter";
import { SiteNav } from "./SiteNav";
import { buildCompanyOwnership } from "./companies/ownership";
import { earningsCatalog } from "./earnings/catalog";
import { money, quarter, readableDate } from "./format";
import { investorCatalog } from "./investors/catalog";
import { publicReleaseIndex, releaseFor } from "./releases/catalog";
import { ventureCatalog } from "./venture/catalog";

const companies = buildCompanyOwnership(investorCatalog);
const availableManagers = investorCatalog.managers.filter((manager) => manager.status === "available");
const disclosedValue = availableManagers.reduce(
  (total, manager) => total + (manager.disclosed_portfolio_value_usd ?? 0),
  0
);
const availableReleases = publicReleaseIndex.releases.filter((release) => release.status === "available");
const attentionReleases = publicReleaseIndex.releases.filter(
  (release) => release.status === "revoked" || release.status === "source_review" || release.freshness === "stale"
);
const earningsRelease = releaseFor("earnings");
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
        <div><span className="agent-orb" aria-hidden="true" /><strong>Quantify Agent</strong></div>
        <span className="stage-state"><i /> Scope locked</span>
      </header>
      <div className="stage-query">
        <span>Evaluation fixture · Microsoft · 10-K</span>
        <p>{verificationSample.claim}</p>
      </div>
      <div className="stage-path" aria-label="Verification stages">
        <span><b>01</b> Grounded</span>
        <span><b>02</b> Counterevidence checked</span>
        <span><b>03</b> Composed</span>
      </div>
      <div className="stage-verdict">
        <div><span>Deterministic verdict</span><strong>{verificationSample.verdict}</strong></div>
        <b aria-label="Verified">✓</b>
      </div>
      <dl className="stage-evidence">
        <div><dt>FY2024 revenue</dt><dd>{money(verificationSample.current)}</dd></div>
        <div><dt>FY2023 revenue</dt><dd>{money(verificationSample.previous)}</dd></div>
        <div><dt>Counterevidence</dt><dd>None in scope</dd></div>
      </dl>
      <footer>
        <a href={verificationSample.sourceUrl}>SEC accession {verificationSample.accession} ↗</a>
        <span>Evidence {verificationSample.previousEvidenceId} · {verificationSample.currentEvidenceId}</span>
        <span>Snapshot {shortHash(verificationSample.snapshotHash)}</span>
        <span>Audit {shortHash(verificationSample.auditHash)}</span>
        <span>Limit: declared frozen Microsoft FY2024 10-K scope only.</span>
      </footer>
    </article>
  );
}

export function OverviewPage() {
  return (
    <main className="data-app commercial-home">
      <SiteNav active="overview" action={{ label: "Open Agent", href: "/agent" }} />

      <section className="commercial-hero page-shell">
        <div className="commercial-hero-copy">
          <p className="terminal-eyebrow">AI research agent · released public-company data</p>
          <h1>Ask the question.<br /><span>See the system work.</span></h1>
          <p>Quantify turns a bounded company claim into a declared scope, released data, source-bound information, typed intelligence, and a deterministic result you can inspect.</p>
          <div className="overview-actions">
            <a className="button button-dark" href="/agent">Open Agent <span aria-hidden="true">↗</span></a>
            <a className="button button-light" href="#research">Explore released research</a>
          </div>
          <div className="commercial-proofline" aria-label="Product boundaries">
            <span><i /> {availableReleases.length} of {publicReleaseIndex.releases.length} catalogs released</span>
            <span>Evidence scope visible</span>
            <span>No trading or predictions</span>
          </div>
        </div>
        <VerificationStage />
      </section>

      <section className="release-signal page-shell" aria-label="Current public release state">
        <div><span>Public release index</span><strong>Generated {readableDate(publicReleaseIndex.generated_at.slice(0, 10))}</strong></div>
        <div><span>Available</span><strong>{availableReleases.length} catalogs</strong></div>
        <div><span>Needs attention</span><strong>{attentionReleases.length}</strong></div>
        <a href="/coverage">Inspect coverage →</a>
      </section>

      <section className="agent-operating-system product-modes page-shell" aria-labelledby="agent-operating-title">
        <div className="commercial-section-head split-head">
          <div><p className="terminal-eyebrow">System logic</p><h2 id="agent-operating-title">One objective. Five controlled stages.</h2></div>
          <p>The agent can organize the work. Released data and deterministic code control what becomes a result.</p>
        </div>
        <AgentSystemMap />
      </section>

      <ReleaseDataSystem />

      <section className="product-modes page-shell" aria-labelledby="product-modes-title">
        <div className="commercial-section-head">
          <p className="terminal-eyebrow">Start with the job</p>
          <h2 id="product-modes-title">Choose the research job.</h2>
          <p>Each path names what you provide, what Quantify returns, and where the current release stops.</p>
        </div>
        <div className="product-mode-grid">
          <article>
            <span>01 / Information</span>
            <h3>Browse released records.</h3>
            <p>Input: a market, manager, or company. Output: source-bound records from active frozen releases.</p>
            <a href="#research">Browse research →</a>
          </article>
          <article>
            <span>02 / Intelligence</span>
            <h3>Connect compatible facts.</h3>
            <p>Input: a released entity or period. Output: exact typed relationships, changes, and official actions.</p>
            <a href="/intelligence">Connect facts →</a>
          </article>
          <article className="product-mode-featured">
            <span>03 / Verification</span>
            <h3>Verify one claim.</h3>
            <p>Input: company, as-of date, and factual claim. Output: verdict, scope, limitation, and audit identity.</p>
            <a href="/agent">Verify a claim →</a>
          </article>
        </div>
      </section>

      <section className="research-grid-section" id="research" aria-labelledby="research-grid-title">
        <div className="page-shell">
          <div className="commercial-section-head split-head">
            <div><p className="terminal-eyebrow">Released research</p><h2 id="research-grid-title">Data and information, released by scope.</h2></div>
            <p>Unavailable layers stay unavailable. Every active layer shows when and how it was observed.</p>
          </div>
          <div className="research-entry-grid">
            <a href="/markets">
              <span>Markets</span><strong>Macro, rates, and filed ETF context.</strong>
              <small>{macroRelease.freshness} macro · {ratesRelease.freshness} rates</small><b>Explore →</b>
            </a>
            <a href="/investors">
              <span>Investors</span><strong>{availableManagers.length} reporting managers across one frozen 13F scope.</strong>
              <small>{quarter(investorCatalog.report_period)} · {money(disclosedValue)} tracked disclosed value</small><b>Explore →</b>
            </a>
            <a href="/companies">
              <span>Companies</span><strong>{companies.length} exact issuer mappings across compatible releases.</strong>
              <small>Released connections only</small><b>Explore →</b>
            </a>
            <a href="/intelligence">
              <span>Intelligence</span><strong>Reported earnings and reviewed policy actions.</strong>
              <small>{earningsRelease.status} earnings · {policyRelease.status} policy</small><b>Explore →</b>
            </a>
            <a href="/investors/venture">
              <span>Venture</span><strong>{ventureCatalog.firms.length} firms and {ventureCatalog.firms.reduce((sum, firm) => sum + firm.tracked_relationship_count, 0)} official-source relationships.</strong>
              <small>No ownership or valuation inference</small><b>Explore →</b>
            </a>
            <a href="/intelligence/earnings">
              <span>Earnings</span><strong>{earningsCatalog.companies.length} companies with exact comparable SEC facts.</strong>
              <small>Reported results · no estimates</small><b>Explore →</b>
            </a>
          </div>
        </div>
      </section>

      <section className="agent-principle page-shell signal-surface">
        <div>
          <p className="signal-kicker">A more accountable AI agent</p>
          <h2>Useful because it shows its limits.</h2>
        </div>
        <div className="agent-principle-grid">
          <article><span>Scope</span><strong>Know exactly what the agent checked.</strong></article>
          <article><span>Evidence</span><strong>Trace facts back to the declared release.</strong></article>
          <article><span>Counterevidence</span><strong>See what could qualify or defeat the claim.</strong></article>
          <article><span>Review</span><strong>Get an explicit stop when ambiguity remains.</strong></article>
        </div>
        <a className="button signal-button" href="/product">See how Quantify works →</a>
      </section>

      <section className="workflow-section page-shell">
        <div className="commercial-section-head"><p className="terminal-eyebrow">Built for review</p><h2>Research that can move through a team.</h2></div>
        <div className="workflow-list">
          <article><span>Research</span><strong>Check disclosure claims before they enter a report.</strong><i>Claim → evidence → verdict</i></article>
          <article><span>Strategy</span><strong>Connect companies, policy, earnings, and reported capital.</strong><i>Entity → release → source</i></article>
          <article><span>Investor relations</span><strong>Inspect how official company facts support a statement.</strong><i>Statement → qualification → citation</i></article>
          <article><span>Compliance-sensitive teams</span><strong>Preserve scope and audit identity for review.</strong><i>Result → reviewer → record</i></article>
        </div>
      </section>

      <section className="commercial-cta page-shell">
        <p className="terminal-eyebrow">Start with one claim</p>
        <h2>Put the evidence in the room.</h2>
        <p>Verification is bounded to the declared frozen release. Review-required is a valid result.</p>
        <a className="button button-dark" href="/agent">Open Quantify Agent →</a>
      </section>

      <CommercialFooter />
    </main>
  );
}
