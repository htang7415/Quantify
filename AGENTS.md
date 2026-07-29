# AGENTS.md

## Purpose

This repository builds **Quantify Research Referee**: a system that audits
AI-generated or human-written public-company analysis against a declared pool
of evidence. The authoritative product specification is
[quantify_spec.md](quantify_spec.md).

Quantify's central promise is deliberately conservative:

> A claim may be published only when its cited evidence warrants it and
> compatible evidence in the same declared frozen pool does not defeat it.

The system is an evidence verifier, not a stock-prediction, trading, brokerage,
or personalized-investment-advice product.

## Current system and next plan

Quantify Core is complete and has passed its frozen-corpus technical readiness
gate. The production design is a **single-turn AI verification harness**:

```text
one bounded structured extraction call
→ deterministic grounding and typed-claim validation
→ deterministic warrant and CE1 counterevidence verification
→ fail-closed verdict composition and audit manifest
```

It is not a multi-agent research system. Private staging is model-enabled:
each uncached verify request makes one pinned Gemini extraction call, supplied
from Secret Manager at runtime. The production profile has no secondary model
path; ambiguity becomes `REQUIRES_AGENT_RESOLUTION`. Model unavailability
fails closed and must not cause an unrecorded model fallback.

The current engineering plan is §14 of `quantify_spec.md`: prepare a private,
IAM-authenticated Google Cloud Run staging service with immutable embedded SEC
fixtures. The deployed allowlist is only:

```text
GET  /healthz
POST /v1/companies/{cik}/verify
```

Production application assembly, dynamic container QA, and private staging
configuration are complete: embedded-fixture-only evidence, semantic-duplicate
claim collapse, startup validation, enforced route allowlist, locked non-root
image, immutable image/secret configuration, and authenticated smoke tooling.
Google Cloud bootstrap and an immutable image build are complete. The next
work is adding Secret Manager version `1`, then separately authorizing a
private staging deployment and staging smoke call. The first Cloud Run revision
is IAM-private staging traffic only; later candidate revisions begin at zero
traffic. Live SEC retrieval
must be unreachable from the deployed request path. Do not deploy, promote
traffic, or publish a release without the corresponding explicit user
authorization.

## Working approach

Use sound engineering judgment to develop, improve, and extend the product.
Choose appropriate architecture, tools, dependencies, tests, and implementation
order for the task at hand. Prefer small, understandable changes, but do not
let an earlier prototype or this guide prevent necessary construction,
refactoring, or integration work.

When requirements are incomplete, make reasonable, reversible assumptions and
state material ones in the handoff. Ask for direction only when a choice would
meaningfully change product behavior, user-facing policy, cost, security, or
external commitments.

Do not make external releases, deployments, purchases, customer contact, or
destructive data changes without explicit authorization.

## Authority

Resolve conflicts in this order:

1. The user's explicit request.
2. This `AGENTS.md`.
3. `quantify_spec.md`.
4. Versioned schemas, policies, manifests, fixtures, and evaluation cases.
5. Existing code and tests.

The specification owns product semantics. If code, a request, or a proposed
implementation conflicts with a core safety or verification rule, explain the
conflict and preserve the stronger rule unless the user explicitly changes it.

## Product principles

- Treat evidence scope honestly. Verdicts apply to the declared snapshot or
  corpus; they do not establish that no contrary evidence exists elsewhere.
- Preserve an auditable separation between evidence acquisition/interpretation
  and deterministic verification. The verifier, not a model, decides whether a
  factual claim is eligible for publication.
- Keep local support and counterevidence distinct. Defeating evidence remains
  visible even when a report acknowledges it.
- Be conservative with ambiguity. Invalid grounding, unsupported claim types,
  uncertain disclosure, or incomplete information should produce a clear review
  path rather than an overconfident negative finding.
- Do not invent financial observations, confidence intervals, provenance, or
  evidence IDs. Preserve the source, time, scope, transformation, and policy
  context needed to interpret an observation.
- Make point-in-time and restatement choices explicit and reproducible.
- Preserve deterministic replay wherever deterministic verdicts are claimed:
  freeze relevant inputs, version policies and schemas, and record manifest
  information sufficient to explain a result.
- Keep user-visible conclusions proportional to the available evidence. An empty
  verified-result set is valid.

## Engineering expectations

- Design clear boundaries between domain semantics, deterministic verification,
  external adapters, orchestration, and presentation. Avoid letting provider or
  interface concerns silently redefine verification behavior.
- Treat model output and external data as untrusted until validated. Validate
  structured output, report grounding, and references before relying on them.
- Use real, attributable source data for financial assertions and frozen
  fixtures for reproducible tests when suitable.
- Test behavior in proportion to risk. Include regression coverage for semantic
  changes and generative/property tests where invariants benefit from them.
- Keep evaluation categories distinct when they measure different behavior (for
  example, mechanical versus judgment cases, or deterministic engine behavior
  versus model extraction quality).
- Do not claim tests, checks, or guarantees that were not actually performed.
- Protect credentials, private report content, and sensitive operational data in
  logs, fixtures, commits, and handoffs.
- Before every handoff, remove any macOS AppleDouble metadata files (`._*`)
  created in the repository; they are never project artifacts.

## Change discipline

For changes that alter claim semantics, evidence eligibility, restatement
handling, counterevidence, verdict composition, or disclosure policy, update
the relevant versioned contract and add focused tests. Record replay-relevant
versions and hashes in audit output when applicable.

For routine implementation work, avoid ceremony that does not improve the
outcome. Leave the repository clearer, safer, and easier to evolve than you
found it.

## Delivery lifecycle

Use this lifecycle as a shared framework for moving work from idea to release:

```text
DEFINE → PLAN → BUILD → VERIFY → REVIEW → SHIP
 idea     spec    code    test     QA      go live
```

Enter at the stage appropriate to the request and preserve work already done.
The `/spec`, `/plan`, `/build`, `/test`, `/review`, and `/ship` labels describe
the intent of each stage; they do not require a particular command, document,
or level of ceremony.

- **Define:** establish the problem, scope, constraints, and success criteria.
- **Plan:** choose a viable approach, interfaces, risks, and verification.
- **Build:** implement the agreed outcome.
- **Verify:** run relevant tests, checks, and practical validation.
- **Review:** assess correctness, quality, safety, and readiness.
- **Ship:** commit, release, deploy, or otherwise hand off only with the
  required authority.

Use feedback naturally: a failed test returns work to Build; a review finding
may return it to Build or Plan; a scope conflict returns it to Define. This is a
guide for clear collaboration, not a constraint against direct, iterative work.

## Completion

Complete work with a concise handoff covering the outcome, important decisions,
verification performed, and any remaining risks or follow-up. A change is ready
when it fulfills the requested outcome without undermining the product
principles above.
