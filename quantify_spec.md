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

The target is a private Google Cloud Run service. This section is a design
contract, not authorization to create cloud resources.

```text
source commit + frozen fixtures
→ tested immutable container image
→ Artifact Registry image digest
→ IAM-authenticated zero-traffic staging revision
→ frozen Microsoft smoke test
→ immutable production revision or rollback
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
region:             us-central1
CPU / memory:       1 vCPU / 512 MiB
min instances:      0
max instances:      2
concurrency:        1
authentication:     Cloud Run IAM
release:            immutable revisions with zero-traffic smoke testing
```

The image must pin Python and dependencies, run as non-root, honor `PORT`, use
a production Uvicorn command, keep application files read-only, enforce report
size limits, and emit redacted structured logs.

Because V1 verification includes extraction, `GEMINI_API_KEY` is required for
the private staging service. Secret Manager injects one numbered, pinned secret
version at runtime through a dedicated least-privilege service identity. No
secret may enter the image, repository, logs, manifests, or private artifacts.
If the pinned Gemini model or extraction schema is unavailable, the request
fails closed with a typed service-unavailable response; Quantify neither
switches models nor performs an unrecorded fallback retry.

Billing alerts are not hard quotas. Private IAM access, a maximum of two
single-concurrency instances, report/model input caps, and one model call per
request bound V1 capacity and spend. They do not implement a per-identity or
per-day request quota; durable tenant quotas and billing remain deferred.

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
```

Promotion, traffic changes, external release, secret binding, and cloud resource
creation are separate ship actions requiring explicit user authorization.

## 14. Next Plan

The production application factory, enforced route allowlist, fixture-only
evidence provider, typed unavailable-model response, duplicate collapse,
locked non-root container, and digest-pinned private staging configuration are
implemented and covered by focused tests. No Google Cloud resource has been
created and no staging request has been sent.

Complete private Cloud Run staging without expanding product scope:

```text
1. After explicit bootstrap authorization, create the named Artifact Registry,
   dedicated runtime identity, and least-privilege Secret Manager access.
2. After explicit build authorization, run the reproducible Cloud Build job and
   record its resulting immutable image digest.
3. After explicit deployment authorization, create the IAM-authenticated,
   zero-traffic tagged staging revision using that digest and secret version.
4. After explicit staging-smoke authorization, run authenticated staging smoke
   tests, review telemetry, then decide whether to promote.
```

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
