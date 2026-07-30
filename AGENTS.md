# AGENTS.md

## Purpose

This repository builds **Quantify Research Referee**, a user-first AI research
agent for public-company analysis. Its authoritative product semantics,
architecture, API plan, policy rules, release lifecycle, and UI direction live
only in [quantify_spec.md](quantify_spec.md). Do not duplicate or reinterpret
those rules here; update the specification first when they change.

Quantify is not a stock-prediction, trading, brokerage, portfolio-management,
or personalized-investment-advice product. Do not add price predictions, buy,
sell, hold, allocation, position sizing, suitability, or trade execution.

## Agent harness

Work inside the boundaries defined in specification sections 1, 3–7, and 10.
The essential invariant is:

~~~
model proposes structured work
→ deterministic code validates grounding, type, warrant, and counterevidence
→ deterministic verifier alone composes the publication verdict
~~~

Only exact structured facts from the declared release can feed a verdict.
Narrative retrieval is context-only and must never establish a fact, broaden
evidence scope, or alter a verdict. Treat model output and external data as
untrusted until validated. Every result must state scope; an empty verified set
is valid. Do not invent facts, confidence intervals, citations, provenance, or
evidence IDs.

The existing AutonomousResolutionLoop is the local pattern for any bounded
agent capability: an explicitly permitted action is capped, replay-visible, and
followed by deterministic composition. In production it is currently configured
for zero actions; do not enable it or add a new action without the specification
contract, focused tests, and explicit authorization where required.

## Current operational boundary

This section intentionally restates the deployed route and release boundary.
It is a non-bypassable operational check for every agent action; all other
architecture and product semantics remain specification-only.

The deployed V1 private core permits only:

~~~
GET  /healthz
POST /v1/companies/{cik}/verify
~~~

The public edge has the safe POST /v1/agent/verify contract and a separately
bounded CloudFront-origin-protected no-sign-up trial route. Neither exposes the
core, performs live SEC retrieval, or can alter a verdict. Deployed systems are
single-region us-east-2 Lambda/API Gateway/Cognito/IAM/DynamoDB/S3 systems.

Treat future architecture in the specification as a plan, not an implicit
deployment authorization. Do not add public endpoints, live sources, providers,
accounts, data purchases, or deployments without explicit user authorization.

## Authority and working approach

Resolve conflicts in this order:

1. The user's explicit request.
2. This AGENTS.md.
3. quantify_spec.md.
4. Versioned schemas, policies, manifests, fixtures, and evaluation cases.
5. Existing code and tests.

Make reasonable, reversible assumptions and state material ones in the
handoff. Ask before a decision changes user-facing policy, security, cost, data
rights, or external commitments. Do not make releases, deployments, purchases,
customer contact, or destructive data changes without explicit authorization.

## Engineering and change discipline

- Preserve boundaries between presentation, orchestration, adapters,
  deterministic verification, evidence acquisition, and policy enforcement.
- Follow the contracts and controls in quantify_spec.md rather than copying
  them here. Changes to claim semantics, evidence eligibility,
  counterevidence, disclosure, model/tool contract, source use, policy,
  release gates, or cache/revocation behavior require a specification update,
  versioned contract update, and focused tests.
- Preserve deterministic replay: record the release, policy hashes, model and
  prompt contract, schemas, engine version, and relevant input hashes.
- Fail closed for malformed model output, invalid grounding, unavailable model,
  missing required audit storage, invalid policy, expired release, or exhausted
  capacity. Never add an unrecorded fallback model.
- Test in proportion to risk. Include the negative and failure cases the
  specification calls for; do not claim checks that did not run.
- Protect credentials, user text, private reports, private sources, and
  evaluation artifacts from logs, fixtures, commits, and handoffs.
- Before every handoff, remove macOS AppleDouble metadata files (._*) created
  in the repository; they are never project artifacts.

## Delivery lifecycle

~~~
DEFINE → PLAN → BUILD → VERIFY → REVIEW → SHIP
 idea     spec    code    test     QA      go live
~~~

Use the appropriate stage, preserve completed work, and return to an earlier
stage when evidence requires it. A handoff states the outcome, key decisions,
verification actually performed, and remaining risks. A change is ready only
when it meets its requested outcome without weakening the specification or this
harness.
