import { readableDate, sentenceCase } from "./format";
import { publicReleaseIndex } from "./releases/catalog";
import { releaseCatalogLabel } from "./releases/operations";
import type { PublicCatalog, PublicRelease } from "./releases/types";

const operatingSteps = [
  { number: "01", label: "Objective", title: "Ask one bounded question.", state: "User supplied" },
  { number: "02", label: "Scope", title: "Lock entity, date, task, and release.", state: "Contract-bound" },
  { number: "03", label: "Data", title: "Load only eligible released records.", state: "Release-indexed" },
  { number: "04", label: "Intelligence", title: "Organize exact compatible connections.", state: "Typed only" },
  { number: "05", label: "Verification", title: "Compose the result in deterministic code.", state: "Audit-bound" }
] as const;

const dataDomains: Array<{
  name: string;
  description: string;
  catalogs: PublicCatalog[];
}> = [
  {
    name: "Companies & capital",
    description: "Reported company facts and released investor relationships.",
    catalogs: ["investors", "venture", "earnings"]
  },
  {
    name: "Funds & exposure",
    description: "Filed fund activity, holdings, and mapped crypto-linked exposure.",
    catalogs: ["etf_flows", "etf_holdings", "crypto_exposure"]
  },
  {
    name: "Macro & policy",
    description: "Official macro observations, rates, and typed policy actions.",
    catalogs: ["macro", "rates", "policy"]
  },
  {
    name: "Declared watch",
    description: "Catalogs declared in the contract but not currently released.",
    catalogs: ["markets", "crypto", "events"]
  }
];

function releaseState(release: PublicRelease): string {
  if (release.status !== "available") return sentenceCase(release.status);
  return release.freshness === "current" ? "Current" : "Available";
}

export function AgentSystemMap({ compact = false }: { compact?: boolean }) {
  return (
    <ol className={`agent-system-map${compact ? " agent-system-map-compact" : ""}`} aria-label="Quantify agent operating model">
      {operatingSteps.map((step) => (
        <li key={step.number}>
          <span>{step.number} / {step.label}</span>
          <strong>{step.title}</strong>
          <small>{step.state}</small>
        </li>
      ))}
    </ol>
  );
}

export function ReleaseDataSystem() {
  return (
    <section className="data-system product-modes page-shell" aria-labelledby="data-system-title">
      <div className="commercial-section-head split-head">
        <div>
          <p className="terminal-eyebrow">Released data foundation</p>
          <h2 id="data-system-title">The agent knows what it can use.</h2>
        </div>
        <p>{publicReleaseIndex.releases.length} declared catalogs. Status comes directly from the public release index.</p>
      </div>
      <div className="data-domain-grid">
        {dataDomains.map((domain) => {
          const releases = domain.catalogs.map((catalog) =>
            publicReleaseIndex.releases.find((release) => release.catalog === catalog)
          ).filter((release): release is PublicRelease => Boolean(release));
          const available = releases.filter((release) => release.status === "available").length;
          return (
            <article key={domain.name}>
              <header><span>{domain.name}</span><strong> · {available} / {releases.length} released</strong></header>
              <p>{domain.description}</p>
              <ul>
                {releases.map((release) => (
                  <li key={release.catalog}>
                    <span>{releaseCatalogLabel(release.catalog)}</span>
                    <b className={release.status === "available" ? "data-state-available" : "data-state-unavailable"}>{releaseState(release)}</b>
                  </li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>
      <p className="commercial-boundary-note data-system-note">
        Generated {readableDate(publicReleaseIndex.generated_at.slice(0, 10))}. Unavailable means no substitute value. <a href="/coverage">Inspect release identities →</a>
      </p>
    </section>
  );
}
