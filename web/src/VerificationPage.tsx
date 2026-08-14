import { useEffect, useState, type FormEvent } from "react";
import { verifyAnalysis } from "./api";
import { beginSignIn, finishSignIn } from "./auth";
import { SiteNav } from "./SiteNav";
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

export function VerificationPage({ verifier = verifyAnalysis }: { verifier?: Verifier }) {
  const anonymousTrial = Boolean(import.meta.env.VITE_QUANTIFY_TRIAL_URL);
  const [cik, setCik] = useState(companies[0].cik);
  const [asOfDate, setAsOfDate] = useState("2024-07-30");
  const [analysis, setAnalysis] = useState("");
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [signInMessage, setSignInMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const selectedCompany = companies.find((company) => company.cik === cik)?.name ?? "Selected company";

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
    <main className="verification-app">
      <SiteNav
        active="agent"
        action={anonymousTrial
          ? { label: "Open agent", href: "#verify" }
          : { label: "Sign in", onClick: () => void signIn() }}
      />
      {signInMessage && <p className="auth-message shell" role="status">{signInMessage}</p>}

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow">Public-company evidence verification</p>
          <h1>Is this claim supported by the declared evidence?</h1>
          <p className="hero-text">
            Quantify checks a bounded company-analysis claim against a frozen evidence
            release. It does not predict prices, recommend trades, or create investment advice.
          </p>
          <div className="hero-actions">
            <a className="button button-dark" href="#verify">
              Check a claim <span aria-hidden="true">↓</span>
            </a>
            <a className="button button-light" href="#trust">
              How it stays bounded
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
            <span className="agent-status"><i className="status-dot" /> Bounded</span>
          </div>
          <div className="agent-run-label">
            <span>Verification path</span>
            <span>Scope declared</span>
          </div>
          <div className="agent-prompt">
            <p className="card-label">Incoming research</p>
            <p>Assess whether a company-analysis claim is warranted by its declared frozen evidence.</p>
          </div>
          <div className="agent-trace" aria-label="Agent verification stages">
            <p><span>01</span> Declare scope <i>Required</i></p>
            <p><span>02</span> Retrieve frozen facts <i>Bounded</i></p>
            <p><span>03</span> Compose verdict <i>Deterministic</i></p>
          </div>
          <div className="agent-answer">
            <div>
              <p className="card-label">Publication rule</p>
              <p className="decision">Scope first</p>
            </div>
            <span className="verified-icon" aria-hidden="true">✓</span>
          </div>
          <p className="agent-footnote">Verification only · Review required when evidence is ambiguous</p>
        </aside>
      </section>

      <section className="trust-bar shell" id="trust" aria-label="Quantify principles">
        <span>Exact scope</span>
        <span>Frozen evidence</span>
        <span>Deterministic verdicts</span>
        <span>Review when unclear</span>
      </section>

      <section className="scale shell" aria-labelledby="scale-title">
        <div className="scale-copy">
          <p className="eyebrow">The verification contract</p>
          <h2 id="scale-title">Evidence before explanation.</h2>
          <p>
            Every result is constrained to its declared release. An empty verified set or
            a review-required result is a valid outcome.
          </p>
        </div>
        <div className="scale-grid">
          <article><span className="scale-number">01</span><h3>Bounded</h3><p>Only declared structured facts can warrant a verdict.</p></article>
          <article><span className="scale-number">02</span><h3>Traceable</h3><p>Every result carries its evidence scope and audit reference.</p></article>
          <article><span className="scale-number">03</span><h3>Fail-closed</h3><p>Ambiguity and unavailable evidence lead to review, not a guess.</p></article>
        </div>
      </section>

      <section className="workspace shell" id="verify">
        <div className="section-heading">
          <p className="eyebrow">Quantify verification</p>
          <h2>Check a claim before it travels.</h2>
          <p>Submit a short company analysis. Receive only a verdict, its declared evidence scope, and an audit reference.</p>
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
                ? "Open access: no sign-up required. Your analysis is sent only when you verify and is not stored in this browser."
                : "Your analysis is sent only when you verify. This prototype does not store it in the browser."}
            </p>
            <p className="safety-note">Do not use this tool for price predictions, trading decisions, or personalized investment advice.</p>
            {anonymousTrial && <p className="trial-notice">The agent uses a frozen evidence release and may slow temporarily to protect reliability.</p>}
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="button button-dark button-submit" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Verifying…" : "Verify analysis"} <span aria-hidden="true">↗</span>
            </button>
          </form>

          <Results result={result} isSubmitting={isSubmitting} companyName={selectedCompany} />
        </div>
      </section>

      <section className="how shell" id="how-it-works">
        <p className="eyebrow">A disciplined verification workflow</p>
        <div className="how-grid">
          <article><span>01</span><h3>Declare</h3><p>Choose a company, date, and bounded analysis claim.</p></article>
          <article><span>02</span><h3>Verify</h3><p>Structured facts are checked under deterministic evidence rules.</p></article>
          <article><span>03</span><h3>Decide</h3><p>Carry the verdict, scope, and audit reference—or route it to review.</p></article>
        </div>
      </section>
    </main>
  );
}

function Results({ result, isSubmitting, companyName }: { result: VerificationResponse | null; isSubmitting: boolean; companyName: string }) {
  if (isSubmitting) {
    return (
      <aside className="results results-progress" aria-live="polite" aria-label="Verification progress">
        <p className="card-label">Verification in progress</p>
        <h3>Checking the declared scope.</h3>
        <ol className="progress-list">
          <li>Bound the company-analysis request</li>
          <li>Load the frozen evidence release</li>
          <li>Compose the deterministic result</li>
        </ol>
        <p>This does not create a price prediction, trade instruction, or personalized advice.</p>
      </aside>
    );
  }
  if (!result) {
    return (
      <aside className="results results-empty" aria-live="polite">
        <p className="card-label">Result</p>
        <h3>Ready when you are.</h3>
        <p>Submit a bounded analysis to see claim verdicts, evidence scope, and an audit reference here. Review-required is a valid result.</p>
      </aside>
    );
  }

  return (
    <aside className="results" aria-live="polite">
      <div className="results-heading">
        <div><p className="card-label">Verification result · {companyName}</p><h3>Claim verdicts</h3></div>
        <span className="result-badge">{result.requires_agent_resolution ? "Review required" : "Scope checked"}</span>
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
        <p className="review-callout"><strong>Review required.</strong> Do not publish automatically; the declared evidence could not resolve this result.</p>
      )}
      <dl className="result-details">
        <div><dt>Evidence scope</dt><dd>{result.evidence_scope.source} · {result.evidence_scope.forms.join(", ")}</dd></div>
        <div><dt>Snapshot</dt><dd className="hash-value">{result.evidence_scope.snapshot_manifest_hash}</dd></div>
        <div><dt>Audit reference</dt><dd className="hash-value">{result.audit_manifest_hash}</dd></div>
      </dl>
      <p className="limitation">{result.limitation}</p>
    </aside>
  );
}
