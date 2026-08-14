import { CommercialFooter } from "./CommercialFooter";
import { SiteNav } from "./SiteNav";
import { readableDate, sentenceCase } from "./format";
import { publicReleaseIndex } from "./releases/catalog";
import { releaseCatalogLabel, releaseNeedsAttention, summarizeReleaseOperations } from "./releases/operations";

const verdicts = [
  ["Verified", "Exact declared evidence warrants the claim and compatible evidence does not defeat it."],
  ["Unsupported", "The declared evidence does not warrant the claim."],
  ["Defeated", "Compatible counterevidence defeats the claim."],
  ["Qualified", "The claim is supported only with an important disclosed qualification."],
  ["Review required", "Ambiguity, invalid grounding, or unavailable information prevents publication."]
] as const;

export function ProductPage() {
  return (
    <main className="data-app commercial-info-page">
      <SiteNav active="product" action={{ label: "Open Agent", href: "/agent" }} />
      <section className="commercial-info-hero page-shell">
        <p className="terminal-eyebrow">Quantify product</p>
        <h1>One system.<br /><span>Three research modes.</span></h1>
        <p>Move from released information to connected intelligence to a deterministic verification result—without losing the evidence boundary.</p>
        <div className="overview-actions"><a className="button button-dark" href="/agent">Open Agent →</a><a className="button button-light" href="/coverage">See current coverage</a></div>
      </section>

      <section className="product-system page-shell" aria-labelledby="product-system-title">
        <div className="commercial-section-head"><p className="terminal-eyebrow">The system</p><h2 id="product-system-title">Different jobs. Clear authority.</h2></div>
        <div className="product-system-flow">
          <article><span>01</span><h3>Information</h3><p>Exact released records with source, time, scope, freshness, and limitations.</p><a href="/#research">Explore research →</a></article>
          <i aria-hidden="true">→</i>
          <article><span>02</span><h3>Intelligence</h3><p>Typed connections and reported changes across compatible active releases.</p><a href="/intelligence">Open intelligence →</a></article>
          <i aria-hidden="true">→</i>
          <article><span>03</span><h3>Verification</h3><p>Claim-level verdicts with declared evidence scope and immutable audit identity.</p><a href="/agent">Verify a claim →</a></article>
        </div>
      </section>

      <section className="authority-section signal-surface page-shell">
        <div><p className="signal-kicker">The authority boundary</p><h2>The agent researches.<br />The verifier decides.</h2></div>
        <div className="authority-stack">
          <article><span>Model</span><strong>Proposes structured work</strong><p>Untrusted until validated.</p></article>
          <article><span>Code</span><strong>Checks grounding and warrant</strong><p>Exact released facts only.</p></article>
          <article><span>Verifier</span><strong>Composes the publication verdict</strong><p>No model fallback or hidden guess.</p></article>
        </div>
      </section>

      <section className="capability-section page-shell" aria-labelledby="capability-title">
        <div className="commercial-section-head"><p className="terminal-eyebrow">Current contract</p><h2 id="capability-title">Available now. Gated next.</h2></div>
        <div className="capability-table" role="table" aria-label="Current and gated product capabilities">
          <div role="row"><strong role="columnheader">Product area</strong><strong role="columnheader">Available</strong><strong role="columnheader">Gated next</strong></div>
          <div role="row"><b role="rowheader">Information</b><span role="cell">Active public release catalogs</span><span role="cell">New sources and live or licensed data</span></div>
          <div role="row"><b role="rowheader">Intelligence</b><span role="cell">Exact earnings, policy, ownership, and entity connections</span><span role="cell">Narrative briefs and broader synthesis</span></div>
          <div role="row"><b role="rowheader">Verification</b><span role="cell">Bounded safe contract and deterministic verdicts</span><span role="cell">Broader coverage, review workspace, and exports</span></div>
          <div role="row"><b role="rowheader">Agent</b><span role="cell">One structured extraction step; zero production resolution actions</span><span role="cell">Multi-step planning and bounded typed tools</span></div>
        </div>
        <p className="commercial-boundary-note">A gated capability is not available and has no enabled action. Every expansion requires its specification, evaluation, replay, and authorization controls.</p>
      </section>

      <section className="access-contract page-shell" id="access" aria-labelledby="access-title">
        <div className="commercial-section-head"><p className="terminal-eyebrow">Access today</p><h2 id="access-title">The commercial boundary stays visible.</h2></div>
        <div className="access-contract-grid">
          <article><span>Released research</span><strong>Browse without sign-in</strong><p>Public research views show only active released records, dates, scope, and limitations.</p></article>
          <article><span>Claim verification</span><strong>Controlled access</strong><p>Use the active authenticated contract or a separately authorized bounded trial when one is enabled.</p></article>
          <article><span>Research-task pilot</span><strong>Private and not open</strong><p>No public request form, pricing, subscription, or service commitment is currently published.</p></article>
        </div>
        <p className="commercial-boundary-note">Do not submit private research material. Quantify does not collect pilot requests on this site.</p>
      </section>

      <section className="commercial-cta page-shell"><p className="terminal-eyebrow">Evidence first</p><h2>Start with a claim.</h2><p>Use the current bounded verification contract for Microsoft or Apple.</p><a className="button button-dark" href="/agent">Open Agent →</a></section>
      <CommercialFooter />
    </main>
  );
}

export function CoveragePage() {
  const summary = summarizeReleaseOperations(publicReleaseIndex);
  return (
    <main className="data-app commercial-info-page">
      <SiteNav active="coverage" action={{ label: "Open Agent", href: "/agent" }} />
      <section className="commercial-info-hero compact page-shell">
        <p className="terminal-eyebrow">Current coverage</p>
        <h1>Know what Quantify<br /><span>can actually see.</span></h1>
        <p>This page is a direct projection of the active public release index. It is coverage state—not uptime, market breadth, or a promise of future availability.</p>
      </section>

      <section className="coverage-summary page-shell" aria-label="Coverage summary">
        <article><span>Declared catalogs</span><strong>{summary.total}</strong></article>
        <article><span>Available</span><strong>{summary.available}</strong></article>
        <article><span>Current</span><strong>{summary.current}</strong></article>
        <article><span>Attention</span><strong>{summary.attention}</strong></article>
      </section>

      <section className="coverage-catalog page-shell" aria-labelledby="coverage-catalog-title">
        <div className="commercial-section-head split-head"><div><p className="terminal-eyebrow">Release index</p><h2 id="coverage-catalog-title">Every declared layer.</h2></div><p>Generated {readableDate(publicReleaseIndex.generated_at.slice(0, 10))}</p></div>
        <div className="coverage-list">
          {publicReleaseIndex.releases.map((release) => (
            <article key={release.catalog}>
              <div className="coverage-name"><span>{releaseCatalogLabel(release.catalog)}</span><strong>{release.limitations[0]}</strong></div>
              <div><span>Status</span><strong className={releaseNeedsAttention(release) ? "coverage-attention" : ""}>{release.status === "source_review" ? "Source review" : sentenceCase(release.status)}</strong></div>
              <div><span>Freshness</span><strong>{sentenceCase(release.freshness)}</strong></div>
              <div><span>Observed</span><strong>{release.observed_at ? readableDate(release.observed_at.slice(0, 10)) : "Not released"}</strong></div>
              <details><summary>Release identity</summary><code>{release.release_id ?? "No active release"}</code>{release.manifest_hash && <code>{release.manifest_hash}</code>}</details>
            </article>
          ))}
        </div>
        <p className="commercial-boundary-note">Unavailable means unavailable. Quantify does not substitute model-generated, illustrative, or out-of-policy values.</p>
      </section>
      <CommercialFooter />
    </main>
  );
}

export function MethodologyPage() {
  return (
    <main className="data-app commercial-info-page">
      <SiteNav active="methodology" action={{ label: "Open Agent", href: "/agent" }} />
      <section className="commercial-info-hero compact page-shell">
        <p className="terminal-eyebrow">Quantify methodology</p>
        <h1>Evidence before<br /><span>explanation.</span></h1>
        <p>A model can propose research work. Only deterministic code can validate released facts and compose a publication verdict.</p>
      </section>

      <section className="method-flow page-shell" aria-labelledby="method-flow-title">
        <div className="commercial-section-head"><p className="terminal-eyebrow">Verification path</p><h2 id="method-flow-title">Four controlled steps.</h2></div>
        <ol>
          <li><span>01</span><div><h3>Declare</h3><p>Bind the company, as-of date, supported forms, and frozen evidence release.</p></div></li>
          <li><span>02</span><div><h3>Propose</h3><p>The model proposes typed statements and evidence references. Its output remains untrusted.</p></div></li>
          <li><span>03</span><div><h3>Validate</h3><p>Deterministic code checks grounding, type, warrant, qualification, and compatible counterevidence.</p></div></li>
          <li><span>04</span><div><h3>Compose</h3><p>The deterministic verifier alone produces the verdict and binds it to an audit identity.</p></div></li>
        </ol>
      </section>

      <section className="retrieval-boundary page-shell signal-surface">
        <div><p className="signal-kicker">Two retrieval paths</p><h2>Facts decide.<br />Narrative explains.</h2></div>
        <article><span>Structured facts</span><strong>Exact typed lookup</strong><p>Eligible to support or defeat a verdict when released and compatible.</p></article>
        <article><span>Narrative context</span><strong>Release-scoped context only</strong><p>May explain issuer disclosure. Never establishes a fact or changes a verdict.</p></article>
      </section>

      <section className="verdict-method page-shell" aria-labelledby="verdict-method-title">
        <div className="commercial-section-head"><p className="terminal-eyebrow">Result language</p><h2 id="verdict-method-title">Five complete outcomes.</h2></div>
        <div className="verdict-method-grid">{verdicts.map(([label, meaning]) => <article key={label}><span>{label}</span><p>{meaning}</p></article>)}</div>
      </section>

      <section className="boundary-section page-shell" id="boundaries" aria-labelledby="boundaries-title">
        <div><p className="terminal-eyebrow">Research boundaries</p><h2 id="boundaries-title">What Quantify does not do.</h2></div>
        <ul><li>Predict security prices or market direction</li><li>Recommend buy, sell, hold, allocation, or position size</li><li>Provide personalized investment advice or suitability</li><li>Execute trades or manage a portfolio</li><li>Claim evidence outside the named frozen release was checked</li></ul>
      </section>
      <CommercialFooter />
    </main>
  );
}
