# Quantify AI Agent System Design

## 1. Purpose

Quantify is an AI-powered **evidence verification agent** for factual claims
in public-company analysis. It is a publication gate, not a research writer or
an investment adviser.

```text
quantify_verify(company, analysis, as_of_date, evidence_release)
    → claim verdicts + evidence scope + audit reference
```

Its single job is to decide whether each extracted factual claim may be
published under a declared, frozen evidence release. A claim is publishable
only when the cited evidence warrants it and compatible evidence in that same
release does not defeat it.

Quantify does not predict prices, recommend trades, manage portfolios, browse
for extra evidence, or make investment decisions.

## 2. Product Model

```text
Human analyst or external AI agent
  → bounded company analysis
  → one structured LLM extraction
  → deterministic evidence verification
  → safe verdicts and audit record
```

The LLM identifies candidate claims and supplied evidence references. It never
decides truth. Deterministic code owns evidence eligibility, claim semantics,
counterevidence, and final verdict composition.

| Verdict | Meaning |
| --- | --- |
| VERIFIED | Evidence warrants the claim and no compatible evidence defeats it. |
| UNSUPPORTED | The declared evidence does not warrant the claim. |
| DEFEATED | Compatible counterevidence defeats the claim. |
| QUALIFIED | A supported claim requires an important disclosed qualification. |
| REQUIRES_AGENT_RESOLUTION | Ambiguity, invalid grounding, or system failure prevents publication. |

Every result is limited to its named evidence release. No result claims that
contrary evidence does not exist elsewhere.

## 3. High-Level AWS Architecture

```text
Customer or external AI agent
  → Cognito / IAM identity, WAF, API Gateway, admission control
  → stateless regional Quantify verification cell
      → one pinned model adapter
      → deterministic verifier using an approved frozen evidence release
      → atomic cost reservation and encrypted audit manifest
  → safe, non-advisory verification response

Independent offline plane
  → source acquisition and normalization
  → evidence-policy review, evaluation, and immutable release publication

Control and assurance plane
  → tenant limits, release registry, audit retention, observability,
    incident response, and model-quality measurement
```

The online path is synchronous, bounded, and horizontally scalable. The
offline plane creates approved evidence releases but is never reachable from a
customer verification request. The control plane may admit or reject a request
but may not change a verdict.

The deployed V1 uses Lambda containers, API Gateway, Cognito/IAM, DynamoDB,
encrypted S3 audit storage, KMS, Secrets Manager, ECR, and CloudWatch. Future
regional cells must preserve the same versioned evidence, policy, model, and
response contract.

## 4. Non-Negotiable Controls

- One bounded model extraction call per uncached request; no silent fallback,
  retry, or second model agent.
- Immutable evidence releases with explicit policy, source, and manifest
  versions; no live SEC retrieval in the verification path.
- Deterministic verification and counterevidence analysis; models cannot alter
  evidence, policy, or verdict rules.
- Fail closed: malformed output, unavailable model, missing audit storage,
  invalid grounding, or exhausted capacity results in a typed unavailable or
  resolution outcome—not a publication decision.
- Tenant isolation for customer reports, credentials, audit records, usage, and
  quotas. Shared public evidence may be deduplicated.
- Atomic server-side admission and worst-case model-cost reservation before an
  uncached model invocation. API throttles and client keys are not sufficient
  spending controls.
- Audit records include the evidence, policy, engine, prompt, schema, and model
  versions needed to explain a result; they exclude submitted report text.

## 5. Current V1 Scope

V1 verifies a closed set of factual claim types against frozen SEC evidence for
Microsoft and Apple. It supports a private IAM-authenticated core and a narrow
public agent endpoint protected by Cognito scope. The public contract returns
only verdicts, evidence scope, audit reference, and a non-investment-advice
limitation.

For a temporary no-signup test, V1 may additionally expose the same safe
contract at a separate anonymous trial route. It is not a public core route:
CloudFront adds a private origin header, Lambda rejects requests lacking that
header, and admission occurs before the private core call. Admission is
time-bounded, hashes the viewer IP with a deployment secret rather than storing
the raw address, and atomically enforces per-IP, daily-request, and reserved
cost caps. A disabled, expired, malformed, or unavailable ledger fails closed.
The trial must be removed or explicitly renewed before its configured expiry.

V1 is a verification service, not a multi-agent research system, a live-data
terminal, a general chatbot, or a trading system.

## 6. Delivery Plan

| Phase | Outcome | Required gate |
| --- | --- | --- |
| 1. Trust foundation — current | Bounded verifier, frozen evidence, deterministic verdicts, audit manifests, authenticated API. | Safety, replay, container, and controlled-beta checks pass. |
| 2. Commercial control plane | Tenant identity, hard quota/cost admission, usage metering, support, and enterprise audit retention. | Isolation, overload, spend-cap, and security-review tests pass. |
| 3. Evidence-release factory | Controlled issuer expansion through immutable snapshots, provenance validation, policy versions, and evaluation corpora. | Each new issuer/category has explicit policy, fixtures, evaluation, and replay evidence. |
| 4. Regional scale | Independent AWS verification cells, capacity budgets, same-release failover, and recovery testing. | Load, provider-outage, storage-failure, and failover tests preserve the contract. |
| 5. Ecosystem integration | SDKs and tool adapters for enterprise AI and analyst workflows. | Integrations preserve every verdict, scope limitation, and audit reference. |

Phases are sequential. More tenants, evidence, or regions are valuable only
when the previous trust boundary is proven. A roadmap item does not authorize a
new public route, live evidence retrieval, model provider, or deployment.

## 7. Web Application Experience

The public web application is a React and TypeScript single-page application.
The normal mode authenticates human users with Cognito authorization-code flow
and PKCE, and calls only the narrow scoped public agent API. The temporary test
mode does not require sign-in and instead calls only the separately bounded
anonymous trial route through CloudFront. It never contains an AWS credential,
model credential, private-core URL, OAuth client secret, or the CloudFront
origin header.

The private preview uses a separate no-secret browser client. Its callback and
logout URLs are pinned to the preview origin and `http://127.0.0.1:5173/`; the
authenticated API independently enforces the `verify` scope. Submitted
analysis stays in memory for the request and is never added to browser storage,
history, or UI logs. The browser retains an access token only in session
storage when the authenticated mode is used.

```text
Sign in
  → Verify analysis: company, as-of date, bounded analysis text
  → Result: verdicts, review warning, evidence scope, audit reference,
    non-investment-advice limitation
  → Optional history: request metadata and audit references only
```

### Visual direction

Use the supplied HockeyStack page only as visual inspiration, not as a source
for its branding, copy, logos, product imagery, or interface assets. Quantify's
design should feel like a calm, premium enterprise control surface:

- light neutral page canvas, generous white space, and a single rounded main
  content panel;
- restrained black/near-black typography with one high-contrast primary action;
- large, concise headline and plain-language product explanation;
- compact navigation and clearly separated sign-in and primary-action controls;
- verdict cards that prioritize status, evidence scope, audit reference, and
  review-required state over decorative charts or investment-style signals;
- accessible contrast, keyboard navigation, responsive layout, and no color as
  the only indicator of a verdict.

The first screen should ask one question: **“Is this company-analysis claim
supported by the declared evidence?”** It must not imply price prediction,
trading, or personalized investment advice.

Broad browser access is blocked until Phase 2 adds tenant records, atomic
server-side tenant quota/cost admission, rate-limit messaging, a metadata-only
history policy, and a named support/incident workflow. Preview invitations are
operator-managed and are not a substitute for those controls.

## 8. Governance

The user request, `AGENTS.md`, and this specification govern in that order.
Any change to evidence eligibility, counterevidence, verdict semantics, model
contract, or disclosure policy requires focused tests and replay-aware version
updates. Credentials, report text, raw source payloads, and private evaluation
artifacts must not enter source control or public logs.
