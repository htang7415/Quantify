import { useEffect, useRef, useState, type FormEvent } from "react";
import { SourceDetails } from "./ResearchUI";
import { verifyAnalysis } from "./api";
import { beginSignIn, finishSignIn } from "./auth";
import { CommercialFooter } from "./CommercialFooter";
import { SiteNav } from "./SiteNav";
import type { VerificationRequest, VerificationResponse, Verdict } from "./types";
import { verificationCompanies, verificationCompanyForCik } from "./verificationContract";

type Verifier = (request: VerificationRequest) => Promise<VerificationResponse>;

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

export function VerificationPage({ verifier = verifyAnalysis, initialCompanyCik }: { verifier?: Verifier; initialCompanyCik?: string }) {
  const anonymousTrial = Boolean(import.meta.env.VITE_QUANTIFY_TRIAL_URL);
  const [cik, setCik] = useState(() => verificationCompanyForCik(initialCompanyCik)?.cik ?? verificationCompanies[0].cik);
  const [asOfDate, setAsOfDate] = useState("2024-07-30");
  const [analysis, setAnalysis] = useState("");
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [signInMessage, setSignInMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const analysisRef = useRef<HTMLTextAreaElement>(null);
  const selectedCompany = verificationCompanyForCik(cik)?.name ?? "Selected company";
  const analysisCount = wordCount(analysis);
  const scopeReady = Boolean(cik && asOfDate);
  const claimReady = analysisCount > 0 && analysisCount <= 250;
  const readinessMessage = !scopeReady
    ? "Complete the scope"
    : analysisCount === 0
      ? "Add one factual claim"
      : analysisCount > 250
      ? "Shorten the claim to 250 words"
        : "Ready to verify";

  function loadExample() {
    setCik(verificationCompanies[0].cik);
    setAsOfDate("2024-07-30");
    setAnalysis("Microsoft revenue increased from fiscal 2023 to fiscal 2024.");
    setResult(null);
    setError(null);
  }

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
    if (!cik || !asOfDate) {
      setError("Choose a company and claim as-of date.");
      return;
    }
    if (!analysis.trim()) {
      setError("Enter one factual claim to verify.");
      return;
    }
    if (count > 250) {
      setError("The claim must contain 250 words or fewer.");
      return;
    }

    setIsSubmitting(true);
    try {
      setResult(await verifier({ cik, analysis: analysis.trim(), as_of_date: asOfDate }));
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Libration verification is currently unavailable."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  function continueFromResult(clearClaim: boolean) {
    if (clearClaim) setAnalysis("");
    setResult(null);
    setError(null);
    analysisRef.current?.focus();
  }

  function invalidateResult() {
    setResult(null);
    setError(null);
  }

  return (
    <main className="verification-app">
      <SiteNav
        active="agent"
        action={anonymousTrial
          ? { label: "Verify a claim", href: "#verify" }
          : { label: "Sign in", onClick: () => void signIn() }}
      />
      {signInMessage && <p className="auth-message shell" role="status">{signInMessage}</p>}

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow">Libration Agent · Current task: verification</p>
          <h1>Verify one company claim.</h1>
          <p className="hero-text">
            Check a supported factual claim against frozen SEC evidence and receive a deterministic, reviewable result.
          </p>
          <div className="hero-actions">
            <a className="button button-dark" href="#verify">
              Check a claim <span aria-hidden="true">↓</span>
            </a>
            <a className="button button-light" href="/#research">
              Explore released research
            </a>
          </div>
        </div>
        <aside className="agent-panel agent-signal signal-surface" aria-label="Libration agent workflow">
          <div className="agent-window-bar">
            <div className="agent-identity">
              <span className="agent-orb" aria-hidden="true" />
              <div>
                <strong>Libration Agent</strong>
              <span>Current task · evidence-bound verification</span>
              </div>
            </div>
            <span className="agent-status"><i className="status-dot" /> Contract ready</span>
          </div>
          <div className="agent-run-label">
            <span>Agent system · evaluation sample</span>
            <span>No live retrieval</span>
          </div>
          <div className="agent-prompt">
            <p className="card-label">Incoming research</p>
            <p>Microsoft revenue increased from fiscal 2023 to fiscal 2024.</p>
          </div>
          <div className="agent-trace" aria-label="Agent verification stages">
            <p><span>01</span> Lock objective + scope <i>Contract</i></p>
            <p><span>02</span> Bind released SEC facts <i>Data</i></p>
            <p><span>03</span> Check warrant + counterevidence <i>Code</i></p>
            <p><span>04</span> Compose publication verdict <i>Verifier</i></p>
          </div>
          <div className="agent-answer">
            <div>
              <p className="card-label">Publication rule</p>
              <p className="decision">Verified</p>
            </div>
            <span className="verified-icon" aria-hidden="true">✓</span>
          </div>
          <p className="agent-footnote">Evaluation preview · Actual results depend on the submitted claim and declared release.</p>
        </aside>
      </section>

      <section className="trust-bar shell" id="trust" aria-label="Libration principles">
        <span>Data · released</span>
        <span>Intelligence · typed</span>
        <span>AI analysis · gated</span>
        <span>Verification · available</span>
      </section>

      <section className="workspace shell" id="verify">
        <div className="section-heading">
          <p className="eyebrow">Available Agent task · Verification</p>
          <h2>Claim in. Evidence out.</h2>
          <p>Choose the scope, write one factual claim, and inspect the result. General AI analysis remains gated.</p>
        </div>
        <div className="work-grid">
          <form className="verify-form" onSubmit={submit} noValidate>
            <div className="agent-contract-bar" aria-label="Current verification contract">
              <span><i /> Current contract</span>
              <strong>2 companies · frozen SEC evidence · 250 words</strong>
            </div>
            <fieldset className="verify-step">
              <legend>01 · Define scope</legend>
              <label htmlFor="company">Company</label>
              <select id="company" value={cik} onChange={(event) => { setCik(event.target.value); invalidateResult(); }}>
                {verificationCompanies.map((company) => (
                  <option key={company.cik} value={company.cik}>
                    {company.name} · CIK {company.cik}
                  </option>
                ))}
              </select>

              <label htmlFor="as-of-date">Claim as-of date</label>
              <input
                id="as-of-date"
                type="date"
                value={asOfDate}
                onChange={(event) => { setAsOfDate(event.target.value); invalidateResult(); }}
                required
              />
            </fieldset>

            <fieldset className="verify-step">
              <legend>02 · Write one claim</legend>
              <div className="label-row">
                <label htmlFor="analysis">Claim to verify</label>
                <span id="analysis-word-limit" aria-live="polite">{analysisCount} / 250 words</span>
              </div>
              <textarea
                aria-describedby="analysis-word-limit analysis-claim-note analysis-data-note analysis-safety-note"
                id="analysis"
                ref={analysisRef}
                value={analysis}
                onChange={(event) => { setAnalysis(event.target.value); invalidateResult(); }}
                placeholder="Example: Microsoft revenue increased from fiscal 2023 to fiscal 2024."
                rows={7}
                maxLength={3500}
                required
              />
              <p className="field-note" id="analysis-claim-note">Write one factual claim that can be checked against the selected company’s declared evidence.</p>
              <button className="example-loader" type="button" onClick={loadExample}>Use released Microsoft example</button>
            </fieldset>
            <p className="field-note" id="analysis-data-note">
              {anonymousTrial
                ? "Open access: no sign-up required. Your analysis is sent only when you verify and is not stored in this browser."
                : "Your analysis is sent only when you verify. This prototype does not store it in the browser."}
            </p>
            <p className="safety-note" id="analysis-safety-note">Do not use this tool for price predictions, trading decisions, or personalized investment advice.</p>
            {anonymousTrial && <p className="trial-notice">The agent uses a frozen evidence release and may slow temporarily to protect reliability.</p>}
            <div className={`agent-contract-bar task-readiness${scopeReady && claimReady ? " is-ready" : ""}`} aria-label="Task readiness" aria-live="polite">
              <span><i /> Task readiness</span>
              <strong>{readinessMessage} · {selectedCompany} · {analysisCount} / 250 words</strong>
            </div>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="button button-dark button-submit" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Verifying…" : "Verify claim"} <span aria-hidden="true">↗</span>
            </button>
          </form>

          <Results
            result={result}
            isSubmitting={isSubmitting}
            companyName={selectedCompany}
            onContinue={() => continueFromResult(!result?.requires_agent_resolution)}
          />
        </div>
      </section>
      <CommercialFooter />
    </main>
  );
}

function Results({ result, isSubmitting, companyName, onContinue }: { result: VerificationResponse | null; isSubmitting: boolean; companyName: string; onContinue: () => void }) {
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
        <p>1. Define scope. 2. Write one factual claim. 3. Verify. The result will include its evidence boundary and audit reference.</p>
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
      <SourceDetails className="result-disclosure" title="Evidence, audit, and limitations">
        <dl className="result-details">
          <div><dt>Evidence scope</dt><dd>{result.evidence_scope.source} · {result.evidence_scope.forms.join(", ")}</dd></div>
          <div><dt>Snapshot</dt><dd className="hash-value">{result.evidence_scope.snapshot_manifest_hash}</dd></div>
          <div><dt>Audit reference</dt><dd className="hash-value">{result.audit_manifest_hash}</dd></div>
        </dl>
        <p className="limitation">{result.limitation}</p>
      </SourceDetails>
      <nav className="result-next-actions" aria-label="Result next actions">
        <button type="button" onClick={onContinue}>{result.requires_agent_resolution ? "Revise claim" : "Verify another claim"}</button>
        <a href="/coverage">Check coverage</a>
        <a href="/methodology">Review methodology</a>
      </nav>
      <p className="result-contract-note">Current safe response shown in full. It does not include user text, model output, or unvalidated narrative context.</p>
    </aside>
  );
}
