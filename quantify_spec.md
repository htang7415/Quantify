# Quantify AI Agent System Design

## 1. Purpose and boundary

Quantify is an evidence-bound AI investment research agent for individual
investors, professional research teams, institutions, and people learning how
companies, markets, and policy connect. It turns released financial, company,
ownership, earnings, macroeconomic, rates, policy, and eventually entitled news
data into inspectable information, typed intelligence, cited analysis, and
claim verification.

The product has four distinct output layers:

1. **Data.** Versioned, time-stamped records with source, methodology,
   freshness, rights, correction, and release state.
2. **Intelligence.** Exact entity, period, ownership, earnings, market, and
   policy connections derived only from compatible released records.
3. **Analysis.** Plain-language comparisons, explanations, drivers,
   counterpoints, and open questions produced from cited facts and labelled
   context. Analysis is model-assisted and remains untrusted until its factual
   statements and citations pass deterministic validation.
4. **Verification.** Claim-level verdicts composed only by the deterministic
   verifier from eligible exact facts in the declared evidence release.

Verification is Quantify's trust layer, not its entire product. An analysis may
help a user understand evidence without assigning a verdict. A verification
result may be embedded in a broader research answer, but the model can never
create, modify, soften, or override that verdict.

Two terms keep that boundary clear. **Automatic factual validation** is the
always-on validation of scope, grounding, statement type, citations,
derivations, prohibited content, policy, and audit bindings for every safe
research answer; it does not produce a verdict. **Explicit claim
verification** is the user-selected agent function that evaluates a bounded
claim and returns a verdict composed only by the deterministic verifier.

Quantify may also publish a read-only investor-tracking catalog compiled
offline from approved public disclosures. Catalog metrics describe the exact
declared filing scope and are not verification verdicts, total assets under
management, personal holdings, or claims about an investor's intent.

Quantify may publish additional read-only company, company-ownership, market,
macro, ETF, cryptocurrency, earnings, policy, event, and entitled news catalogs
only after their source rights, methodology, freshness rules, correction path,
and release gate are defined. These catalogs are time-stamped research data,
not live trading feeds, predictions, recommendations, or verification verdicts.
Until an approved release exists, the public web shows an explicit unavailable
state and does not substitute example, cached-out-of-policy, or model-generated
values.

> A claim may be published only when its cited evidence warrants it and
> compatible evidence in the same declared frozen pool does not defeat it.

Quantify is not a stock-prediction, trading, brokerage, portfolio-management,
or personalized-investment-advice product. It must not make buy, sell, hold,
allocation, position-size, suitability, or trade-execution recommendations.

The agent may scope a question, plan research, retrieve approved releases,
request deterministic calculations, compare compatible facts, draft cited
analysis, surface counterpoints, and identify open questions. Only the
deterministic verifier may mark a factual claim VERIFIED. This is
non-negotiable.

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

The repository also contains the local, provider-free
`research-answer.v1` schema and deterministic validator. The validator accepts
only an independently admitted scope, exact authorized citation records,
calculation inputs, interpretation warrants, model attribution, verifier
results, and audit identity; it returns a detached canonical document or a
typed fail-closed error. It is not connected to a model composer, worker, API,
or public submission surface and therefore does not make model-assisted
analysis available.

Regional placement is explicit. `us-east-2` is the sole V1 operating region
for compute, APIs, identity, queues, databases, evidence and audit storage,
policy control, logs, and regional alarms. CloudFront is global; its required
WAFv2 Web ACL, WAF metrics, and any WAF-block notification topic/alarm are the
narrow AWS-required exception and are managed in `us-east-1`. That global
control-plane exception stores no Quantify evidence, audit, policy, identity,
or user-request content and must not be used to introduce a second operating
region. Deployment configuration names the primary region `AWS_REGION` and
the exception `CLOUDFRONT_WAF_REGION` so a WAF deployment cannot silently
redirect regional application resources.

### Private research-task pilot foundation

The repository contains an IAM-only research-task pilot foundation. Its
template defaults to non-consuming operation: worker reserved concurrency is
`0`, no SQS event-source mapping is present, and the Lambda handler fails
closed until an indexed-release worker composition is installed. The private
pilot in us-east-2 was later activated under explicit authorization with
reserved concurrency and mapping maximum both bounded at `2`, one selected
frozen release, signed controls, offline IAM-only admission, and no HTTP
route. This activation is not authorization for a public asynchronous surface.

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
by default until active signed artifacts and evidence pointers exist in the
target account, actual capacity is allocated, and the required post-deploy
checks pass. The authorized private pilot has satisfied those prerequisites;
any additional environment needs its own authorization and checks.

The target fact index does not create a second verifier. Initially, the async
path will use the existing deterministic engine through an indexed evidence
snapshot adapter that has replay parity with the approved embedded release.
The V1 routes continue reading their embedded fixtures until dual-read replay
tests prove identical verdicts, qualifications, counterevidence, and audit
inputs for that release. Only then may the same versioned snapshot-provider
interface be adopted by V1; its behavior and public contract remain unchanged.

### Target state

The next product is a scalable, no-sign-up investment research agent with
deliberately bounded capability. It unifies released data, typed intelligence,
cited analysis, and verification through policy-governed planning, efficient
retrieval, asynchronous tasks, and a sustainable evidence-release factory while
retaining the V1 verifier as the only verdict authority. Identity, private
documents, workspaces, and enterprise RBAC are later capabilities, not
prerequisites for the user-first product.

### Commercial product direction

Quantify's commercial direction is an **evidence-bound investment intelligence
system** for company, market, ownership, macroeconomic, policy, and event
research. It competes on integrated research workflow, reproducibility,
controlled evidence, source-visible AI analysis, review, and auditability—not
on generic chat, terminal-scale breadth, price prediction, trade
recommendations, or autonomous portfolio action. Every factual statement and
verification result remains attributable to its declared release, source,
runtime/release-gate policies, deterministic-engine version, and applicable
model/prompt contract.

The product develops in four independently governed layers:

~~~
Research workspace
  → explore data, ask, analyze, compare releases, verify, review, and export

Evidence-release platform
  → approved sources, issuer coverage, corrections, revocation, citations

Bounded research workflow agents
  → search approved data, calculate, compare, draft cited analysis,
    verify claims, and create review tasks
  → never compose a publication verdict

Enterprise trust control plane
  → deterministic verifier, policy, provider attribution, audit,
    workspace isolation, RBAC, retention, and legal hold
~~~

The public audience includes individual investors and learners who want to
understand released evidence. The initial paid audience remains professional
research, corporate strategy, investor-relations, consulting, and
compliance-sensitive institutional teams. Quantify does not provide
personalized investment advice. Commercial packaging may differentiate
released-data coverage, cited analysis, verification, team workflow, safe API
access, and enterprise controls; it must never charge for, incentivize, or
imply a trading recommendation.

Scale uses two distinct execution lanes. The interactive lane serves bounded,
low-latency verification under admission and cost caps. The offline lane runs
approved issuer onboarding, historical backfills, evaluation campaigns, and
correction scans through attributable asynchronous provider jobs. Provider
attempt records bind Quantify task IDs to provider operation IDs, model and
prompt contracts, immutable input/output references, status history, and
attributable usage where available. Provider results are untrusted until they
pass deterministic validation; a missing or unattributable result fails closed
and never triggers an automatic model retry or fallback.

### Commercial roadmap

This is a milestone roadmap, not a timing promise or authorization to expose a
route, acquire data, accept private material, make a regulated service claim,
or deploy a future capability. Each stage retains the system invariant in this
specification and passes its stated release, policy, evaluation, security, and
operational gates before the next stage is relied upon.

1. **Trust foundation — current private-pilot stage.** Complete the
   deterministic referee, signed policy and evidence releases, attributable
   provider attempts, bounded workers, recovery/replay proof, encrypted audit,
   and private delivery controls. An LLM may propose structured research work;
   it never establishes a fact or composes a publication verdict.
2. **Integrated investment research product.** Deliver an evidence-backed
   company and market research workspace for individuals, learners,
   professional research, strategy, investor-relations, consulting, and
   compliance-sensitive teams. It supports released-data exploration, typed
   intelligence, approved-source analysis, release comparison, claim
   verification, review, and export. Evidence scope, interpretation,
   qualification, counterpoints, citation, unavailable data, and audit identity
   are visible in every result.
3. **Research platform.** Deliver bounded APIs, SDKs, and typed tools for
   customer applications. All requests remain subject to identity,
   authorization, tenant boundaries, source entitlements, admission/cost caps,
   policy, provenance, evaluation, and revocation. Customer systems may make
   their own decisions; Quantify must not present a response as personalized
   investment advice or an instruction to trade.
4. **Broader investment-intelligence workflows.** Add separately evaluated
   workflows for disclosure, company, ownership, earnings, market, macro,
   policy, regulatory, competitive, event, and entitled news research.
   The shared knowledge layer is time-versioned and permission-aware: every
   fact, definition, policy, legal or institutional source, and correction has
   a source, effective period, release/version, entitlement, warrant status,
   and revocation path. RAG remains context-only; released, deterministically
   validated facts are the only facts eligible to affect a published verdict.
5. **Enterprise trust cloud.** Deliver the institutional program for private
   workspaces, RBAC, private-data connectors, retention, deletion, legal hold,
   customer-managed policy controls, model/provider attribution, evaluation,
   and audit export. This stage begins only after the private-data prerequisite
   in section 8.1 and the required security, data-rights, and contractual
   approvals are satisfied.
6. **Specialized deployments.** Consider distinct, separately governed offers
   for regulated financial institutions and government users. Such offers are
   not extensions of the public product by default: each requires its own
   permitted use cases, source rights, deployment boundary, supervision,
   security review, procurement, legal analysis, and explicit authorization.

The durable architecture across all stages is:

~~~
authoritative, time-versioned data and policy
  → released facts, typed intelligence, and scoped narrative context
  → LLM planner with bounded, typed tools
  → deterministic factual/citation validation
  → cited research answer and, when requested, deterministic verifier result
  → workspace, API, or customer workflow
  → human or customer-owned consequential decision
~~~

Quantify's defensible advantage is the combination of attributable evidence,
deterministic policy enforcement, correction and replay, entitlement-aware
access, and measurable quality/cost/latency/failure controls. Data collection
or RAG alone is not sufficient. The initial commercial wedge remains
professional research and business teams; retail advice, proprietary trading
and execution, and government operations remain separate programs rather than
one undifferentiated first product.

### Commercial positioning and initial wedge

Quantify is a public research product with professional and institutional
**verifiable research and decision-workflow** offerings. It is not positioned
as a cheaper financial data terminal, a generic financial chat interface, or a
system that predicts prices or recommends trades. Established data and research
platforms validate demand for integrated AI-assisted financial research, but
their existence does not weaken the need for a provider-neutral control layer
that can make research output reviewable, reproducible, policy-aware, and
attributable.

Public workflows serve individual investors and learners without collecting a
portfolio, risk tolerance, or suitability profile. Initial paying users are
professional research, corporate strategy,
investor-relations, consulting, and compliance-sensitive teams. Initial
commercial workflows are deliberately narrow and measurable:

1. verified SEC and company-disclosure research;
2. earnings, disclosure-change, competitor, and policy-impact research;
3. reviewable reports and exports with evidence scope, qualifications,
   counterevidence, citations, and audit identity; and
4. safe APIs and typed tools for customers that need the same controls in
   their own applications.

Commercial value comes from reducing time to a reviewable answer while making
its basis inspectable and recoverable. Product evaluation therefore measures
grounded-fact accuracy, warranted conclusion accuracy, counterevidence
coverage, citation/provenance completeness, reviewer overturn rate, correction
handling, reproducibility, latency, and attributable cost. A speed or
engagement metric alone cannot establish product quality.

Licensed, customer-provided, and public sources remain distinct entitlement
classes. Quantify must neither imply rights to a source nor use a customer or
licensed source outside its recorded terms. Any future integration with a data
provider, execution system, adviser, regulated financial institution, or
government entity requires a separately approved data-rights, legal, policy,
and deployment review.

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
| Investor holdings catalog | Immutable, versioned 13F release JSON in S3 | Compile offline from approved filings; label period, filing, scope, and limitations. |
| Venture relationship catalog | Immutable, versioned official-source release JSON in S3 | Compile offline from reviewed public firm portfolio pages; publish only declared relationships and explicitly disclosed fields. |
| Company ownership views | Deterministic projection of released investor catalogs | Sum only the tracked disclosed rows; never label the result total institutional ownership. |
| Market, macro, ETF, and cryptocurrency catalogs | Immutable, versioned release JSON in S3 | Acquire offline from approved sources; publish observation time, methodology, freshness, and limitations. |
| Earnings, policy, and event catalogs | Immutable, versioned release JSON in S3 | Separate reported facts from labelled scenarios or inferences; preserve effective dates and corrections. |
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

### 4.1 Account, authorization, entitlement, and persistence contracts

Accounts are a future access layer around the same released-data and safety
contracts; authentication must never change evidence eligibility, factual
validation, or verdict composition. The intended access levels are:

1. **Public:** approved marketing, methodology, coverage, and selected released
   research without an account.
2. **Registered:** released data, permitted news and events, bounded agent use,
   and saved research only after those capabilities are separately authorized.
3. **Professional:** approved expanded coverage, briefs, watchlists, exports,
   and higher limits under an active plan.
4. **Institutional:** workspaces, role-based access, entitled or private
   sources, review workflows, and audit export under the private-data gate.

The current Cognito machine client and administrator-created user-pool boundary
are not human sign-up authorization. A future human web or mobile client uses
authorization code with PKCE, has no client secret, verifies account ownership,
and remains separate from machine credentials. MFA may be optional for
registered and initial professional users. It is required for institutional
owners and administrators, and step-up authentication is required before
member or role changes, entitlement administration, private-source access,
audit export, legal-hold actions, organization deletion, or security-setting
changes.

Authentication answers who the principal is; authorization answers what that
principal may do now. All application authorization passes through one
explicit, testable interface rather than endpoint-specific role checks:

~~~
authorize(principal, workspace, action, resource, entitlement, policy_pointers)
  → allow | deny(reason_code, next_safe_action)
~~~

The interface denies by default and binds the current principal, workspace,
membership, role, subscription, source entitlement, resource tenant, release
state, and signed policy pointers. A token claim may narrow access but can
never expand it. Every decision resolves against authoritative server-side
state. Read-heavy surfaces may satisfy that resolution from a server-side
authorization cache with an approved single-digit-second TTL and no client-side
authority; entitlement, membership, subscription, policy, and release-change
events explicitly invalidate affected entries. A missed invalidation is bounded
by that TTL. Security-sensitive actions, queued-task continuation, each tool
action, exports, private-source reads, and administrative mutations bypass the
cache and re-read authoritative state. If required state or invalidation
controls are unavailable, authorization fails closed.

Persistence remains purpose-specific rather than one overloaded database:

- Cognito stores authentication credentials and recovery state.
- Bounded-domain DynamoDB tables store account profiles, workspaces,
  memberships, entitlements and subscriptions, Library metadata, task
  ownership metadata, and usage/admission ledgers. Every tenant-owned key and
  authorization lookup binds a workspace or account partition.
- Versioned encrypted S3 stores immutable releases, licensed source objects
  when rights permit, generated report objects, and pseudonymous audit objects;
  DynamoDB stores their hashes, ownership, lifecycle state, and authorization
  metadata rather than large content bodies.
- Exact fact and context indexes remain compiled, release-bound projections;
  they are not account databases.

Raw payment credentials are never stored by Quantify. A relational database is
not added preemptively; it is reconsidered only when measured access patterns
require relational constraints, multi-entity transactional workflows, or
analytics that bounded DynamoDB models cannot safely and economically support.
Any future authorization engine, including a managed policy service, must
implement the same central interface so adoption is an adapter change rather
than an endpoint rewrite.

Entitlement is evaluated both when content is created and whenever it is
served, opened from Library, exported, or used by an agent tool. Library
records separate public released facts, user-authored notes, licensed-source
references or excerpts, context-derived analysis, and audit metadata. Library
storage references licensed material instead of copying it as unrestricted
content. When a source entitlement expires or is revoked, the default is to
retain permitted public facts and metadata, hide licensed excerpts and source
objects, block export, and hide dependent analysis unless the source contract
explicitly permits continued display. Each source must define expiry,
revocation, saved-view, excerpt, derivation, export, correction, and deletion
behavior before its Library schema freezes.

Paid-plan state is an authorization input, not a UI flag. The subscription
lifecycle must define trial, active, grace, past-due, suspended, cancelled,
refund, reactivation, and plan-change behavior; a grace state grants access
only when an approved policy says so. A lapsed plan fails closed using the same
serve-time checks and user-facing access grammar as a revoked data entitlement.
Billing-provider references may be stored, but payment secrets may not.

Account deletion and immutable audit use separate identities. Audit records
contain an opaque pseudonymous principal surrogate and no email, name,
credential, unnecessary raw content, or payment secret. A separately protected
mapping binds that surrogate to the mutable account. A deletion request
immediately disables the account, revokes sessions and entitlements, removes
memberships, deletes or anonymizes mutable account and Library data on the
approved schedule, and destroys the mapping when retention and legal-hold rules
permit. Only the minimum approved pseudonymous audit record remains for its
defined retention period; immutable means unaltered during that period, not
retained forever.

Workspace lifecycle is explicit. A sole owner cannot complete ordinary account
deletion until ownership is transferred or an approved workspace-dissolution
flow completes. If the owner is abruptly disabled, or an institutional
subscription lapses, the workspace freezes rather than silently transferring
or deleting data; an approved recovery, retention, legal-hold, and notification
policy determines the next action. No support process may improvise ownership.

The following versioned decision artifacts must pass product, legal, privacy,
security, and data-rights review as applicable before account, workspace,
entitlement, subscription, or Library schemas freeze:

1. account and workspace lifecycle policy, including orphaned-workspace
   transfer, freeze, dissolution, recovery, retention, and notification;
2. licensed-content and Library lifecycle policy;
3. audit retention, legal hold, export, erasure, and pseudonymization policy;
4. anonymous-task ownership and expiry contract;
5. central authorization contract and denial reason registry;
6. authentication-assurance and step-up policy; and
7. subscription, billing-reference, grace, downgrade, and entitlement
   lifecycle policy.

Until those artifacts approve a more permissive outcome, licensed content,
account deletion, workspace recovery, subscription lapse, and entitlement
uncertainty use the fail-closed defaults above. This section freezes the design
boundary; it does not authorize self-registration, billing, private-data
intake, licensed-news acquisition, a new route, or deployment.

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

For a no-sign-up research task, creation returns an opaque, high-entropy,
short-lived task capability with the task ID. The service stores only a
one-way hash of that capability. Status, retry, and cancel require both values,
use constant-time comparison, and return an indistinguishable not-found result
when either is invalid or expired. A retry inherits the same still-valid
capability for its linked task; no raw capability is placed in an audit record,
log, queue message, cache key, or idempotency record. Cognito-principal task
access is a separate future contract and does not weaken this boundary.

Anonymous tasks are permanently unowned in the first account release. Signing
in cannot claim or attach an earlier capability-bound task; the user starts a
new authenticated task instead. A future transfer contract requires separate
authorization, proof of capability possession, capability rotation, explicit
consent, duplicate-ownership prevention, expiry handling, and an audit record.

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

The first implementation slice has one typed tool, `verify_claims`. The bounded
investment-research sequence adds tools only after narrow contracts and
evaluations pass:

1. `search_approved_evidence_release` for exact released records;
2. deterministic calculation and compatible-period comparison tools;
3. release-scoped narrative context;
4. research-answer composition under `research-answer.v1`;
5. `create_review_task`; and
6. separately governed watchlist alerts.

Explore, analyze, compare, and verify are task intents, not blanket tool
permissions. The planner receives only the allowlist for the admitted intent.
It cannot call arbitrary URLs, inspect private documents, alter policy, write a
verdict, trade, access live filings, or treat a news or narrative passage as an
eligible verification fact.

The first read-only search contract is split into
`approved-evidence-search-request.v1` and
`approved-evidence-search-result.v1`. A request contains one admitted task
intent, exact company CIK, as-of date, release ID and manifest hash, and no more
than 32 exact structured queries. Each query declares a unique query ID,
metric, period start, period end, and unit. It contains no free-form search
text, URL, provider, ranking instruction, or narrative request.

The provider-free adapter accepts only an in-memory or archive-loaded
`IndexedEvidenceRelease`. It first proves the release identity, issuer, and
as-of date were compiled into that release, then performs exact
release-hash/CIK/metric/period/unit lookup. It never performs similarity search,
network retrieval, source expansion, or narrative fallback. Missing facts are
returned explicitly with reason `exact_fact_not_found`; an empty verified fact
set is a complete safe result.

Each returned fact binds the query and stable fact/evidence IDs to the exact
entity, metric, canonical decimal-string measurement, period, filing accession
and date, source URL, release hash, and a deterministic source statement. The
adapter emits a structured-fact citation authorization compatible with
`research-answer.v1`; it cannot emit narrative context or a verdict. Result
status is `completed` when every query resolves, `partial` when some resolve,
and `unavailable` when none resolve. The canonical request hash and detached
result hash make replay visible. This local tool contract creates no API route,
worker action, model call, or deployment authorization.

The first calculation tool is split into
`approved-calculation-request.v1` and
`approved-calculation-result.v1`. It is a deliberately narrower execution
boundary than the complete calculation graph accepted by
`research-answer.v1`. A request binds the exact approved-evidence search-result
hash and release manifest hash, then declares one through 32 ordered
calculation instructions. Each instruction contains a unique result statement
ID, one of the four approved operations, ordered input statement IDs, and zero
through twelve decimal places. It cannot supply values, units, result text,
formulas, executable code, URLs, provider instructions, or narrative.

The provider-free adapter receives the request and the independently validated
`ApprovedEvidenceSearchResult` object. It proves both hashes and the release
binding match, resolves every input only to a numeric released-fact statement
in that result, and performs decimal arithmetic using round-half-even. The
first adapter does not accept a model value, narrative value, arbitrary caller
value, or another calculation as an input. This direct-fact restriction keeps
the initial tool graph bounded even though the downstream research-answer
validator can replay already validated calculation dependencies.

For `sum`, at least two facts must have one unit and the exact same reporting
period. For `difference` and `percent_change`, exactly two facts must represent
current then baseline for the same company, release, metric, and reporting
period duration, allowing a one-day duration difference for calendar effects;
the current period must end later. Percent change additionally requires a
non-zero baseline. `percentage_point_change` has the same comparison rules and
requires both inputs to use unit `percent`. These checks prevent a model or
caller from silently comparing incompatible metrics, reversed periods, or
unrelated reporting windows.

Each completed calculation is the exact `deterministic_calculation` statement
shape accepted by `research-answer.v1`: fixed kind, statement ID and text,
empty citation IDs, ordered derivation IDs, null measurement, operation,
canonical decimal-string value, unit, and decimal places. Canonical request and
detached result hashes make replay visible. Invalid or unavailable inputs fail
closed; the adapter never substitutes a value or narrative. This local
contract adds one policy-known internal tool name,
`calculate_approved_evidence`, but does not enable it in a deployed policy,
worker, API, public task, or autonomous action loop.

The first narrative-context tool is split into
`approved-narrative-context-request.v1` and
`approved-narrative-context-result.v1`. It is a provider-free retrieval
boundary over the already compiled narrative index, not the later semantic
retrieval system. A request binds one admitted task intent, exact company CIK,
as-of date, release ID and manifest hash, zero through sixteen exact filing
accessions, and a maximum of one through sixteen chunks. It contains no
free-form query, URL, source text, ranking instruction, provider, or licensed
news request. An empty filing list means all eligible issuer chunks within the
declared release and as-of scope, subject to the explicit cap.

Every compiled narrative chunk binds its release, company, filing accession,
filing date, HTTPS source URL, exact character span, authorized statement text,
and content hash. The adapter proves the loaded release identity, issuer, and
as-of snapshot, excludes chunks filed after the admitted date, filters only by
the exact requested accessions, and orders results deterministically before
applying the cap. It reports missing filing context and omitted chunk counts
explicitly; status is `completed`, `partial`, or `unavailable`. It performs no
network retrieval, similarity search, source expansion, or model call.

Each returned item is a `narrative_context` statement and a citation
authorization compatible with `research-answer.v1`. Its source type is fixed to
`narrative_disclosure`, verification role is fixed to `context_only`, evidence
ID is null, and release hash, source record, URL, chunk hash, and source span
must match the compiled chunk exactly. Narrative context cannot authorize a
measurement, released fact, deterministic calculation, interpretation,
verification input, or verdict. Canonical request and detached result hashes
make replay visible. This local contract may replace the untyped internal
`narrative_context` helper behind the existing policy-known tool name, but it
does not enable that tool in a deployed policy, worker, API, public task, model
loop, or autonomous action loop.

The first review boundary is split into
`approved-review-task-request.v1` and
`approved-review-task-result.v1`. A request records one admitted task intent;
one system-assigned origin; one typed review reason; a concise single-line
review question; the exact release ID and manifest hash; runtime and
release-gate policy hashes; one through eight independently admitted source
result hashes; zero through thirty-two statement IDs; zero through thirty-two
citation IDs; and the audit-manifest hash. At least one statement or citation
ID is required. The question contains no URL, source passage, hidden reasoning,
investment recommendation, allocation, price target, or trade instruction.

The origins are `bounded_agent`, `deterministic_validator`,
`deterministic_verifier`, and `policy_control`. Deterministic code restricts
each origin to compatible reasons: evidence ambiguity, conflict, missing
required evidence, interpretation review, verifier resolution, or publication
policy review. The caller cannot label an agent request as a verifier or policy
decision. An independently constructed grounding context binds the admitted
intent, origin, exact data-minimized review question, release, both policy
hashes, audit hash, authorized source result hashes, statement IDs, and citation
IDs. The request cannot authorize its own question. Missing, cross-release,
cross-policy, unaudited, unknown, duplicate, or ungrounded references fail
closed.

The provider-free adapter derives a stable review-task ID from the canonical
request hash and emits one replayable `requires_review` record. The same exact
request is therefore idempotent. Creating this record is not reviewer approval,
assignment, persistence, notification, publication permission, or verdict
composition. The first adapter performs no database write, queue operation,
model call, network request, or user contact. It may replace the mutable
in-memory `create_review_task` helper behind the existing policy-known tool
name, but does not enable that tool in a deployed policy, worker, API, public
task, or autonomous action loop.

The first agent-planning boundary uses one canonical task-intent enum across
all research contracts: `explore`, `analyze`, `compare`, and `verify`. A
versioned deterministic matrix narrows the signed runtime policy for each
intent. Explore may propose exact search, narrative context, or review;
analyze and compare may additionally propose deterministic calculation;
verify may propose only deterministic claim verification or review. The
effective allowlist is the intersection of this matrix and the current signed
runtime policy after disabled tools are removed. Neither the model nor a
request may broaden it.

The planning contract is split into `agent-plan-request.v1` and
`agent-plan-result.v1`. The request binds a task ID, admitted intent, hash of
the exact normalized user question, company CIK, as-of date, release ID and
manifest hash, both policy hashes, effective ordered tool allowlist, model-call
and action caps, and prompt/tool contract hashes. An independently constructed
grounding context binds the same fields and the exact question; the persisted
plan request contains only its hash. This keeps raw user text out of the
replay artifact without allowing the request to authorize its own scope.

A plan result contains only an ordered, bounded list of typed stages or an
explicit unavailable reason. Each stage has a unique ID, one allowed tool, one
fixed purpose compatible with that tool, and dependencies that refer only to
earlier stages. Calculation must depend on exact search; review must depend on
prior grounded work; verification is available only to the verify intent. The
plan carries no URL, source passage, executable code, tool arguments, fact,
citation, answer, recommendation, or verdict. It is therefore a proposal, not
execution authority. A later tool request must independently pass its own
typed contract, admitted scope, current-policy authorization, and task-local
artifact checks immediately before execution.

Each planner call is recorded under `model-attempt.v1`. The record binds the
task and plan-request hash to the exact provider, model and version, secret
version, prompt and tool hashes, runtime-policy hash, sequence number,
provider-attempt identifier when one exists, provider outcome, deterministic
validation outcome, output hash when completed, token use, and attributable
cost. It stores no raw prompt, provider output, hidden reasoning, credentials,
or user text. Completed output is either accepted or rejected by deterministic
validation; not-started, ambiguous, and unavailable attempts are never treated
as completed. No attempt authorizes an automatic retry or fallback model.

The first provider-free implementation validates plans and records synthetic
provider outcomes for tests only. It performs no model call or tool action and
adds no API, queue consumer, deployment, or public capability. The next private
slice may connect one pinned model through this boundary, then execute each
separately validated tool request with policy reauthorization and deterministic
`research-answer.v1` composition. Explicit claim-verification verdicts remain
the sole output of the deterministic verifier.

The provider-free execution boundary is `agent-execution-result.v1`. It accepts
only a validated plan, its independently admitted plan request and question
context, current policy pointers, and a stage-request provider controlled by
the application. The plan never supplies executable arguments. Immediately
before each stage, the provider supplies an instance of that tool's existing
versioned request type; deterministic code proves its stage, intent, company,
as-of date, release, request hash, dependency, and policy scope before the
existing approved tool adapter reauthorizes and executes it. The first runner
does not call a planner or create tool requests from model text.

Each execution owns a task-local artifact registry. A registered artifact binds
one plan stage and tool to its canonical request hash, result hash, dependency
result hashes, terminal tool status, and exact statement, citation, or claim
identifiers exposed by the validated result. The registry retains typed result
objects only inside that execution. Unknown tasks, plans, stages, dependencies,
request hashes, result hashes, statement IDs, citation IDs, and claim IDs fail
closed. Calculation resolves only an exact-search artifact declared as its
plan dependency; review references only artifacts and identifiers already in
the same registry. A model-visible identifier is never sufficient authority.

The runner executes stages in their validated order, once each, subject to the
plan action cap. It rechecks current policy before every action and before
returning the execution record. Typed partial or unavailable retrieval remains
visible and may support a later independent stage, but an invalid dependency,
revoked policy, unavailable required input, missing deterministic verifier, or
tool failure stops safely without fallback. `requires_review` is terminal. The
execution result contains artifact metadata and one unavailable reason, not raw
tool output, a research answer, or a verdict composed by the runner. A later
composer must build `research-answer.v1` only from this registry and separately
authorized interpretation warrants.

Web and mobile use one `agent-presentation.v1` grammar over these shared
contracts. The primary surface contains, in order: one result state, one short answer or
reason, one plain scope line, and one next safe action. `Ask Quantify` shows
only three working labels: `Understand`, `Research`, and `Check`. Facts,
analysis, context, and verification are visually distinct, while citations,
methodology, release identity, policy identity, and audit identity remain under
`Details`. Internal tool names, hashes, queues, provider attempts, token counts,
policy terminology, and architecture are never primary-interface copy. Web and
mobile may change layout but not wording, state meaning, or information order.

The private pilot foundation implements the SQS batch-adaptation and
control-plane boundaries described above. Its guarded offline IAM-only
admission command may validate and durably queue one task only when an
authorized operator invokes it; it is not an HTTP surface and its dry-run mode
performs no write. The command remains non-consuming until separately activated
through a preflighted, bounded two-worker-concurrency and SQS-mapping procedure.
The V1 public and private verification routes remain the only active product
contracts until the prerequisites in Section 8 are satisfied and separately
authorized.

## 6. Safe results and provenance

Every visible statement is labelled verified fact, qualification,
counterevidence, agent inference, open question, or review required.

A structured fact citation carries source_type structured_fact,
verification_role verdict_evidence, release hash, filing/accession, fact ID,
and evidence ID. A narrative or entitled-news citation carries source_type
narrative_disclosure or licensed_news, verification_role context_only, release
hash, source-record ID, chunk hash, and source span. It is visibly attributed
context, not independent verification.

Every agent inference includes visible derived-from statement IDs. An open
question includes those IDs when it arises from a visible statement and may
instead point to an explicitly unavailable request. This allows users to trace
reasoning inputs without turning an inference into a verdict.

The versioned `research-answer.v1` contract is the safe composition boundary
for explore, analyze, and compare tasks. It contains task type and terminal
state; entity and as-of scope; exact release IDs and hashes; a concise answer;
the ordered statement IDs from which deterministic code composes that answer;
typed statements; citations; counterpoint statement references; explicitly
unavailable requests; limitations; the pinned model and prompt/tool contract
when a model was used; optional embedded deterministic-verifier results; and an
audit manifest hash. The published answer string must equal the selected
validated statement texts joined in order with two newline characters. It never
contains raw provider output, hidden chain of thought, an ungrounded confidence
score, a recommendation, a price target, an allocation, or a trade instruction.

Research-answer statements use only these types:

- `released_fact` — exact released data with at least one eligible structured
  citation;
- `deterministic_calculation` — a recorded calculation derived from released
  fact statement IDs;
- `agent_interpretation` — a cited explanation derived from visible statement
  IDs and never presented as a fact or verdict;
- `narrative_context` — attributed release-scoped disclosure or entitled-news
  context whose verification role is always `context_only`; and
- `open_question` — an explicit unresolved question, never a hidden completion.

Every released-fact or narrative-context statement uses only text authorized by
its exact release-bound citation record. A numeric released fact may also carry
a typed measurement containing a canonical finite decimal string and unit. An
interpretation or open question never carries a measurement. A
deterministic-calculation statement records its operation, ordered input
statement IDs, canonical decimal-string result, unit, and decimal places; its
input IDs exactly equal its derived-from IDs. Decimal strings never use an
exponent, leading plus sign, `NaN`, or infinity.

The initial replayable calculation operations are deliberately small:

- `sum` accepts at least two inputs with one unit and returns that unit;
- `difference` accepts current then baseline with one unit and returns that
  unit;
- `percent_change` accepts current then non-zero baseline with one unit and
  returns `percent`; and
- `percentage_point_change` accepts current then baseline percentages and
  returns `percentage_points`.

Calculations use decimal arithmetic and round the result to the declared zero
through twelve decimal places using round-half-even. Inputs may be only numeric
released facts or already validated deterministic calculations. Interpretation,
narrative context, and open questions can never become calculation inputs.
Deterministic code also composes each calculation statement text using one of
these exact forms: `Calculated sum: {value} {unit}.`, `Calculated difference:
{value} {unit}.`, `Calculated percent change: {value}%.`, or `Calculated
percentage-point change: {value} percentage points.`

Validation receives an independently admitted context containing the exact
ordered release bindings, observed-through time, authorized citation records
and their permitted statement text and measurement, expected model contract,
expected deterministic-verifier results, expected audit hash, and any
interpretation warrants produced by a separate deterministic or policy-approved
warrant check. An interpretation is rejected unless its statement ID, text, and
ordered derivation IDs exactly match one of those warrants; the proposed answer
cannot authorize its own interpretation. Fields in the proposed answer cannot
authorize themselves. Deterministic validation rejects shape or type drift,
duplicate IDs, missing or cyclic references, unreachable statements, unused
citations, citations outside the admitted release scope, unauthorized citation
content, narrative marked as verdict evidence, non-replaying calculations,
answer-composition drift, prohibited advisory or trade output, verification
without exact deterministic authority, and model or audit mismatch. An empty
fact or analysis set remains a valid safe result when the answer instead
contains a typed open question and explicit unavailable state.

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

The public release-operations view is a read-only deterministic projection of
`public-release-index.v3`. It may display only each declared catalog, status,
freshness, observation time, release ID, manifest hash, limitation, and the
index generation time. Counts and attention states are exact arithmetic over
those fields. It is not production telemetry, reviewer throughput, a release
gate, or evidence that an unavailable catalog is healthy.

The first public-catalog refresh coordinator is offline and candidate-only. It
accepts explicitly supplied local reviewed source files, an already compiled
and hash-validated investor catalog, reviewed security metadata, and the active
public release index. It compiles ETF flows before release-bound ETF holdings,
records exact input and output hashes, emits a content-addressed candidate
manifest and rollback bindings, and writes a complete staging directory
atomically. It has no network adapter, publish flag, active-index mutation,
deployment step, or implicit reviewer approval. A malformed input, invalid
catalog hash, dependency mismatch, existing target directory, or partial
compile fails closed without a candidate. The same inputs and declared run time
must produce byte-identical candidate artifacts. Refreshing the 13F source
itself remains a separately reviewed acquisition/compiler step; passing an
existing investor catalog to this coordinator does not claim that acquisition
occurred.

`public-refresh-candidate.v2`, `public-candidate-review.v2`, and
`public-candidate-gate-policy.v2` extend that candidate-only workflow with an
optional reviewed `vc-source-bundle.v1` input. When present, the coordinator
compiles `vc-catalog.v1` and `vc-compilation-record.v1`, binds the prior Venture
release for rollback, and proposes the new Venture identity in the candidate
index. It still has no acquisition, promotion, active-index mutation,
publication, deployment, or approval path. The deterministic reviewer replays
the Venture catalog and compilation record, compares exact firm IDs and exact
firm/company relationship IDs with the active catalog, and records added and
removed firms and relationships. Any Venture release-identity change, new firm,
new official host, or relationship-scope change is Lane B and requires a later
full review. Every candidate and review record states that publication or
promotion is not authorized. Omitting Venture input preserves the active
Venture binding and does not claim that the source was refreshed.

The first offline Form 13F compiler input is
`investor-sec-source-bundle.v1`. A reviewed bundle manifest declares the exact
reporting-manager CIK set, history depth, creation time, and every local SEC
resource by canonical SEC URL, relative path, media type, and SHA-256 hash. The
cache-only client rejects non-SEC hosts, absolute or escaping paths, duplicate
URLs or paths, undeclared requests, missing or changed bytes, manager-scope
mismatch, unused declared resources, and an invalid history depth. It has no
network fallback. The source-manifest hash, security-metadata hash, compiler
contract, and resulting catalog identity are recorded in the release candidate.
The bundle is an input to deterministic compilation, not evidence that source
review, a release gate, promotion, or deployment occurred. Creating or updating
the bundle from SEC remains a separate explicitly run offline acquisition step.
That acquisition requires an SEC-compliant user agent, a declared creation
time and bounded history depth, records only the exact resources requested for
the configured managers, and atomically writes a new target directory. It may
use the local acquisition cache but has no overwrite, catalog-publication,
promotion, deployment, or active-index mutation path. Acquisition preserves a
valid bundle when configured managers have different latest reporting periods;
the compiler still fails closed until their latest compatible filings share one
period.

`investor-filing-readiness.v1` is the deterministic, offline preflight for a
reviewed `investor-sec-source-bundle.v1`. It binds the exact source-manifest
hash, an explicit check time, and one requested quarter-end, then reports each
configured manager's latest compatible Form 13F period, filing date, accession,
and one of `ready`, `waiting`, or `ahead`. `ready` means the latest compatible
filing is exactly the requested quarter; it does not mean the filing contents
or resulting catalog have passed source review. The report is complete only
when every configured manager is `ready`, is content-addressed, and always
states `candidate_build_authorized: false`. Missing, changed, undeclared,
non-SEC, out-of-scope, malformed, or temporally inconsistent bundle content
fails closed without a report. The preflight has no network fallback and no
compile, approval, promotion, publication, deployment, or active-index mutation
path.

When a candidate compiles a new investor catalog, it must also rebuild every
deterministic public projection bound to the investor release. The initial
dependency is `crypto-exposure-catalog.v1`; its candidate binding changes with
the investor release or the candidate fails closed. A candidate may not retain
a crypto-exposure binding to a different investor manifest.

`public-candidate-gate-policy.v1` governs deterministic review of a staged
public refresh candidate. The reviewer replays the candidate run ID, base-index
hash, every declared artifact hash and catalog manifest, candidate-index
bindings, unchanged catalog bindings, previous rollback bindings, investor
compilation record, and investor-to-crypto dependency before calculating a
diff. Missing, extra, malformed, changed, unbound, or non-replaying content
fails closed and produces no review-ready record.

For a valid candidate, the gate reports exact catalog identity/status/freshness
changes and bounded structural metrics: investor manager scope, source-review
count, per-manager disclosed-value and holdings-count changes, ETF fund scope,
ETF net-asset changes, ETF published-row counts, and investor-to-crypto binding.
The versioned policy alone defines Lane B thresholds. Manager-scope changes,
status or observation regressions, increased source-review cases, stale
candidate bindings, or threshold breaches require Lane B; otherwise the
candidate is Lane A. Zero identity changes are disclosed explicitly. The
review record is content-addressed, includes the exact rollback bindings, and
always states `promotion_authorized: false`. Lane A requires a later spot
review and Lane B requires a later full review. This gate cannot approve,
promote, publish, deploy, mutate an index, or act as a reviewer signature.

Public investor-tracking releases use the same factory boundary. The release
compiler resolves the reporting-manager identity, filing accession, reporting
period, amendments, security rows, and comparison policy before publishing.
Displayed value and weight are limited to the disclosed 13F information table.
`NEW` and `EXITED` mean presence changed between compatible releases;
`ADDED` and `REDUCED` use normalized share-count changes, while portfolio-weight
movement is displayed separately in percentage points. Missing mappings,
incompatible quarters, and ambiguous amendments fail closed rather than being
estimated. Ticker and theme metadata are separately versioned and may be absent.

Venture relationships use `vc-catalog.v1`, never the Form 13F contract. The
initial release is a bounded official-source sample for Sequoia Capital,
Andreessen Horowitz, Founders Fund, and Khosla Ventures. `vc-source-bundle.v1`
contains only manually reviewed relationship facts from declared public firm
portfolio pages, with an exact retrieval time, source URL, and source-content
hash for every row. `vc-compilation-record.v1` binds the source payload,
compiler contract, catalog identity, firm count, and relationship count and
always records `publication_authorized: false`.

Each published venture row states only that the named firm publicly presents
the named company as a portfolio relationship in the declared source snapshot.
Broad sector labels are versioned Quantify display classifications and are
counted by tracked company, never by invested dollars. First-partnered year,
stage, participation role, and follow-on status remain `undisclosed` unless the
same declared official source states them exactly. V1 contains no ownership
percentage, check size, position value, portfolio weight, AUM, valuation,
markup, return, exit inference, or recommendation. A missing or ambiguous
identity fails closed; an empty verified relationship set is valid. Venture
company names do not enter public-company ownership pages or the claim-verdict
fact index. An exact public-company connection requires a later reviewed entity
mapping and contract update.

The next reviewed Venture candidate may extend the Core technology / AI group
with Thrive Capital and General Catalyst, using only their declared official
portfolio or portfolio-careers pages. Those candidate relationships remain
unreleased until Lane B review and separately authorized promotion. An official
firm-operated portfolio-careers subdomain is eligible only as an attributed
firm/company relationship source; job count, hiring activity, third-party
descriptions, stage tags, and other career-platform metadata are not Venture
facts.

Public market-intelligence releases use distinct versioned contracts rather
than extending the 13F schema. Each metric records a stable entity or asset ID,
value, unit, effective time, observation time, source record, methodology,
release identity, freshness state, and limitations. Market and cryptocurrency
acquisition runs offline; browsers and online agents never call an exchange,
chain indexer, news site, or data vendor directly. Missing, stale, conflicting,
or revoked inputs fail closed to `unavailable` or `source_review`.

Cryptocurrency identity is keyed by a stable asset ID plus network and contract
address where applicable, never by symbol alone. A crypto release defines its
price-composite method, circulating-supply method, continuous-market freshness
limit, wrapped/bridged-asset policy, chain-finality rule, and revision handling.
ETF or ETP holdings and flows remain distinct from direct token ownership.
Quantify does not infer wallet owners, call price or volume movement
institutional accumulation, or present staking yield as a recommendation.

Market-source eligibility is recorded in the versioned public-intelligence
source register before an adapter or release is enabled. Technical public API
access does not establish redistribution or commercial-display rights. A source
marked `blocked_public_display`, `blocked_commercial_use`, or
`license_required` cannot feed a public release. Changing that status requires
review of the applicable permission or agreement and a versioned register
update; it is not implied by a successful network request.

The first crypto-connected release is `crypto-exposure-catalog.v1`, a
deterministic projection of crypto-linked exchange-traded product rows already
present in an approved investor 13F release. Reviewed SEC-filed security
identity maps an ETP CUSIP to a crypto asset. The release binds the investor
manifest, preserves every manager filing source, permits an empty asset
position set, and never represents ETP shares as direct token ownership or
reported-position changes as ETF flows. It carries no market or network data.

The first active market layer is `treasury-rates-catalog.v1`. It is compiled
offline from the official U.S. Treasury Daily Par Yield Curve XML feed and
contains exact published maturities plus the deterministic `10Y − 2Y` spread.
The release records the observation date, feed publication time, source record
and hash, freshness deadline, methodology, and limitations. Treasury par yields
are labelled as interpolated curve observations based on indicative bid-side
quotations, not transaction prices. Stale releases remain visibly stale and may
not be represented as current; no rate direction or forecast is inferred.

The first active macro layer is `bls-macro-catalog.v1`. It is compiled offline
from exact U.S. Bureau of Labor Statistics Public Data API rows for the
not-seasonally-adjusted all-items CPI index, the not-seasonally-adjusted
all-items-less-food-and-energy CPI index, and the seasonally adjusted
unemployment rate. Headline and core CPI are deterministic year-over-year
percent changes requiring the exact current and prior-year index rows and are
rounded to one decimal; missing inputs fail closed. Unemployment is the exact
published rate. The release records the period, retrieval time, source rows and
hash, calculation method, freshness deadline, required secondary-use
disclaimer, and limitations. It does not infer a macro regime, market impact,
or forecast, and revisions after retrieval remain outside the immutable
release.

The active ETF-flow layer is `etf-flow-catalog.v2`. It is compiled
offline from exact Form N-PORT Item B.6 fields in one declared SEC quarterly
data set and is initially limited to SPY, QQQ, SMH, IWM, and VGT. Fund report
dates and their exact three-month windows are preserved independently; the
interface must not imply that different fund dates are synchronized. For each
filed month, net flow equals the reported net asset
value of shares sold plus shares sold through reinvestment minus shares
redeemed or repurchased. The release preserves all three inputs, the derived
monthly result, the three-month total, fund and series identity, accession,
filing date, report date, official filing page, source archive hash, and ticker
identity source. A change in fund net assets is never labelled flow. The layer
is a delayed filing view, not a daily creation/redemption feed, and it does not
infer investor intent, underlying-security purchases, market direction, or a
recommendation.

The first active ETF-holdings layer is `etf-holdings-catalog.v1`. It is an
offline deterministic projection of reviewed `FUND_REPORTED_HOLDING` rows from
the same declared SEC Form N-PORT archive as the active ETF-flow release. The
initial release is limited to the ten largest filed positions by reported
percentage for VGT, QQQ, and SMH. It preserves fund identity, accession,
filing and report dates, the archive hash, holding ID, issuer, title, CUSIP,
balance and unit, reported currency value, filed percentage, and investment
country. Display tickers and themes may be joined only from the versioned
reviewed security-metadata map; missing mappings remain null. The compiler
binds each fund to the matching ETF-flow fund record and fails closed for a
dataset, accession, report-date, net-asset, ordering, or release mismatch. The
layer is a top-ten snapshot, not a complete portfolio, current exposure,
beneficial-ownership statement, sector classification, flow attribution, or
recommendation. A company-page connection means only that an exact mapped
security appears in this bounded filed snapshot.

The first active earnings layer is `earnings-catalog.v1`. It is compiled
offline from exact facts in the declared frozen SEC Company Facts manifest and
is initially limited to AAPL and MSFT. Each company record binds one filed
quarter to its CIK, accession, form, fiscal period, period dates, filing date,
Company Facts source, and SEC filing page. Revenue and diluted EPS use declared
US-GAAP concepts and units. A year-over-year change is published only when the
current filing contains an exact comparative prior-year quarter for the same
concept, unit, and accession; missing or incompatible inputs fail closed. The
release contains reported results only. It does not contain consensus
estimates, surprise labels, guidance interpretation, future earnings dates, or
market-price reactions.

The first active policy layer is `policy-event-catalog.v1`. It is compiled
offline from a small declared set of official Federal Reserve, SEC, and federal
rulemaking records. Each event binds a stable event ID, authority, category,
action type, status, publication and effective dates, official document ID,
source URL and source hash, plus a typed detail contract specific to the event.
The first release contains the latest FOMC target-range decision and scheduled
next meeting, the final joint Financial Data Transparency Act standards rule,
and the final BIS advanced-computing export-license review rule. Quantify may
show exact named products, agencies, destinations, requirements, and company
identifiers explicitly named by a source. It does not convert a policy event
into a certain asset-price direction, implied probability, recommendation, or
forecast. Narrative context cannot create an affected-asset relationship.

## 8. Implementation plan

This is a dependency plan, not a timing promise. Build and test each step before
relying on it. Workstreams explicitly marked independent may proceed in
parallel, but they converge at the same contracts and gates before exposure.

1. **Policy-control and pilot foundation — complete for one private pilot.** Signed-envelope types, KMS signing and verification boundaries, content-addressed artifact loading, strongly consistent pointer/status reads, and reload-on-authorization are implemented. The target account has active signed runtime and release-gate artifacts, selected evidence pointers, verified KMS/S3/DynamoDB access, replay-visible audit hashes, and a tested emergency disable/restore. Remaining work is recurring operational monitoring and repeating these checks for any new environment or release.
2. **One approved frozen release — complete for the pilot.** Exact-fact and release-scoped narrative indexes are compiled and replay-checked for the approved embedded corpus. Archive load verifies every index hash; tests prove narrative context cannot enter verdict evaluation. Future releases require the same factory and gate process.
3. **Async worker boundary — active private pilot.** Canonical hashing, idempotency collision rejection, sharded admission, bounded queues, task state, SQS batch failure reporting, guarded offline IAM-only admission, exact release-scope preflight, and the fail-closed indexed worker composition are implemented. The pilot has a selected approved archive, bounded worker and SQS mapping at `2`, active-mode post-deploy checks, and an end-to-end task with durable safe state and encrypted audit persistence. Before a terminal transition, the worker durably journals only its validated publication-safe result; a duplicate delivery can finalize that journal without another model call, while a missing journal remains explicitly reconciling and fail-closed. The deployed pilot exercised the journal to a durable `requires_review` result and replayed its terminal SQS message: state and audit binding were unchanged, and the queue and DLQ drained to zero. V1 continues reading embedded fixtures. Remaining work: prove all recovery cases in the target account and repeat the release parity process for every new release.
4. Prove failure/recovery semantics: provider-not-started, completed, ambiguous, reconciliation-unavailable, manual retry, cancellation, and reservation reconciliation. No automatic model retry or fallback.
5. Load and abuse test public access: sharded hard caps, burst behavior, queue saturation, WAF/rate enforcement, cache behavior, and telemetry separation. Do not expose a research-task route until these tests and an explicit authorization approve it.
6. **Private catalog staging and delivery — complete for one private pilot, not publicly exposed.** Source validation, normalization, evaluations, Lane A/B gate records, immutable manifests, and rollback/revocation controls are implemented. A separately KMS-signed named-reviewer action can stage or revoke an immutable catalog in a private IAM-only bucket with compare-and-swap pointer updates; a passed release gate cannot stage it automatically. The pilot has a distinct versioned, public-blocked delivery bucket encrypted with a customer-managed key, a CloudFront Origin Access Control, trusted key group, existing global WAF, and an S3 policy limited to catalog reads from that distribution. A separately authorized, non-deleting sync copies only `release-catalogs/v1/` into the delivery bucket. Deployment verification proves unsigned and expired signed URLs return `403`, while a short-lived valid signed URL can read the staged pointer. The original policy-artifact bucket remains outside CDN delivery. A distinct authorization is still required before any public CDN promotion.
7. **Grounded research-answer and agent-planning boundary — local validator,
   exact-search, direct-fact calculation, narrative-context, review-task,
   intent, plan, and model-attempt contracts complete, not connected.**
   `research-answer.v1` schema validation,
   exact admitted-scope comparison, authorized citation binding,
   statement/reference checks, deterministic calculation replay, independent
   interpretation warrants, answer composition, prohibited-content screening,
   model/verifier/audit matching, and focused negative tests are implemented
   locally. The versioned approved-evidence request/result schemas and
   provider-free frozen-release adapter now return only exact structured facts
   or explicit unavailable outcomes, with replay hashes and citation
   authorizations. The versioned calculation request/result contracts now bind
   direct released-fact operands to that exact search result, enforce unit and
   reporting-period compatibility, replay decimal arithmetic, and emit
   research-answer-compatible calculation statements. The versioned narrative
   request/result contracts bind exact issuer, as-of, release, optional filing,
   and chunk-cap scope; the provider-free adapter returns only frozen
   disclosure chunks with exact source metadata, replay hashes, explicit
   truncation or unavailable outcomes, and `context_only` citation
   authorizations. Indexed-release archive `1.2.0` preserves and replays the
   filing date, HTTPS source URL, character span, text, and chunk hash. The
   loader may replay a `1.1.0` archive only when it contains no narrative
   chunks; legacy chunks without the new citation metadata fail closed and
   require offline recompilation. The versioned review-task request/result
   contracts bind one safe question to exact origin, reason, release, policy,
   source-result, statement, citation, and audit context; the deterministic
   adapter derives an idempotent `requires_review` record without persistence,
   assignment, approval, notification, or verdict authority. Existing
   policy-controlled internal tools delegate to all four adapters. The
   canonical intent matrix, versioned agent-plan request/result contracts,
   independently grounded provider-free plan validator, and attributable
   model-attempt record now bind plans to admitted scope, ordered tools,
   action/model budgets, provider outcome, validation outcome, and replay
   hashes without storing raw user or provider text. They have no API, model,
   live retrieval, similarity expansion, or verdict authority. The local
   provider-free execution runner now consumes independently supplied typed
   stage requests, reauthorizes every approved tool, binds results into one
   task-local artifact registry, rejects cross-task or cross-stage references,
   and emits only replayable execution metadata. It does not compose an answer
   or verdict. Next compose `research-answer.v1` deterministically from the
   registry, then connect one pinned model in a private orchestration loop.
   Model-assisted composition remains private until admission, cost, and
   public-task gates pass.
8. **Account and access decisions — specification work may run in parallel with
   step 7.** Complete the seven decision artifacts in section 4.1, including
   licensed-content retention, audit erasure, subscription lapse, and orphaned
   workspaces. This work may not create account schemas, collect user data,
   enable human sign-up, purchase data, or expose a route. The licensed-content
   and audit/erasure decisions are hard gates for the Library and account data
   contracts.
9. Expand issuer coverage according to measured release-factory throughput;
   maintain SDK/tool adapters that preserve the safe contract. Reassess storage
   only from observed query patterns.
10. Implement accounts, workspaces, subscriptions, Library, RBAC, retention,
    legal hold, and private-data classification only through the gated sequence
    in section 8.3. None is implied by completion of the public research tools.

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

### 8.2 Public intelligence web sequence

The public intelligence web expands through independently releasable slices:

1. Establish one coherent application shell and routes for Overview, Markets,
   Investors, Companies, Intelligence, and claim verification.
2. Build company ownership pages as deterministic projections of the existing
   frozen investor catalog. Label all totals as sums across tracked reporting
   managers and retain each filing source.
3. Add a public release index and explicit unavailable states. A route may
   exist before its data release, but it must not display illustrative values as
   observations.
4. Add market and macro catalogs only after approved sources, field methods,
   freshness thresholds, correction handling, schemas, compiler tests, and a
   release gate exist.
5. Add a narrow cryptocurrency release, initially limited to approved BTC and
   ETH market, fund-flow, network, policy, and event fields. Expand asset
   coverage only after symbol/contract resolution and continuous-market
   freshness controls pass.
6. Add earnings, policy, ETF-flow, and high-impact event catalogs one at a time.
   Each receives its own source and methodology review.
7. Add a separately typed venture relationship catalog and interface from
   reviewed official firm sources. Do not project private-company relationships
   into public-company ownership or the claim-verdict fact index.
8. Add a typed cross-catalog entity graph and search only from released exact
   identifiers. Narrative similarity may suggest review work but cannot publish
   an entity relationship as fact.
9. Add model-assisted `research-answer.v1` composition only after deterministic
   validation can bind every factual statement and citation to its declared
   release, calculations can be replayed, counterpoints and unavailable data are
   explicit, and admission, cost, privacy, and public-task authorization pass.
10. Add a daily brief only after deterministic validation can bind every factual
   statement to eligible released fields and label every inference or open
   question. It must not predict prices or recommend a trade.

### 8.3 Account and authorization implementation sequence

Account implementation begins only after section 4.1's reviewed decision
artifacts exist. It then proceeds in this dependency order:

1. Publish versioned identity, account, workspace, membership, entitlement,
   subscription, Library, task-ownership, audit-surrogate, and lifecycle
   contracts. Contract tests cover expiry, downgrade, deletion, legal hold,
   entitlement revocation, owner loss, and cross-tenant denial.
2. Implement the central `authorize()` module against deterministic fixtures
   and fake repositories before persistence. Tests cover deny-by-default,
   tenant and workspace mismatch, membership and role changes, subscription
   lapse, source revocation, policy and release revocation, cache expiry and
   event invalidation, step-up requirements, queued-task continuation, saved
   result access, export, and administrative actions. The module is not shipped
   without a backing store; fixture-first work isolates policy semantics.
3. Bind the same tested repository interfaces to bounded DynamoDB tables and
   encrypted S3 objects. Prove conditional writes, tenant-key isolation,
   pseudonymous audit mapping, TTL handling, point-in-time recovery where
   required, deletion schedules, and fail-closed read or invalidation failure.
4. Add a non-production human Cognito client and sign-up/sign-in flow only with
   explicit authorization. Keep machine credentials separate; verify PKCE,
   account confirmation, recovery, session revocation, MFA, step-up, abuse
   controls, privacy copy, and safe logs before any public exposure.
5. Add the concise signed-in shell—`Today`, `Data`, `News & Events`, `Agent`,
   and `Library`—using only active contracts and canonical access states.
   Unreleased sources and actions remain visibly unavailable and disabled.
6. Add licensed news or event content only source by source after rights,
   lifecycle, attribution, freshness, correction, excerpt, derivation, export,
   and revocation gates pass.
7. Add authenticated agent history and saved research only after serve-time
   authorization, anonymous-task separation, data deletion, and Library
   redaction behavior pass end-to-end tests.
8. Add paid plans, daily workflows, institutional workspaces, private sources,
   APIs, and mobile clients as separate gated slices. Institutional owners and
   administrators require MFA; private-data intake remains blocked until
   section 8.1 is complete and explicitly authorized.

The research-tool work in step 7 and the decision work in step 8 are independent
and should proceed in parallel. All later account implementation depends on the
reviewed section 4.1 artifacts, while public model-assisted research remains
independently gated by its tool, evaluation, admission, cost, privacy, and
authorization requirements.

## 9. Web experience

### 9.1 Commercial web product contract

The commercial web presents Quantify as one coherent, high-technology research
product with four immediately understandable layers:

1. **Data.** Browse exact released company, investor, market, earnings,
   and policy records with visible observation or filing dates, scope, source,
   freshness, and limitations.
2. **Intelligence.** Connect only typed identities and relationships already
   present in compatible active releases; show reported change,
   counterevidence, qualifications, and open questions without turning context
   or inference into a fact or market-direction claim.
3. **Analysis.** Explain and compare compatible evidence with statement types,
   citations, counterpoints, unavailable fields, and limitations. The current
   public product exposes deterministic metrics and source-bound explanations;
   general model-assisted research answers remain visibly gated.
4. **Verification.** Give a bounded company-analysis claim to the research
   agent and receive claim-level verdicts composed only by the deterministic
   verifier, with evidence scope, citations, qualifications, counterevidence,
   review state, and audit identity.

The agent is the primary product action and the unifying interface across these
modes. It is differentiated by inspectability, reproducibility, controlled
evidence, and honest refusal or review states rather than by claims of general
intelligence, autonomous decision-making, or superior investment performance.
It may propose and explain structured research work; it may never establish a
fact, broaden the release, compose a verdict, recommend a security, or execute
a trade. Public copy may call it an `AI research agent` or `research referee`,
but may not claim that it is the best, most accurate, or better than a named
product without a current approved comparative evaluation and review.

The homepage must answer, in its first screen, what Quantify does, who it is
for, what the user can do next, and the current evidence boundary. The preferred
message pattern is a short outcome-led statement such as `Understand markets.
Analyze companies. Verify claims.`, followed by one sentence that distinguishes
currently released data, intelligence, and verification from gated
model-assisted analysis. The primary action opens an actual released research
view; the secondary action is `Open Agent` or `Verify a claim`. Marketing copy
must not lead with internal architecture terminology.

The public audience includes self-directed investors and learners who want to
understand companies, markets, and policy through source-visible research. The
paid audience includes professional research, corporate strategy,
investor-relations, consulting, and compliance-sensitive institutional teams.
Persona content describes bounded workflows and reviewable outputs. It must not
promise returns, trading outcomes, comprehensive coverage, time saved,
accuracy, security certification, service levels, or customer adoption unless
the exact claim is supported by current approved evidence.

The commercial capability matrix is explicit and release-visible:

| Product area | Available contract | Gated next state |
| --- | --- | --- |
| Data and information | Public read-only views derived from active released catalogs; the public release index is the coverage authority. | New sources, fields, entities, and live or licensed data require their own rights, methodology, freshness, correction, and release gates. |
| Intelligence | Exact released earnings, policy, entity, ownership, and other typed connections only where their sub-releases are active. | Narrative events, briefs, broader cross-catalog synthesis, and additional intelligence workflows remain unavailable until independently contracted and released. |
| Analysis | Deterministic released metrics and source-bound explanations already present in current research views. No general LLM research-answer task is public. | `research-answer.v1` composition, broader comparisons, counterpoint generation, and model-assisted synthesis require typed tools, grounding evaluation, admission/cost controls, and separate public-task authorization. |
| Verification | The bounded safe verification contract, current identity or separately authorized trial controls, deterministic verdicts, and audit identity. | Broader issuer coverage, async task UX, comparison, review, and export follow their existing release and task gates. |
| AI research agent | One structured extraction step under V1 policy; zero production resolution actions; no live retrieval, tool autonomy, or verdict authority. | Multi-step planning and bounded typed tools require a specification contract, focused evaluation, replay controls, and explicit action authorization. |
| Commercial access | Public catalog plus the currently authorized authentication and trial boundaries. | Pricing, subscriptions, team workspaces, public customer API, enterprise controls, and service commitments require separate product, cost, security, legal, and deployment approval. |

The website derives `available` labels from the active release and runtime
contracts wherever possible. A planned capability is visually separated from
an available capability and never uses an enabled action, fabricated product
screen, or ambiguous `coming soon` treatment that could imply access.

The commercial product exposes one systematic agent operating model across
explore, analyze, compare, and verify task intents. It is a presentation and
orchestration model, not additional model or tool authority:

1. **Objective.** The user supplies a bounded research question or claim.
2. **Scope contract.** Quantify declares company or entity identity, as-of
   date, permitted task, evidence release, input limit, and access mode before
   work begins.
3. **Released data.** The system identifies the exact active structured
   catalogs that may supply facts. Catalog status, release identity,
   observation time, freshness, source class, and limitations stay visible;
   unavailable data remains an explicit system state.
4. **Intelligence and analysis.** Human-readable records retain their data
   bindings. Typed identity, period, ownership, earnings, and policy
   connections may organize compatible released facts. An admitted analysis
   task may add deterministically validated comparisons and cited
   interpretations under `research-answer.v1`, but cannot create a missing fact,
   hide unavailable information, or imply market direction.
5. **Research result.** Deterministic code validates factual grounding,
   citations, derivations, scope, and prohibited content. When verification is
   requested, the deterministic verifier separately validates warrant,
   qualifications, and compatible counterevidence and alone composes the claim
   verdict. The safe result exposes limitations, review state, and audit
   identity in either case.

The homepage and agent workspace make this sequence legible as a compact
system map. They distinguish `Data` (versioned source-bound released records),
`Intelligence` (typed connections across compatible records), `Analysis`
(cited explanation whose factual statements are deterministically validated),
and `Verification` (a deterministic claim decision). A visual stage may say
`ready`, `available`, or `sample` only when that state comes from the current
runtime contract, active release index, or a labelled versioned fixture. It
must not simulate autonomous progress, continuous monitoring, live retrieval,
or capabilities that are not active.

Release-derived counts answer exactly what they count—for example declared
catalogs, active catalogs, reporting managers, mapped issuers, or reviewed
relationships. They never become claims of total market coverage, database
size, model knowledge, accuracy, adoption, or performance. The system map must
remain useful when the active verified set is empty or one or more data layers
are unavailable.

### 9.2 Visual and interaction direction

The commercial experience is concise, confident, product-led, and visibly
technical. It may draw general inspiration from high-quality modern financial
product sites: oversized outcome-led typography, generous whitespace, crisp
high-contrast calls to action, immersive product panels, short progressive
sections, and clear trust and disclosure layers. It must not copy another
company's trade dress, layouts, illustrations, interaction details, product
names, or trading language.

Quantify retains its own soft-white, lavender, purple-to-magenta visual identity
and may add a controlled near-black `signal` surface for the agent, verification
trace, and selected data demonstrations. The gradient is an accent and focus
device, not a full-page substitute for hierarchy. Interface imagery should be
rendered from real product components or versioned contract-valid fixtures;
generic stock imagery, fabricated dashboards, fake conversations, invented
customer results, unsupported counters, and decorative pseudo-live charts are
not allowed.

The canonical visual system uses one compact typographic ladder across public
routes: display heading, section heading, card heading, body, control, and
metadata. Display sizes may respond by viewport, but equivalent components use
the same role and scale; route-specific font sizes do not create a parallel
hierarchy. Body and explanatory text remain comfortably readable, while the
smallest metadata role is reserved for release state, source, time, identifier,
hash, and audit detail. Monospaced type is limited to those technical labels and
numeric or machine-readable values. Controls use a consistent height, weight,
radius, and focus treatment.

The high-technology character comes from precise alignment, restrained
geometry, strong contrast, thin system lines, tabular data, visible state, and
the near-black signal surface—not excessive glow, gratuitous gradients,
oversized card rounding, tiny labels, or decorative pseudo-instrumentation.
Shared surfaces use the canonical small, medium, and large radii; deviations
require a functional reason such as a circular status marker.

Pages use one dominant idea per viewport and progressive disclosure for detail.
Headlines are short, body copy is plain language, and the primary action remains
visually stable. Data surfaces may be compact and dense, but marketing sections
must be scannable. Motion may communicate agent progress, evidence binding,
state transition, or navigation context; it must be brief, interruptible,
non-essential to comprehension, respect `prefers-reduced-motion`, and never
simulate unavailable live data or certainty. Responsive layouts, keyboard
operation, visible focus, semantic headings, labelled state changes, and text
alternatives are release requirements. Color alone never communicates a
verdict, freshness state, direction, or availability.

Every durable public route supplies a concise route-specific title,
description, canonical path, and social-sharing metadata derived from the same
approved product contract as the visible page. Unknown routes and private
previews fail closed with `noindex`; search indexing and sitemap publication
remain disabled until an approved public origin and explicit production-launch
authorization exist. Metadata must not introduce broader coverage, performance,
customer, security, or commercial claims than the rendered page supports.

### 9.3 Commercial information architecture

The public experience uses a compact commercial shell around the existing
research routes. Its durable concepts are `Research`, `Intelligence`,
`Coverage`, and `Methodology`, with `Open Agent` as the persistent primary
action and sign-in shown only when required by the active access contract.
`Research` groups the existing Markets, Investors, and Companies surfaces; it
does not change their released-data semantics. The exact final header labels
and any new public routes require an approved implementation change before
deployment.

The primary header begins with `Research`, which links to the homepage, followed
by `Product`, `Intelligence`, `Coverage`, and `Methodology`. The navigation order
must reflect the landing-page hierarchy rather than placing a supporting
product-explanation page before the homepage.

After account contracts and exposure gates pass, the signed-in application uses
one stable daily-workflow shell: `Today`, `Data`, `News & Events`, `Agent`, and
`Library`. `Today` summarizes only entitled, released, time-stamped material;
it is not a live trading dashboard. Public marketing navigation and signed-in
application navigation remain distinct so account complexity does not make the
public research experience harder to scan.

The homepage follows this order:

1. outcome-led hero, evidence-boundary sentence, primary released-research
   action, and one secondary agent or sample-result action;
2. a real product-stage demonstration that binds question, released evidence,
   counterevidence, deterministic verdict, and audit identity;
3. four concise product modules for Data, Intelligence, Analysis, and
   Verification, with planned analysis visibly gated;
4. a release-derived coverage strip showing only current supported entities,
   source/filing periods, observation times, and freshness states;
5. professional workflow examples for research, strategy,
   investor-relations, consulting, and compliance-sensitive teams;
6. a plain-language trust section covering scope, provenance, review-required
   behavior, correction, revocation, and reproducibility;
7. a bounded trial or pilot-access action whose limits and data handling are
   visible before submission; and
8. a structured footer linking methodology, release operations, corrections,
   security and privacy information, terms, acceptable use, research
   disclaimer, product support, company identity, and contact information when
   those materials are approved for publication.

Supporting commercial content may include Product, Solutions, Coverage,
Methodology, Security and privacy, Pilot access or Pricing, About, Contact,
Corrections, and legal pages. Until a route and its content are approved, the
site must not expose an empty placeholder. Pricing must not be invented: before
commercial terms are approved, the conversion action is `Request pilot access`,
not a fabricated plan or discount. API documentation appears publicly only
after the corresponding customer API and support contract are authorized.

The sample result is a core product demonstration, not a decorative mockup. It
must come from a versioned eligible fixture or public-safe released result and
show the submitted claim, company and as-of date, claim-level verdict, verdict
meaning, supporting evidence, qualifications, compatible counterevidence,
citations, release identity, audit reference, and limitation. It must be clearly
labelled as a sample and must not imply a customer, endorsement, coverage level,
or production event that did not occur.

### 9.4 Agent experience

The agent experience should feel faster and more capable by reducing ambiguity
and making useful state visible, not by hiding boundaries. Before submission it
shows supported companies or scopes, the selected as-of date or release, input
limits, access mode, and relevant data-handling notice. During work it shows a
small number of truthful stages derived from durable task state. After work it
leads with the result and then exposes evidence, counterevidence,
qualifications, citations, release identity, and audit identity through
progressive disclosure.

The future multi-tool entry is labelled `Ask Quantify`. Intent routing maps a
bounded question to explore, analyze, compare, or explicit claim verification
and shows the interpreted job and scope before work begins. Users who do not
know what to ask receive a small set of contract-derived starters such as
research a company, track a released investor filing, explain an approved
policy record, inspect ETF or BTC-linked exposure, or verify a claim. A starter
links to an existing released view or enabled agent action; it never simulates
an unavailable tool. Ambiguous or unsupported questions return a short scope
choice or an available research route rather than silently choosing broader
authority.

Data retrieval, intelligence synthesis, analysis, and verification remain
visibly distinct in the agent output. Released structured facts are labelled
facts; narrative context is labelled context-only; derived explanations retain
their source bindings and statement type; and deterministic verdicts use the
meanings in section 6.
Unavailability, empty verified scope, refusal, and review-required are complete
product states with a clear safe next action. The UI must not replace them with
a model-generated answer, a hidden fallback, or an invitation to make a trade.

A review state uses one concise presentation: `Review required`, one
plain-language reason, and one safe next action. Release, policy, source-result,
statement, citation, and audit bindings remain available under details. The UI
must not say `sent`, `queued`, `assigned`, or `under review` until an authorized
persistent review workflow has durably recorded that exact state.

Authorization and entitlement failures use one mandatory grammar across data,
news, subscriptions, step-up authentication, workspaces, Library, and agent
tools:

~~~
This {resource} is unavailable under your current access. {Next safe action}.
~~~

The first sentence is not rewritten per endpoint. The second sentence contains
one approved action, such as sign in, verify identity, view available sources,
choose an included plan feature, or contact the workspace owner. A compact
label may distinguish `Sign-in required`, `Access changed`, `Plan inactive`,
`Verification required`, or `Workspace unavailable`, while a stable typed
reason code supports logs and support without exposing sensitive policy detail.
The same backend reason must render the same label, sentence grammar, and next
action everywhere. Verification verdict, unavailable-evidence, and
review-required states retain their separate meanings and are never presented
as access denials.

Every primary product surface uses the same user-task grammar:

1. **Job.** State the bounded research outcome the user can complete now.
2. **Required input.** Name the entity, time or release scope, and factual claim
   or released record needed to start.
3. **Output.** Name the exact released data, typed connection, cited analysis,
   or verification result the current contract can return.
4. **Boundary.** Keep unavailable data, source limits, access mode, and prohibited
   uses visible before the user acts.
5. **Next safe action.** After every complete, empty, unavailable, failed, or
   review-required state, offer a relevant non-advisory action such as revising
   the claim, inspecting coverage, reviewing methodology, or routing the result
   to an authorized human review process.

The homepage maps user intent to four product jobs: explore released data,
connect compatible facts, analyze evidence, or verify one company-analysis
claim. Each entry names its input, output, and current availability rather than
asking users to infer a workflow from the architecture. Until the public
research-task gate passes, analysis is displayed as a gated next state with no
enabled submission action. The current verification workspace groups its
available task into `Define scope` and `Write one claim`, derives readiness from
the actual form state, and keeps the output contract visible. Architecture and
policy detail use progressive disclosure and must not be repeated after the
user has entered the task flow.

Future multi-step research work may add a review workspace, task history,
release comparison, exports, and bounded typed tools only as their respective
contracts and authorization gates are completed. A polished interface does not
accelerate or bypass those gates.

### 9.5 Document-first delivery sequence

Commercial web work proceeds in the following order and returns to an earlier
stage whenever review finds an unsupported claim or product-state mismatch:

1. **Document.** Update this specification with the product promise, page
   hierarchy, current-versus-planned capability matrix, content rules, route
   proposal, access model, data handling, and acceptance criteria. Material
   policy, security, source-rights, cost, or legal decisions receive their
   required review before implementation.
2. **System.** Extend the existing visual tokens and shared components for the
   commercial shell, high-contrast signal surface, responsive typography,
   product-stage panels, state labels, motion reduction, and structured footer.
3. **Homepage.** Implement the concise commercial narrative and contract-valid
   product demonstration. Coverage and freshness are projections of the active
   public release index, never separately maintained marketing values.
4. **Agent.** Clarify the four research layers and the currently available
   verification task; improve truthful task progress, result hierarchy,
   citation and counterevidence presentation, review-required state,
   accessibility, and failure states without changing verdict authority or
   enabling a new action.
5. **Trust and conversion.** Add only approved methodology, coverage, privacy,
   security, correction, legal, and pilot-access content. Forms minimize data,
   disclose handling before submission, validate input, fail closed, and do not
   accept private research material unless the private-data prerequisite is
   complete.
6. **Verify.** Test copy against the capability matrix; verify release bindings,
   unavailable states, responsive layout, keyboard and screen-reader behavior,
   color independence, reduced motion, performance budgets, safe logging, form
   abuse controls, and route behavior. Conduct product, security, data-rights,
   and legal review in proportion to the claims being published.
7. **Ship.** Prepare a release-ready artifact and handoff. A production route,
   trial-policy change, commercial offer, analytics provider, or deployment is
   activated only with explicit authorization and its applicable release gates.

### 9.6 Released research surface contracts

The public web uses one coherent Quantify visual system across Overview,
Markets, Investors, Companies, Intelligence, and claim verification: a
soft-white canvas, lavender surfaces, the Quantify purple-to-magenta gradient,
consistent navigation, typography, spacing, and controls. Data-heavy pages
remain denser through compact cards, tabular figures, thin borders, and
prominent observation or filing dates, but every route must feel like the same
product. Task-progress UI, release selection, and richer citation presentation
arrive with the async task work above.

The web helps a user answer four bounded questions: “What released data is
available?”, “What compatible facts connect?”, “What can the cited evidence
explain?”, and “Is this company-analysis claim supported by the declared
evidence?” It shows availability, scope, statement type, citations,
counterpoints, limitations, and audit identity appropriate to the selected
job. Until model-assisted analysis is authorized, the third question links only
to deterministic metrics and source-bound explanations in released views.

The investor homepage centers reported holdings and quarter-over-quarter
changes. Each public-market manager page contains overview, holdings, changes,
allocation, and history modules. Holdings default to descending disclosed
portfolio weight. The UI says `Disclosed Portfolio Value`, not AUM, attributes
positions to the reporting manager rather than a named person's private
portfolio, and presents concentration only as a reported-position signal. The
VC experience has a separate schema and never invents ownership, position
value, or valuation precision.

The investor section exposes explicit `Public markets` and `Venture capital`
lenses. Venture cards show only firm identity, tracked official relationship
count, reviewed strategy labels, broad sector counts, and source coverage time.
Venture detail pages contain overview, a source-visible relationship table,
sector counts, and source limitations. They never reuse public-market value,
weight, concentration, change, or holdings-history modules. The words
`portfolio` and `investment` on a venture page always refer to the bounded
official-source sample, not a complete current fund portfolio.

The Venture company explorer is a deterministic projection of exact company IDs
already present in the active `vc-catalog.v1` release. It may show company name,
versioned broad sector, tracked firm count, firm names, disclosed
first-partnered years, and exact relationship sources. The overlap view counts
only identical released company IDs shared by two tracked firms and labels the
result `Tracked relationship overlap`. It is not ownership, syndication,
portfolio similarity, conviction, capital allocation, co-investment timing, or
evidence that the firms invested together. Neither view creates a public-company
mapping or adds a fact to the claim-verdict index.

The website and read-only investor catalog are public without sign-in. The
currently deployed claim-verification submission requires Cognito sign-in; a
separately authorized no-sign-up route may be enabled only under its bounded
policy, WAF, admission, and cost controls. Controls fail closed. Authentication
must not change the evidence or safety contract.

Use accessible text labels with all green/red or directional indicators; never
use color alone to convey a change or verdict. Investor pages must show the
reporting period, filing date, SEC accession/source, catalog release, and the
limitations of 13F coverage.

The released research navigation follows the commercial shell in section 9.3:
`Research`, `Product`, `Intelligence`, `Coverage`, and `Methodology`, with
`Open Agent` as the persistent current-task action. Research routes for
Markets, Investors, and Companies remain directly reachable from the homepage
and exact released entity graph.
`Markets` contains Macro, Rates, ETFs, Sectors, Crypto, and Commodities. Company
pages may connect only released manager positions initially; market cap,
valuation, insider, ETF, and event modules remain unavailable until their
corresponding approved releases exist. Earnings modules appear only for exact
company identities present in the active earnings release. Crypto assets have canonical
asset pages separate from company pages.

Cross-section navigation is a projection of the same typed released entity
graph, never a narrative or inferred relationship. Overview links every primary
section that has at least one available sub-release; one unavailable sublayer
must not label the entire primary section unavailable. A mapped security ticker
in an investor or ETF table may link to its exact Company page. Company is the
canonical integration surface for exact released manager, ETF, earnings, and
policy connections, with reciprocal links to their owning sections. Policy may
link an affected Company only when the typed policy record contains that exact
released ticker. Available connection controls are links; unavailable states
remain non-interactive and explicit.

Global search is a deterministic browser-side projection of exact identifiers
and display metadata already present in active public releases. Matching is
limited to normalized exact, prefix, word-prefix, and token-substring matching;
it is not narrative or semantic retrieval and may not create a new entity
relationship. Each result retains its entity type, stable released identifier,
destination, contributing release identities, and release state.

Release operations is an Intelligence subpage, not a new primary navigation
section. It exposes the bounded public release-index projection above in a
compact table with text-labelled status and freshness, short display hashes,
full machine-readable identifiers, current limitations, and a concise diagram
of the offline candidate lifecycle. It does not expose credentials, internal
audit records, private release artifacts, environment health, or invented
operational metrics.

Investor comparison is limited to two available reporting managers in the same
active investor release. A shared position means the exact released
`security_id` occurs in both current holdings tables. The interface may show
the two disclosed weights, disclosed values, reported share-change labels, and
their arithmetic percentage-point difference. It may not call the comparison
portfolio similarity, infer a trade, infer intent, combine positions into an
account, or rank one manager as better than another.

Market and crypto values always display an observation time and freshness
state. Because crypto trades continuously, its release policy uses a separate,
stricter staleness threshold. Directional color is descriptive of an observed
change only. Policy and event pages use `Affected assets` and clearly labelled
scenarios rather than presenting an up/down market reaction as certain.

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
