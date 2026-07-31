# Quantify AI Agent System Design

## 1. Purpose and boundary

Quantify is a user-first AI research companion for public-company analysis. It
helps people and external AI agents test factual claims, surface
counterevidence, and follow an auditable research trail against a declared,
frozen evidence release.

> A claim may be published only when its cited evidence warrants it and
> compatible evidence in the same declared frozen pool does not defeat it.

Quantify is not a stock-prediction, trading, brokerage, portfolio-management,
or personalized-investment-advice product. It must not make buy, sell, hold,
allocation, position-size, suitability, or trade-execution recommendations.

The agent may plan research and draft explanations. Only the deterministic
verifier may mark a factual claim VERIFIED. This is non-negotiable.

## 2. Current baseline and target

### Current V1

The deployed core is a bounded verification harness with one primary structured
extraction call:

~~~
one pinned structured extraction call
→ deterministic grounding and typed-claim validation
→ deterministic warrant and CE1 counterevidence verification
→ fail-closed verdict composition and immutable audit manifest
~~~

The codebase also contains `AutonomousResolutionLoop`, the V1 precedent for a
policy-bounded agent step: it can make at most one disclosure-assessment action
and then re-run deterministic composition; remaining ambiguity is
REQUIRES_AGENT_RESOLUTION. The production assembly currently configures that
loop with zero actions, so it is a tested safety contract and implementation
precedent, not a live second model call. Future tools must retain its boundary:
bounded action first, deterministic composition last.

The private IAM-authenticated core exposes only:

~~~
GET  /healthz
POST /v1/companies/{cik}/verify
~~~

The safe public edge exposes POST /v1/agent/verify with Cognito scope
enforcement. A separately bounded no-sign-up trial route may serve the same
safe contract through CloudFront. It is not a public core route: it is
origin-header protected, admission-controlled, time-limited, and fails closed.

V1 uses immutable embedded SEC fixtures, Lambda containers, API Gateway,
Cognito/IAM, DynamoDB, encrypted S3 audit storage, KMS, Secrets Manager, ECR,
and CloudWatch in us-east-2. It is not yet a multi-tool research agent, a
live-data terminal, or an async task platform.

### Private research-task pilot foundation

The repository contains an IAM-only research-task pilot foundation. It is not
deployed, exposes no HTTP route, and is intentionally non-consuming by
default: worker reserved concurrency is `0`, no SQS event-source mapping is
present, and the Lambda handler fails closed until an indexed-release worker
composition is installed. This is an infrastructure and adapter boundary, not
authorization to accept or process research tasks.

The foundation includes an encrypted, point-in-time-recoverable DynamoDB task
table; encrypted SQS queue and DLQ; a digest-pinned Lambda image contract; a
30-day worker log group; and alarms for queue age, DLQ depth, worker errors,
and throttles. Its deployment script requires explicit authorization and
restricts the region to us-east-2. No deploy, queue consumption, concurrency
increase, or event-source mapping is authorized merely by the presence of this
foundation.

It also establishes the storage boundary for policy control: a separate,
encrypted, versioned, public-blocked policy-artifact bucket; a separate
encrypted policy-control table; and an asymmetric RSA-4096 KMS SIGN_VERIFY
key. Offline publishers can create signed policy envelopes, while worker-side
verification uses KMS verification and strongly consistent reads of the
independently managed pointers and status records. The runtime policy-control
adapter reloads those records before each authorization decision so a queued
task cannot continue after a policy or evidence release is revoked. The
worker-side code provides no policy-publication operation.

The SQS batch adapter returns only failed message identifiers for retry and
redrive handling; it does not log or interpret malformed message bodies as
research input. The repository now contains a fail-closed indexed-release
worker composition: it rebuilds and verifies the archived exact-fact index,
reloads signed controls, binds all three audit hashes, requires encrypted audit
persistence, and records the digest-pinned worker image. It remains inactive
until active signed artifacts and evidence pointers exist in the target
account, actual capacity is allocated, and the required post-deploy checks
pass.

The target fact index does not create a second verifier. Initially, the async
path will use the existing deterministic engine through an indexed evidence
snapshot adapter that has replay parity with the approved embedded release.
The V1 routes continue reading their embedded fixtures until dual-read replay
tests prove identical verdicts, qualifications, counterevidence, and audit
inputs for that release. Only then may the same versioned snapshot-provider
interface be adopted by V1; its behavior and public contract remain unchanged.

### Target state

The next product is a scalable, no-sign-up research agent with deliberately
bounded capability. It adds policy-governed planning, efficient retrieval,
asynchronous tasks, and a sustainable evidence-release factory while retaining
the V1 verifier as the only verdict authority. Identity, private documents,
workspaces, and enterprise RBAC are later capabilities, not prerequisites for
the user-first product.

## 3. High-level system design

Quantify has three deliberately separated planes:

~~~
Public delivery plane
  Browser / SDK
    → CloudFront + WAF
    → static, versioned release catalog and watchlist manifests in S3
    → bounded public verification and research-task APIs

Online research plane
  API admission → DynamoDB task and cost state → SQS → bounded Lambda worker
    → pinned planner model and typed tools
    → exact fact retrieval / scoped narrative retrieval
    → deterministic verifier → safe response + encrypted audit object

Offline evidence factory
  approved source acquisition → normalization → evaluation → release gate
    → immutable evidence release and compiled indexes → S3/CDN publication
~~~

The public plane never receives model or AWS credentials. The online plane
never fetches live SEC or web content for a user request. The factory is not
reachable from an online request. A control decision may admit, throttle, or
reject work, but it may never alter a verdict.

### 3.1 Two retrieval paths

Structured fact retrieval handles numeric and typed factual claims. Its
compiled key is:

~~~
evidence_release_manifest_hash + CIK + metric + fiscal_period + unit
~~~

It returns exact fact and evidence identifiers and is the only retrieval path
that can feed deterministic verification.

Narrative retrieval is semantic search over normalized disclosure text, such as
MD&A and risk-factor passages. It may provide context for an explanation or
identify a research question. It is filtered to the exact
evidence_release_manifest_hash selected when the task begins. It can never
change a verdict, establish a numeric fact, or expand the release.

### 3.2 Data and delivery

| Need | Primary mechanism | Rule |
| --- | --- | --- |
| Immutable evidence, manifests, evaluations, and audit objects | Versioned encrypted S3 | Address by content hash; retain replay inputs. |
| Public catalog and watchlist refresh | CloudFront-cached S3 JSON | Browsers poll a short-cached index, never Lambda. |
| Facts | Compiled exact fact index | Exact typed lookup, never vector similarity. |
| Narrative context | Release-scoped vector index | Context-only, with source span and chunk hash. |
| Tasks, admission, idempotency, release metadata | DynamoDB | Model access patterns first; reassess relational storage only when justified. |
| Work execution | SQS, Lambda workers, DLQ | Reserved concurrency and bounded failure handling. |

Browser watchlists are local-only CIK and release-ID lists. Quantify does not
collect holdings, risk tolerance, portfolio composition, or behavioral profiles.
Abuse-protection identifiers are HMAC-derived, short-lived, and may not be
joined with feedback or watchlist telemetry.

## 4. Evidence, policy, and audit contracts

Evidence, runtime policy, and release-gate policy are independent, immutable
artifacts with separate publish and approval paths. An urgent policy restriction
must not wait for an evidence release.

Every task and response records three hashes:

~~~
evidence_release_manifest_hash
runtime_policy_bundle_hash
release_gate_policy_hash
~~~

An approved policy bundle is signed, content-addressed, encrypted at rest, and
has a status registry: active, deprecated, revoked, or emergency_disabled. It
defines the pinned planner model/provider/version, secret version, prompt hash,
call and token budgets, tool and source allowlists, prohibited actions,
admission and cache rules, and release-gate thresholds.

A policy-pointer change may tighten controls or disable a tool without a Lambda
deployment. A task reauthorizes policy before every side effect. New work
cannot use revoked policy; queued/running work stops safely; side effects made
by revoked tools stop firing while their audit trail remains. Planner output
from a revoked model/tool policy is never served. A cached deterministic verdict
is served only if the evidence release and current serving policy remain valid.
Revoked evidence is not publicly served, though protected audit records remain.

Audit records preserve source, time, scope, transformation, model, policy,
schema, engine, prompt, and manifest versions needed to explain a result. They
must not include raw user text, credentials, or private operational secrets.

## 5. Agent and task model

The current synchronous POST /v1/agent/verify remains a tight V1 contract. The
scalable agent adds a separate asynchronous surface:

~~~
POST /v1/research-tasks       → 202 Accepted + task_id
GET  /v1/research-tasks/{id}  → state and safe result
POST /v1/research-tasks/{id}/retry
POST /v1/research-tasks/{id}/cancel
~~~

The API canonicalizes requests before admission. One idempotency record maps an
idempotency key, canonical request hash, task, and reservation. Reusing a key
with the same request returns the existing task. Reusing it with different
content returns 409 Conflict and creates no work or cost reservation.

~~~
accepted → admitted → queued → running → completed
                       ↘ requires_review | unavailable | failed_unresolved
~~~

SQS and Lambda workers provide bounded execution. A DLQ captures exhausted
messages. Before an uncached model call, the service atomically reserves
worst-case capacity using deterministically sharded daily/monthly counters.
Public traffic must not bypass admission.

Provider uncertainty is fail-closed but fair:

1. If the provider did not start, reuse or release the reservation as policy permits.
2. If state is ambiguous, run delayed adapter reconciliation where attributable usage/result lookup exists.
3. Recover result/cost when completed, or reservation when not started.
4. If unresolved, never auto-retry or switch model; record failed_unresolved.
5. A user or operator may request one controlled retry linked to the original task and reservation. It is separately admitted and audited.

The first implementation slice has one typed tool, verify_claims. Add tools only
after narrow contracts and evaluations pass: search_approved_evidence_release,
create_review_task, release-scoped narrative context, then watchlist alerts.
The planner cannot call arbitrary URLs, inspect private documents, alter policy,
write a verdict, trade, or access live filings.

The private pilot foundation implements only the SQS batch-adaptation and
control-plane boundaries described above. It does not implement the
indexed-release worker composition or authorize any asynchronous HTTP surface.
The V1 public and private verification routes remain the only active product
contracts until the prerequisites in Section 8 are satisfied and separately
authorized.

## 6. Safe results and provenance

Every visible statement is labelled verified fact, qualification,
counterevidence, agent inference, open question, or review required.

A structured fact citation carries source_type structured_fact, verification_role
verdict_evidence, release hash, filing/accession, fact ID, and evidence ID. A
narrative citation carries source_type narrative_disclosure, verification_role
context_only, release hash, filing/accession, chunk hash, and source span. It is
visibly issuer-disclosure context, not independent verification.

Every agent inference and open question includes derived_from citation IDs. This
allows users to trace reasoning inputs without turning an inference into a
verdict.

| Verdict | Meaning |
| --- | --- |
| VERIFIED | Exact declared evidence warrants the claim and no compatible evidence defeats it. |
| UNSUPPORTED | Declared evidence does not warrant the claim. |
| DEFEATED | Compatible counterevidence defeats the claim. |
| QUALIFIED | The claim is supported only with an important disclosed qualification. |
| REQUIRES_AGENT_RESOLUTION | Ambiguity, invalid grounding, or unavailable information prevents publication. |

No conclusion asserts that contrary evidence does not exist outside the named
release.

## 7. Evidence-release factory and coverage

An issuer becomes available only through a controlled factory:

~~~
licensed/approved sources → normalize and validate
→ compile facts and narrative chunks → evaluation corpus
→ release gate → immutable manifest → CDN catalog
~~~

The factory, not Lambda concurrency, is the real scalability constraint. It
measures issuer coverage, automated pass rate, review exceptions, correction
rate, source freshness, and reviewer throughput. These same explicit metrics
are both the release gate and the operating dashboard.

- Lane A — routine release: existing issuer/schema and all policy thresholds pass, with automated checks and approved spot review.
- Lane B — full review: new issuer, source/type, restatement, failed critical evaluation, or threshold breach; explicit reviewer approval is required.

Sources must be licensed or public and frozen into a release before public use.
Live retrieval belongs only to the offline factory, never the verifier or
planner request path.

## 8. Implementation plan

This is an ordered plan, not a timing promise. Build and test each step before
relying on the next.

1. **Policy-control and pilot foundation — partially implemented, inactive.** The repository contains signed-envelope types, an offline KMS signing boundary, a KMS verification boundary, content-addressed artifact loading, a strongly consistent DynamoDB policy-control reader, and a reload-on-authorization policy facade. The private pilot template creates the isolated storage, signing, queue, worker, and alarm resources but defaults worker concurrency to zero and configures no event source. Remaining work: separately authorize and operate an offline publication path; publish active runtime and release-gate artifacts plus evidence status/pointers; verify actual KMS/S3/DynamoDB access in the target account; populate all three audit hashes; and test emergency disable without code deployment.
2. Compile the exact fact and release-scoped narrative indexes for one approved release. Test exact matching, manifest filtering, and that narrative output cannot enter verdict evaluation.
3. **Async worker boundary — partially implemented, inactive.** Canonical hashing, idempotency collision rejection, sharded admission, bounded queues, task state, SQS batch failure reporting, and the fail-closed indexed worker composition exist as code-level boundaries. The archived provider rebuilds the exact-fact and context-only narrative indexes and proves their hashes before it can serve a task. Before activation, publish and select an actual approved indexed release; prove dual-read replay parity with the embedded release for its full approved corpus; configure an authorized event-source mapping and bounded concurrency; and run the private post-deploy checks. Keep V1 on embedded fixtures until parity proves identical verdicts, qualifications, counterevidence, and audit inputs.
4. Prove failure/recovery semantics: provider-not-started, completed, ambiguous, reconciliation-unavailable, manual retry, cancellation, and reservation reconciliation. No automatic model retry or fallback.
5. Load and abuse test public access: sharded hard caps, burst behavior, queue saturation, WAF/rate enforcement, cache behavior, and telemetry separation. Do not expose a research-task route until these tests and an explicit authorization approve it.
6. Operationalize the factory: source validation, normalization, evaluations, Lane A/B gate records, immutable manifests, CDN catalog publication, rollback/revocation tests, and reviewer workflow.
7. Add approved-release search, review tasks, and narrative context one at a time. Each needs a typed contract, policy allowlist, evaluation, provenance, and revocation test.
8. Expand issuer coverage according to measured release-factory throughput; maintain SDK/tool adapters that preserve the safe contract. Reassess storage only from observed query patterns.
9. Treat accounts, uploads, workspaces, RBAC, retention, legal hold, and private-data classification as a separate institutional program.

### 8.1 Institutional private-data prerequisite

Before any account, workspace, upload, or private-source route is exposed,
publish a versioned private-data policy defining data classes, retention,
deletion, legal hold, workspace ownership, role permissions, audit fields,
incident response, and access-review cadence. Private material is isolated by
workspace and may never enter a public evidence release, public catalog,
public telemetry, or a deterministic verdict unless a separately versioned
private-evidence contract explicitly permits it. Initial implementation may
provide only internal policy and authorization primitives; it must not imply
authorization to accept private material.

## 9. Web experience

The visual direction describes the target public experience. The deployed web
already uses the soft-white and Quantify-purple direction; task-progress UI,
release selection, and the richer citation presentation arrive with the async
task work above.

The web asks one question: “Is this company-analysis claim supported by the
declared evidence?” It shows task progress or a bounded result, evidence scope,
qualifications, counterevidence, citations, and an audit ID.

Use a soft-white canvas with the Quantify purple gradient as the primary brand
color, large clear type, and a calm technology-product layout. Show scope and
review-required states as prominently as favorable outcomes. Avoid
market-terminal imagery and price-prediction cues; never use color alone to
convey a verdict.

No-sign-up access is intentional for this phase but remains bounded by policy,
WAF, sharded admission, and cost caps. Controls fail closed. Future accounts
must not change the evidence or safety contract.

## 10. Governance

The user request, AGENTS.md, and this specification govern in that order.
Changes to claim semantics, evidence eligibility, counterevidence, verdict
composition, disclosure, model contract, source use, policy behavior, or release
gates require versioned contract updates, focused tests, and replay-aware audit
fields.

Do not deploy, purchase data, contact customers, publish a release, or expose a
new public route without explicit user authorization. Credentials, user text,
private source payloads, and private evaluation artifacts must not enter source
control or public logs.
