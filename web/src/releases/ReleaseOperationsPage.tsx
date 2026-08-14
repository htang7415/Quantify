import { SiteNav } from "../SiteNav";
import { readableDate, sentenceCase } from "../format";
import { publicReleaseIndex } from "./catalog";
import { releaseCatalogLabel, releaseNeedsAttention, summarizeReleaseOperations } from "./operations";
import type { PublicRelease } from "./types";

function displayDate(value: string | null): string {
  return value ? readableDate(value.slice(0, 10)) : "Not released";
}

function releaseState(release: PublicRelease): string {
  if (releaseNeedsAttention(release)) return "Attention";
  return sentenceCase(release.status);
}

function ManifestHash({ value }: { value: string | null }) {
  if (!value) return <span className="release-empty-value">Not released</span>;
  return (
    <details className="release-hash">
      <summary>{value.slice(0, 12)}…</summary>
      <code>{value}</code>
    </details>
  );
}

export function ReleaseOperationsPage() {
  const summary = summarizeReleaseOperations();
  return (
    <main className="data-app release-operations-page">
      <SiteNav active="intelligence" action={{ label: "Verify a claim", href: "/agent" }} />
      <section className="data-hero release-operations-hero page-shell">
        <div>
          <p className="terminal-eyebrow">Intelligence / release operations</p>
          <h1>Every public release. One exact state.</h1>
          <p>A read-only view of the public release index: what is available, when it was observed, and the immutable identity behind it.</p>
          <div className="scope-pills"><span><i /> {summary.total} declared catalogs</span><span>Index generated {displayDate(publicReleaseIndex.generated_at)}</span></div>
        </div>
      </section>
      <nav className="market-subnav page-shell" aria-label="Intelligence sections"><a href="/intelligence">All intelligence</a><a href="/intelligence/earnings">Earnings</a><a href="/intelligence/policy">Policy</a><a className="active" href="/intelligence/releases">Release operations</a></nav>

      <section className="release-operations-shell page-shell" aria-labelledby="release-state-title">
        <div className="release-summary-grid" aria-label="Public release summary">
          <article><span>Available</span><strong>{summary.available}</strong><p>Released with replay identity</p></article>
          <article><span>Unavailable</span><strong>{summary.unavailable}</strong><p>No approved active release</p></article>
          <article><span>Current</span><strong>{summary.current}</strong><p>Available and freshness-current</p></article>
          <article><span>Attention</span><strong>{summary.attention}</strong><p>Stale, revoked, or source review</p></article>
        </div>

        <div className="data-section-head release-state-head"><div><p className="terminal-eyebrow">Public index</p><h2 id="release-state-title">Catalog state</h2></div><span className="release-badge">Read only</span></div>
        <div className="release-table-wrap">
          <table className="release-operations-table">
            <thead><tr><th>Catalog</th><th>State</th><th>Freshness</th><th>Observed</th><th>Release ID</th><th>Manifest</th></tr></thead>
            <tbody>{publicReleaseIndex.releases.map((release) => <tr key={release.catalog}>
              <th scope="row"><strong>{releaseCatalogLabel(release.catalog)}</strong><small>{release.limitations[0]}</small></th>
              <td><span className={`release-state release-state-${releaseState(release).toLowerCase()}`}>{releaseState(release)}</span></td>
              <td>{sentenceCase(release.freshness)}</td>
              <td>{displayDate(release.observed_at)}</td>
              <td><code>{release.release_id ?? "Not released"}</code></td>
              <td><ManifestHash value={release.manifest_hash} /></td>
            </tr>)}</tbody>
          </table>
        </div>
        <p className="data-note">Counts are exact arithmetic over public-release-index.v3. They are not uptime, review throughput, or production telemetry.</p>
      </section>

      <section className="release-lifecycle page-shell" aria-labelledby="candidate-lifecycle-title">
        <div><p className="terminal-eyebrow">Offline candidate lifecycle</p><h2 id="candidate-lifecycle-title">Source to review, without implicit publish.</h2><p>Each boundary is explicit. The candidate coordinator cannot activate a catalog or deploy the website.</p></div>
        <ol>
          <li><span>01</span><div><strong>Reviewed local inputs</strong><p>Exact source files, metadata, active bindings, and hashes.</p></div></li>
          <li><span>02</span><div><strong>Deterministic compile</strong><p>Selected catalogs compile from reviewed local inputs in declared dependency order.</p></div></li>
          <li><span>03</span><div><strong>Candidate manifest</strong><p>Input hashes, output hashes, release IDs, and rollback bindings.</p></div></li>
          <li><span>04</span><div><strong>Separate review</strong><p>Promotion and deployment still require their own authorization.</p></div></li>
        </ol>
      </section>

      <footer className="catalog-footer market-catalog-footer"><div><strong>Index / {publicReleaseIndex.schema_version}</strong><span>Generated {publicReleaseIndex.generated_at.replace("T", " ").replace("Z", " UTC")}</span></div><div><p>Only public catalog identity and state are shown here.</p><p>Unavailable is a valid fail-closed result; no missing value is estimated.</p></div><p>Research data only. No price predictions, trade recommendations, or personalized investment advice.</p></footer>
    </main>
  );
}
