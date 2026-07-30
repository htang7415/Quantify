# Quantify AI Agent System Design

## 1. Purpose

Quantify is an evidence-constrained AI system for auditing factual claims in
public-company analysis. It is designed to answer a narrow question:

> Does a claim have local support in a declared, frozen SEC evidence pool, and
> does compatible evidence in that same pool defeat it?

Quantify is not a stock-prediction system, trading product, broker, valuation
engine, or personalized investment-advice service.

Its output is an auditable verification result, not an investment conclusion.

## 2. Product Contract

### Inputs

```text
company CIK
analysis as-of date
report text
eligible SEC form types
declared evidence and policy versions
```

### Outputs

```text
verified claims
unsupported claims
defeated claims with counterevidence
qualified claims where defeating evidence was disclosed
unclassified and non-factual statements
agent-resolution items
audit manifest and replay hashes
```

Every conclusion is limited to the declared evidence snapshot. Quantify never
claims that no contrary evidence exists outside that frozen scope.

## 3. Governing Rule

```text
Publish a claim only when cited evidence locally warrants it and compatible
uncited evidence in the same frozen pool does not defeat it.
```

The verifier, not the model, determines publication eligibility.

## 4. System Shape

```text
SEC evidence
→ normalize and apply policy
→ immutable evidence snapshot
→ one bounded structured extraction call
→ deterministic grounding and typed-claim validation
→ deterministic warrant and CE1 counterevidence analysis
→ fail-closed verdict composition
→ audit manifest and API response
```

Quantify is a single-turn AI verification harness. It is not a multi-agent
research workflow. The model may propose structured candidates; it never
changes evidence, policy, relation semantics, or final verdicts.

## 5. Architectural Boundaries

```text
domain schemas and policy
→ deterministic verification engine
→ evidence/snapshot and model adapters
→ orchestration, API, observability, deployment
```

### Deterministic engine

The engine owns:

- typed evidence, claims, relations, verdicts, and quality rules;
- evidence eligibility and restatement policy;
- local warrant and CE1 counterevidence analysis;
- verdict composition and temporal-persistence annotation.

It is a pure function of frozen inputs. It has no provider, network, cache,
clock, interface, or deployment dependency.

### Harness and adapters

The harness owns:

- SEC retrieval, content-addressed caching, and normalization;
- snapshot construction and manifest validation;
- bounded structured model extraction;
- deterministic report grounding and evidence-reference validation;
- bounded evidence acquisition and resolution records;
- orchestration, service/API adapters, caching, and observability.

No harness or deployment component may weaken verification semantics.

## 6. Evidence Model

V1 uses real SEC EDGAR company facts and filing metadata for Microsoft and
Apple only. Evidence records preserve identity, source, filing date, period,
unit, accession, provenance, eligibility, and policy context.

Evidence is normalized before use and frozen into an immutable snapshot. The
snapshot has a content-derived manifest hash. Restatement selection, form
resolution, period alignment, units, duplicate handling, and visibility are
explicit policy decisions.

Frozen SEC fixtures and their manifest are the reproducible development and
staging evidence source. Quantify does not fabricate financial observations.

This two-issuer scope is intentional. Foreign private issuers, unusual fiscal
calendars, nonstandard taxonomies, and segment-heavy or materially restated
disclosures require an explicit evidence-policy extension, fixtures, and
evaluation before becoming supported. They must not enter V1 by fallback.

## 7. Claim and Verdict Model

V1 supports closed typed factual relations, including threshold, comparison,
and historical-baseline claims. Canonical claim identity is derived from
normalized semantics, never trusted from model output.

Candidates with the same normalized semantics collapse to one canonical claim
before the six-claim proposal limit is applied. Their source span IDs are
retained in the audit record. This is a deployment contract: implementation
must not use model-supplied IDs or duplicate wording to bypass the cap.

```text
VERIFIED
UNSUPPORTED
DEFEATED
QUALIFIED
REQUIRES_AGENT_RESOLUTION
```

Local warrant and full-pool counterevidence are separate auditable decisions.
Hard counterevidence prevents publication. Ambiguity, invalid grounding,
invalid references, unknown policy versions, incomplete disclosure assessment,
and model failures fail closed.

Returning no verified claims is valid.

## 8. AI Agent Contract

The private V1 request path is model-enabled and permits exactly one bounded
Gemini structured extraction call per uncached verification request. The
extraction contract is pinned by model identifier, prompt hash, temperature,
output schema version, input limit, output limit, and timeout.

The current evaluated contract is:

```text
model:                   gemini-3.1-flash-lite
structured schema:       1.1.0
grounding:               deterministic report_span_id
timeout:                 4 seconds
maximum output:          256 tokens for the evaluated profile
```

The model selects supplied span IDs and evidence IDs; it does not reconstruct
report text or create report offsets. Invalid JSON, unknown span IDs, invalid
claim shapes, transport failures, or input-limit failures become explicit
fail-closed resolution results with a recorded reason.

The deployed private API configures no disclosure-detector or other secondary
model path. It does not silently add a second model call. Ambiguous disclosure
or extraction results remain `REQUIRES_AGENT_RESOLUTION`.

## 9. Auditability and Replay

Each result records replay-relevant context, including:

```text
evidence and snapshot hashes
source payload hashes and filing accessions
policy and normalizer versions
model, prompt, schema, temperature, and adapter versions
selection and restatement rationale
cache status
resolution records
audit-manifest hash
```

Identical frozen inputs and versions must produce identical deterministic
verification output. Model extraction remains separately measured and never
redefines engine truth.

The manifest intentionally excludes the submitted report text. It supports
evidence-and-engine replay, not independent end-to-end request reconstruction;
the caller must resupply the original report text to repeat extraction.

## 10. Safety and Operating Limits

```text
LLM extraction calls per snapshot: 1
maximum proposed claims:          6
maximum published claims:         6
maximum soft disclosures:         3
maximum licensed unknowns:        3
maximum brief length:             250 words
```

Quantify does not silently substitute filings, refresh historical evidence,
retry with another model, turn an extraction failure into `UNSUPPORTED`, or
omit failures from the audit record.

Credentials, report text, raw filing payloads, and private evaluation artifacts
must not enter source control, public logs, fixtures, or audit manifests.

## 11. Evaluation and Technical Readiness

Evaluation separates deterministic engine behavior from model extraction
behavior and separates mechanical from judgment cases.

The frozen corpus contains 20 mechanical and 10 judgment cases. Readiness
requires near-zero mechanical false positives, zero mechanical
VERIFIED↔DEFEATED instability, useful abstention, acceptable latency/cost, and
explicit SEC-insufficiency measurement.

The completed private readiness evaluation produced the following observations
on the frozen 30-case corpus. They are corpus results, not a statistical claim
about all issuers or all reports:

```text
normal-prompt repeated agreement: no instability observed (2 × 30 runs)
classified ↔ unclassified changes: 0
verified ↔ defeated flips:         0
mechanical verified ↔ defeated:    0
mean interactive latency:          0.819 seconds/report
mean interactive model cost:       $0.000426/report
technical readiness:               PROCEED, no blockers
```

Batch parity and throughput evidence are offline measurements only. They never
establish or alter interactive latency readiness.

## 12. Private Deployment Design

The target is a private AWS Lambda container image behind an API Gateway HTTP
API. This section is a design contract, not authorization to create cloud
resources. “Private” means the gateway allows only AWS Signature Version 4
(SigV4) requests from explicitly authorized IAM principals. The endpoint is
not anonymously invokable; no application-issued alternate authentication path
is permitted.

```text
source commit + frozen fixtures
→ tested immutable Lambda container image
→ Amazon ECR image digest
→ IAM-authenticated API Gateway staging route
→ frozen Microsoft smoke test
→ immutable Lambda version or rollback
```

### Deployed API allowlist

```text
GET  /healthz
POST /v1/companies/{cik}/verify
```

Review, resolution, and batch interfaces remain development/internal adapters
until deliberately added to a future deployment policy. The production
application factory and routing configuration enforce this allowlist; merely
documenting it is insufficient.

### Evidence and startup guarantees

The first image embeds:

```text
/app/fixtures/sec/
/app/fixtures/sec/manifest.json
```

Startup recomputes fixture hashes and fails readiness on a missing manifest,
missing file, or mismatch. The image digest and evidence-manifest hash belong
in the response audit record. Runtime evidence must never silently mean
“latest”; a later external snapshot design must use an explicitly named,
hash-validated immutable object generation.

The production application factory wires only this embedded-fixture evidence
provider. Live SEC retrieval adapters may exist for development and snapshot
creation, but are disabled and unreachable from the deployed request path.

### Runtime profile

```text
region:              selected AWS staging region
memory:              512 MiB
timeout:             10 seconds
reserved concurrency: explicit per-environment cap when quota allows; new-account staging
                      defaults to 0 (the unreserved Lambda pool)
authentication:      API Gateway HTTP API AWS_IAM / SigV4
release:             digest-pinned Lambda image; immutable published staging alias
```

The Lambda image must pin Python and dependencies, contain only the validated
fixtures, use the Lambda runtime’s restricted execution user, keep application
files read-only, enforce report size limits, and emit redacted structured logs.
The AWS boundary is a narrow API Gateway payload-v2-to-ASGI adapter; the
provider-neutral FastAPI production factory remains the in-process allowlist.

Because V1 verification includes extraction, `GEMINI_API_KEY` is obtained only
from one explicitly pinned AWS Secrets Manager version at Lambda initialization
through a dedicated least-privilege execution role. The image, repository,
environment, logs, manifests, and private artifacts must never contain the
secret value. The execution role may read only the declared secret ARN. If the
pinned secret, Gemini model, or extraction schema is unavailable, the request
fails closed; Quantify neither switches models nor performs an unrecorded
fallback retry.

Private IAM access, API throttling, report/model input caps, one model call per
request, and the private staging monthly model-cost reservation ledger bound V1
capacity and spend. The first staging stack uses the unreserved Lambda pool
because its new AWS account quota is too small to reserve capacity while
retaining Lambda's required unreserved allocation. Per-identity and tenant
quotas remain deferred.

Private staging emits aggregate-only request metrics and pinned-model failure
records to CloudWatch Logs. It also creates alarms for Lambda errors,
near-timeout duration, throttles, API Gateway 5xx responses, and pinned-model
unavailability. The staging stack routes these alarms to one SNS email
subscription after the recipient confirms AWS's subscription message; logs and
alarms must never contain report text, SEC payloads, or secret values.

## 13. Deployment Quality Gate

Before staging promotion, require:

```text
tests pass inside the production image
fixture manifest validates at startup
engine import boundary passes
dependency, container, and secret scans pass
container runs as non-root
/healthz succeeds
frozen Microsoft smoke request matches expected verdict and audit hashes
identical request returns deterministic cached output
logs contain no report text, API key, or SEC payload
timeout and invalid structured output fail closed
unavailable pinned model or schema returns the typed fail-closed response
deployed request path cannot invoke live SEC retrieval or secondary model calls
audit persistence failure returns its typed fail-closed response
monthly cost-cap rejection occurs before the model call
caller role has only the two API invoke permissions
API throttling is configured
```

Promotion, traffic changes, external release, secret binding, and cloud resource
creation are separate ship actions requiring explicit user authorization.

## 14. Next Plan

The production application factory, enforced route allowlist, fixture-only
evidence provider, typed unavailable-model response, duplicate collapse,
digest-pinned AWS Lambda image configuration, and authenticated SigV4 smoke
tooling are implemented and covered by focused tests. Private staging is
deployed in `us-east-2` with an immutable ECR image, pinned Secrets Manager
version, API Gateway AWS_IAM authentication, and a successful authenticated
smoke request. It is not a production release.

The deployed staging smoke, ECR basic scan, and a schema/redaction inspection
of the Lambda and API access logs have passed. The repeatable
`deploy/aws/validate_observability.sh` check reports only record counts and
rejects unexpected log fields or smoke-report/credential-like fragments.

The deployed staging baseline includes a private S3 audit-manifest
bucket: public access is blocked, objects require AWS KMS encryption, the
Lambda role may only put canonical manifests, and lifecycle expiration is a
reversible 90-day default (30, 90, or 365 days). A deployed authenticated
smoke request created and validated the canonical encrypted object. A storage
failure prevents publication of the verification result with a typed fail-closed
response.

Private staging also has a distinct one-hour `QuantifyCallerRole`. It trusts
only the configured operator identity and permits only the two deployed API
routes; it has no S3, Secrets Manager, Lambda, or administrative permissions.
The authenticated smoke contract passes while using that role rather than the
administrator session.

Private staging applies a stage-wide API Gateway token-bucket limit of two
requests per second with a burst of two. This bounds uncached pinned-model
calls because V1 performs at most one extraction per verification request.
CloudWatch alarms when more than twenty verified requests arrive in five
minutes.

With the approved $10 paid Gemini cap, staging pins the standard
`gemini-3.1-flash-lite` price contract ($0.25 input and $1.50 output per
million tokens) and reserves a conservative maximum cost in a private DynamoDB
ledger before each uncached model call. The first request of the month reserved
12,384 micro-USD; a failed reservation returns the typed fail-closed cap
response before Gemini is invoked.

Gemini AI Studio project-spend controls and the $10 in-service reservation cap
are configured. AWS's new-account Lambda profile currently provides ten total
concurrent executions and rejects a modest quota-increase request; it cannot
yet support a reserved-concurrency allocation while retaining AWS's required
unreserved pool. Keep the staging cap at zero and recheck the account quota
after normal private use. Never create a production stack merely because
private staging checks pass.

### Authenticated public production candidate

The intended V1 public release remains a single-agent verification API, not a
public research chatbot. It consists of two separately deployed stacks:

```text
public internet
→ API Gateway HTTP API with Cognito JWT access-token scope
→ narrow public agent Lambda: POST /v1/agent/verify
→ SigV4-only private production core
→ one bounded Gemini extraction + deterministic verifier
```

The public edge accepts only `cik`, `analysis`, and `as_of_date`; it validates
the bounded input, returns only the `quantify_verify` safe contract, and hides
provider, secret, IAM, and report-detail error information. API Gateway must
require the `.../verify` OAuth scope before invoking Lambda. The public agent
role may invoke only the private core's `POST /v1/companies/*/verify` route.
The core verifier, evidence fixtures, audit store, Gemini secret, and model
cost ledger stay private.

Offline Gemini Batch parity is quality evidence only; its queue time cannot
satisfy the interactive latency gate. The Batch Quantify branch must reuse the
same versioned extraction instruction, response schema, model, temperature,
and input/output envelope as the deployed extractor. A reduced or separately
worded Batch prompt is not comparable production evidence. The prompt-only
branch remains a distinct model-visible baseline.

`deploy/aws/template.yaml` is the production-core candidate when supplied a
separate stack name, `StageName=production`, and `ReleaseAlias=production`.
`deploy/aws/public_agent_template.yaml` is the public-edge candidate. Both
deployment scripts refuse to act without their production-specific
authorization variables.

The first authenticated production release is deployed in `us-east-2`. Its
private core accepts only the two AWS_IAM routes, while its public edge accepts
only the scoped JWT route. It uses a separate Gemini key restricted to the
Generative Language API and a pinned AWS Secrets Manager version. The public
OAuth smoke proves an unauthenticated request is rejected and a scoped token
receives only the safe contract. Core and edge alarms are `OK`, the ECR basic
scan reports zero findings, and the replacement production log group passes the
redaction inspection.

Credential rotation must create a new API-restricted Gemini key, pin the new
Secrets Manager version in a new immutable image release, and retire the old
key before it can be reused. Secret values must never be printed by provider
CLIs or stored in repository files. A trailing secret-file newline is trimmed
at Lambda initialization before a value can reach a provider HTTP header.

An external AI agent may use Quantify only through the narrow
`quantify_verify(cik, analysis, as_of_date)` adapter. For the public edge, it
must use a Cognito OAuth access token with only the configured `verify` scope;
the restricted AWS caller role applies only to private staging. The agent must
preserve every returned verdict and evidence-scope limitation, and must not turn
a verification result into investment advice, retrieve additional evidence, or
introduce a multi-agent workflow.

During the controlled public beta, run the read-only production-beta check to
require complete stacks, `OK` alarms, a nonempty private audit store, and a
monthly cost-ledger reservation at or below its configured cap. It reports only
aggregate counts and cost figures, never reports, audit payloads, or secrets.

## 15. Deferred Capabilities

Do not add these capabilities to V1 deployment:

```text
CE2 voting or CE3 ambiguity rules
coverage gate
price data, valuation, or brokerage integration
vector database, LangGraph, or multi-agent framework
live market feeds
model training
general web search
public unauthenticated API access
durable per-tenant quota or billing system
```

## 16. Governance

Authority order:

```text
explicit user request
→ AGENTS.md
→ this specification
→ versioned schemas, policies, manifests, fixtures, and evaluation artifacts
→ existing code and tests
```

Semantic changes require versioned contracts, focused tests, replay-aware audit
updates, and renewed evaluation when the model-visible contract changes.
