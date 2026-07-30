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
  const anonymousTrial = Boolean(import.meta.env.VITE_QUANTIFY_TRIAL_URL);
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
          <a href="#verify">Agent</a>
          <a href="#how-it-works">How it works</a>
          <a href="#trust">Trust</a>
        </div>
        {anonymousTrial ? (
          <a className="button button-dark button-compact" href="#verify">Try Quantify</a>
        ) : (
          <button className="button button-dark button-compact" type="button" onClick={() => void signIn()}>
            Sign in
          </button>
        )}
      </nav>
      {signInMessage && <p className="auth-message shell" role="status">{signInMessage}</p>}

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow">Evidence assurance for investment research</p>
          <h1>Publish research. Prove every claim.</h1>
          <p className="hero-text">
            For investment teams, trading desks, and institutional AI workflows.
            Quantify verifies company-research claims against a frozen evidence release.
          </p>
          <div className="hero-actions">
            <a className="button button-dark" href="#verify">
              Verify an analysis <span aria-hidden="true">↗</span>
            </a>
            <a className="button button-light" href="#trust">
              Why Quantify
            </a>
          </div>
        </div>
        <aside className="agent-panel" aria-label="Quantify agent workflow">
          <div className="agent-window-bar">
            <div className="agent-identity">
              <span className="agent-orb" aria-hidden="true" />
              <div>
                <strong>Quantify Agent</strong>
                <span>Research verification</span>
              </div>
            </div>
            <span className="agent-status"><i className="status-dot" /> Active</span>
          </div>
          <div className="agent-run-label">
            <span>Sample agent run</span>
            <span>Snapshot locked</span>
          </div>
          <div className="agent-prompt">
            <p className="card-label">Incoming research</p>
            <p>Assess whether the submitted claim is warranted by its declared evidence release.</p>
          </div>
          <div className="agent-trace" aria-label="Agent verification stages">
            <p><span>01</span> Parse claims <i>Complete</i></p>
            <p><span>02</span> Ground evidence <i>Complete</i></p>
            <p><span>03</span> Evaluate warrant <i>Complete</i></p>
          </div>
          <div className="agent-answer">
            <div>
              <p className="card-label">Verdict</p>
              <p className="decision">Verified</p>
            </div>
            <span className="verified-icon" aria-hidden="true">✓</span>
          </div>
          <p className="agent-footnote">Evidence verification only · Not investment advice</p>
        </aside>
      </section>

      <section className="trust-bar shell" id="trust" aria-label="Quantify principles">
        <span>Source-constrained</span>
        <span>Frozen evidence</span>
        <span>Deterministic verdicts</span>
        <span>Institution-ready audit trail</span>
      </section>

      <section className="scale shell" aria-labelledby="scale-title">
        <div className="scale-copy">
          <p className="eyebrow">Designed for commercial scale</p>
          <h2 id="scale-title">Research teams need proof, not another opinion.</h2>
          <p>
            Quantify gives analysts and AI systems an independent evidence check
            before research moves through an institution.
          </p>
        </div>
        <div className="scale-grid">
          <article><span className="scale-number">01</span><h3>Controlled</h3><p>One bounded task, one extraction, one deterministic decision.</p></article>
          <article><span className="scale-number">02</span><h3>Explainable</h3><p>Every verdict carries its evidence scope and audit reference.</p></article>
          <article><span className="scale-number">03</span><h3>Institution-ready</h3><p>Trusted verification cells preserve the contract at scale.</p></article>
        </div>
      </section>

      <section className="workspace shell" id="verify">
        <div className="section-heading">
          <p className="eyebrow">Quantify verification</p>
          <h2>Verify research before it travels.</h2>
          <p>Submit a short company analysis. Receive a verdict, evidence scope, and audit reference.</p>
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
            <p className="field-note">
              {anonymousTrial
                ? "Anonymous test preview: request limits apply. Your analysis is sent only when you verify and is not stored in this browser."
                : "Your analysis is sent only when you verify. This prototype does not store it in the browser."}
            </p>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="button button-dark button-submit" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Verifying…" : "Verify analysis"} <span aria-hidden="true">↗</span>
            </button>
          </form>

          <Results result={result} />
        </div>
      </section>

      <section className="how shell" id="how-it-works">
        <p className="eyebrow">A disciplined AI research workflow</p>
        <div className="how-grid">
          <article><span>01</span><h3>Draft</h3><p>Give the agent a company, date, and bounded research.</p></article>
          <article><span>02</span><h3>Verify</h3><p>The model extracts; deterministic evidence rules decide.</p></article>
          <article><span>03</span><h3>Publish</h3><p>Carry the verdict, scope, and audit reference with your work.</p></article>
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
