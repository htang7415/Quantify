import { useEffect, useState, type FormEvent } from "react";
import { verifyAnalysis } from "./api";
import { beginSignIn, finishSignIn } from "./auth";
import type { VerificationRequest, VerificationResponse, Verdict } from "./types";

type Verifier = (request: VerificationRequest) => Promise<VerificationResponse>;

const companies = [
  { cik: "0000789019", name: "Microsoft" },
  { cik: "0000320193", name: "Apple" }
];

const verdictCopy: Record<Verdict, string> = {
  verified: "Supported by the declared frozen evidence snapshot.",
  unsupported: "The declared evidence does not warrant this claim.",
  defeated: "Compatible evidence in the declared snapshot defeats this claim.",
  qualified: "Supported only with an important qualification.",
  requires_agent_resolution: "A reviewer must resolve an ambiguity before publication."
};

function wordCount(value: string): number {
  return value.trim() ? value.trim().split(/\s+/).length : 0;
}

export function App({ verifier = verifyAnalysis }: { verifier?: Verifier }) {
  const [cik, setCik] = useState(companies[0].cik);
  const [asOfDate, setAsOfDate] = useState("2024-07-30");
  const [analysis, setAnalysis] = useState("");
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [signInMessage, setSignInMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    void finishSignIn().catch((authError) => {
      setSignInMessage(authError instanceof Error ? authError.message : "Sign-in could not be completed.");
    });
  }, []);

  async function signIn() {
    setSignInMessage(null);
    try {
      await beginSignIn();
    } catch (authError) {
      setSignInMessage(authError instanceof Error ? authError.message : "Sign-in could not be started.");
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null);
    setError(null);
    const count = wordCount(analysis);
    if (!analysis.trim()) {
      setError("Enter an analysis to verify.");
      return;
    }
    if (count > 250) {
      setError("Analysis must contain 250 words or fewer.");
      return;
    }

    setIsSubmitting(true);
    try {
      setResult(await verifier({ cik, analysis: analysis.trim(), as_of_date: asOfDate }));
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Quantify verification is currently unavailable."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main>
      <nav className="nav" aria-label="Primary navigation">
        <a className="brand" href="#top" aria-label="Quantify home">
          <span className="brand-mark">Q</span>
          <span>Quantify</span>
        </a>
        <div className="nav-links" aria-label="Product links">
          <a href="#how-it-works">How it works</a>
          <a href="#verify">Verify analysis</a>
          <a href="#trust">Trust</a>
        </div>
        <button className="button button-dark button-compact" type="button" onClick={() => void signIn()}>
          Sign in
        </button>
      </nav>
      {signInMessage && <p className="auth-message shell" role="status">{signInMessage}</p>}

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow">Evidence verification for AI research</p>
          <h1>Publish claims you can defend.</h1>
          <p className="hero-text">
            Quantify checks factual company-analysis claims against a declared,
            frozen evidence release—then records exactly what supports the result.
          </p>
          <div className="hero-actions">
            <a className="button button-dark" href="#verify">
              Verify an analysis <span aria-hidden="true">↗</span>
            </a>
            <a className="button button-light" href="#how-it-works">
              How it works
            </a>
          </div>
        </div>
        <div className="hero-art" aria-label="Evidence verification workflow">
          <div className="art-topline">
            <span className="status-dot" /> Frozen evidence release
            <span className="art-code">Q-001</span>
          </div>
          <div className="art-card art-card-main">
            <p className="card-label">Verification decision</p>
            <p className="decision">VERIFIED</p>
            <p>Claim is supported by the declared evidence snapshot.</p>
          </div>
          <div className="art-card art-card-side">
            <p className="card-label">Audit record</p>
            <div className="audit-lines"><span /><span /><span /></div>
          </div>
          <div className="art-grid" aria-hidden="true">
            <span /><span /><span /><span /><span /><span />
          </div>
        </div>
      </section>

      <section className="trust-bar shell" id="trust" aria-label="Quantify principles">
        <span>One bounded model call</span>
        <span>Frozen evidence scope</span>
        <span>Deterministic verdicts</span>
        <span>Audit-ready output</span>
      </section>

      <section className="scale shell" aria-labelledby="scale-title">
        <div className="scale-copy">
          <p className="eyebrow">Designed for commercial scale</p>
          <h2 id="scale-title">A bounded agent, designed to scale.</h2>
          <p>
            Quantify grows through independently operated verification cells and
            immutable evidence releases—not through more model autonomy.
          </p>
        </div>
        <div className="scale-grid">
          <article><span className="scale-number">01</span><h3>Tenant-ready</h3><p>The commercial control plane will isolate customer reports, audit records, credentials, and usage.</p></article>
          <article><span className="scale-number">02</span><h3>Release-pinned</h3><p>Every verdict identifies the exact evidence, policy, model, and schema release.</p></article>
          <article><span className="scale-number">03</span><h3>Cell-ready</h3><p>Future stateless AWS verification cells can scale capacity while preserving the same contract.</p></article>
        </div>
      </section>

      <section className="workspace shell" id="verify">
        <div className="section-heading">
          <p className="eyebrow">Quantify verification</p>
          <h2>Is this claim supported by the declared evidence?</h2>
          <p>Submit a bounded company analysis. Quantify returns verdicts, not investment advice.</p>
        </div>
        <div className="work-grid">
          <form className="verify-form" onSubmit={submit} noValidate>
            <label htmlFor="company">Company</label>
            <select id="company" value={cik} onChange={(event) => setCik(event.target.value)}>
              {companies.map((company) => (
                <option key={company.cik} value={company.cik}>
                  {company.name} · CIK {company.cik}
                </option>
              ))}
            </select>

            <label htmlFor="as-of-date">Analysis as-of date</label>
            <input
              id="as-of-date"
              type="date"
              value={asOfDate}
              onChange={(event) => setAsOfDate(event.target.value)}
              required
            />

            <div className="label-row">
              <label htmlFor="analysis">Company analysis</label>
              <span aria-live="polite">{wordCount(analysis)} / 250 words</span>
            </div>
            <textarea
              id="analysis"
              value={analysis}
              onChange={(event) => setAnalysis(event.target.value)}
              placeholder="Example: Microsoft revenue increased from fiscal 2023 to fiscal 2024."
              rows={7}
              maxLength={3500}
              required
            />
            <p className="field-note">Your analysis is sent only when you verify. This prototype does not store it in the browser.</p>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="button button-dark button-submit" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Verifying…" : "Verify analysis"} <span aria-hidden="true">↗</span>
            </button>
          </form>

          <Results result={result} />
        </div>
      </section>

      <section className="how shell" id="how-it-works">
        <p className="eyebrow">Built for reliable AI workflows</p>
        <div className="how-grid">
          <article><span>01</span><h3>Bound the task</h3><p>Analysis, company, date, and evidence scope are explicit.</p></article>
          <article><span>02</span><h3>Verify deterministically</h3><p>The model proposes; the evidence verifier decides.</p></article>
          <article><span>03</span><h3>Keep an audit trail</h3><p>Every result names its evidence scope and audit reference.</p></article>
        </div>
      </section>
    </main>
  );
}

function Results({ result }: { result: VerificationResponse | null }) {
  if (!result) {
    return (
      <aside className="results results-empty" aria-live="polite">
        <p className="card-label">Result</p>
        <h3>Ready when you are.</h3>
        <p>Submit a bounded analysis to see claim verdicts, evidence scope, and an audit reference here.</p>
      </aside>
    );
  }

  return (
    <aside className="results" aria-live="polite">
      <div className="results-heading">
        <div><p className="card-label">Verification result</p><h3>Claim verdicts</h3></div>
        <span className="result-badge">Complete</span>
      </div>
      <div className="verdict-list">
        {result.verdicts.map((item) => (
          <article className={`verdict verdict-${item.verdict}`} key={item.claim_id}>
            <div><p className="card-label">{item.claim_id}</p><strong>{item.verdict.replaceAll("_", " ")}</strong></div>
            <p>{verdictCopy[item.verdict]}</p>
          </article>
        ))}
      </div>
      {result.requires_agent_resolution && (
        <p className="review-callout">Review required: do not publish automatically.</p>
      )}
      <dl className="result-details">
        <div><dt>Evidence scope</dt><dd>{result.evidence_scope.source} · {result.evidence_scope.forms.join(", ")}</dd></div>
        <div><dt>Snapshot</dt><dd>{result.evidence_scope.snapshot_manifest_hash.slice(0, 12)}…</dd></div>
        <div><dt>Audit reference</dt><dd>{result.audit_manifest_hash.slice(0, 12)}…</dd></div>
      </dl>
      <p className="limitation">{result.limitation}</p>
    </aside>
  );
}
