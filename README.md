# Quantify

## Evidence-bound AI investment research agent

Quantify is an AI investment research agent for self-directed investors,
learners, analysts, and institutions that want to understand companies,
markets, and policy through inspectable evidence.

The product has four distinct layers: released data, typed intelligence, cited
analysis, and deterministic claim verification. It does not simply generate a
persuasive answer: exact released records retain their source, time, scope, and
limitations; model-assisted analysis stays untrusted until validated; and only
deterministic code controls a claim verdict and audit identity.

Use the public product across four bounded research jobs:

- browse source-bound records from an active release;
- connect only compatible facts with exact typed identities and periods;
- inspect deterministic metrics and source-bound explanations while the
  general model-assisted research-answer task remains gated; or
- verify one company-analysis claim and receive a verdict, evidence scope,
  limitation, and audit identity.

[Visit Quantify](https://d3ljopjg1qmt4.cloudfront.net/)

## Investor intelligence

The public Quantify investor section tracks reported positions for a focused
set of public-market investment managers. It shows disclosed Form 13F value, portfolio
weights, quarter-over-quarter share changes, concentration, allocation, and
five-quarter position history from a frozen, versioned SEC filing catalog.

The tracker is public without sign-in. Its figures cover only each reporting
manager's disclosed 13F information table; they are not AUM, personal holdings,
or evidence of investment intent. Source-review failures remain visible with
derived values withheld instead of estimated.

Global search uses only exact identifiers and display metadata from active
public releases. Investor comparison joins two available reporting managers
only when the same released security ID appears in both holdings tables; it
keeps disclosed values, weights, and reported share changes separate and does
not infer portfolio similarity, trades, or intent.

Venture capital is a separate investor lens with its own release contract. The
initial release contains 24 manually reviewed firm-to-company relationships
across Sequoia Capital, Andreessen Horowitz, Founders Fund, and Khosla Ventures.
It publishes only what each frozen official source supports: company, a broad
versioned sector classification, disclosed first-partnered year when available,
and the exact source. Unknown stage, participation role, and follow-on status
remain `undisclosed`; ownership, check size, value, weight, AUM, valuation,
markup, and return are neither inferred nor displayed. These private-company
relationships never enter the public-company ownership index.

## Connected public intelligence

The public overview connects the frozen investor release to deterministic
company ownership views. A company page sums only the disclosed rows belonging
to Quantify's tracked reporting managers and links every row back to its SEC
filing. It does not claim total institutional or beneficial ownership.

Markets, macro, ETF flows, cryptocurrency, earnings, policy, and high-impact
events have public routes and explicit release states. They do not display
illustrative or model-generated observations. Values remain unavailable until
an approved source, methodology, freshness policy, correction path, immutable
release, and focused tests exist. The initial cryptocurrency contract is
deliberately limited to BTC and ETH and distinguishes ETF/ETP flows from direct
token ownership.

The first released crypto connection is intentionally narrower than a market
feed. It projects reviewed crypto-linked ETP security identities over the
existing frozen 13F catalog, showing exact disclosed manager positions and
their SEC filing sources. Spot prices, market capitalization, flows, wallets,
and network statistics remain unavailable. A versioned source register blocks
technically public APIs whose terms do not permit Quantify's public commercial
display.

The first active market layer is an official U.S. Treasury par yield-curve
release. It displays the dated 1-month through 30-year curve and a deterministic
2s10s spread, with source, publication time, freshness deadline, methodology,
and manifest. It is not a real-time bond feed or a rate forecast.

The active ETF-flow layer uses exact SEC Form N-PORT Item B.6 fields for SPY,
QQQ, SMH, IWM, and the technology ETF VGT. Each fund retains its own report
date and exact three-month window. Monthly net flow is filed sales plus
reinvestment minus redemptions; it is never inferred from a change in net
assets. The release is a delayed three-month filing view, not a daily
creation/redemption feed.

The ETF-holdings layer publishes the reviewed top ten Form N-PORT positions for
VGT, QQQ, and SMH, preserving each fund's own report date and filing source.
Ticker connections use only the versioned reviewed security map; unmapped rows
remain visibly unmapped. This is a delayed top-ten snapshot, not a complete or
live portfolio.

The first active macro layer is a bounded U.S. Bureau of Labor Statistics
release. It shows headline CPI, core CPI, and unemployment for one declared
period. CPI rates are deterministic year-over-year calculations from exact BLS
index inputs; unemployment is the exact published seasonally adjusted rate.
The release records retrieval time, freshness, source rows, methodology, the
BLS secondary-use disclaimer, and immutable hashes. It is not a live feed or a
macro forecast.

The first active earnings layer uses the existing frozen SEC Company Facts
release for AAPL and MSFT. It publishes exact quarterly revenue and diluted EPS,
deterministic year-over-year comparisons, fiscal and calendar periods, filing
dates, accessions, and SEC source links. It does not publish consensus
estimates, surprise labels, guidance interpretation, or future earnings dates.

The first active policy layer covers three official actions: the latest FOMC
target-range decision and next scheduled meeting, the final joint financial
data standards rule, and the final BIS advanced-computing export-license review
rule. Every event records authority, dates, status, document identity, source
hash, and typed exact details. Policy pages do not claim a certain market
reaction or publish rate probabilities, forecasts, or recommendations.

The Intelligence section also includes a read-only release-operations page.
It projects exact status, freshness, observation time, release ID, manifest
hash, and limitation fields from the public release index. It is not an uptime
or internal-review dashboard.

## Grounded analysis boundary

The repository defines `research-answer.v1` for future explore, analyze, and
compare tasks. The contract separates released facts, deterministic
calculations, warranted interpretation, narrative context, and open questions.
The local provider-free validator checks an independently admitted entity and
release scope, exact citation authorization, reference integrity, calculation
replay, interpretation warrants, deterministic answer composition, model and
verifier attribution, audit identity, and prohibited investment-output
language. It returns a detached canonical document or fails closed.

This validator is not connected to a model, worker, API, or public form. It
does not make general AI analysis available and cannot create a verification
verdict.

The first provider-free evidence-search slice is also implemented locally.
`approved-evidence-search-request.v1` accepts one company, as-of date, frozen
release identity, and at most 32 exact metric/period/unit keys. The adapter
searches only the already compiled `IndexedEvidenceRelease` and returns a
versioned `approved-evidence-search-result.v1`: exact structured facts with
canonical decimal strings and citation authorizations, plus explicit
`exact_fact_not_found` outcomes. Request and result hashes make replay visible.
It has no similarity ranking, narrative fallback, live retrieval, model call,
verdict authority, worker, or public route.

The deterministic calculation slice adds `approved-calculation-request.v1` and
`approved-calculation-result.v1`. A request references only released-fact
statement IDs from one exact search result; it cannot provide values, formulas,
code, source text, or model instructions. The provider-free adapter performs
bounded sums, differences, percent changes, and percentage-point changes with
decimal round-half-even behavior. It rejects reversed or incompatible periods,
mixed metrics for comparisons, unit mismatches, missing facts, zero percent
baselines, and release/hash drift. Its output replays directly as a
`research-answer.v1` deterministic-calculation statement. The internal tool
name is policy-known for tests but is not enabled in deployed policy, connected
to a worker, or exposed through an API or public form.

The release-scoped narrative slice is also implemented locally through
`approved-narrative-context-request.v1` and
`approved-narrative-context-result.v1`. A request binds an exact company,
as-of date, frozen release, optional filing accessions, and a maximum of 16
chunks; it cannot provide a prompt, URL, source text, ranking instruction,
provider, or licensed-news request. The provider-free adapter returns only
compiled disclosure text with exact filing date, HTTPS source, character span,
chunk hash, replay hashes, and explicit truncation or unavailable outcomes.
Every authorization is fixed to `narrative_disclosure` and `context_only`, with
no evidence ID or measurement. Indexed-release archive `1.2.0` replays the new
source metadata. Empty-narrative `1.1.0` archives remain replayable; a legacy
archive containing narrative chunks fails closed until it is recompiled with
the required metadata. The internal tool remains policy-gated and is not
connected to a model, worker, API, public form, semantic retriever, or verdict
path.

The review boundary is implemented locally through
`approved-review-task-request.v1` and `approved-review-task-result.v1`. A
request binds one concise admitted question and typed reason to the exact
release, runtime and release-gate policy hashes, source-result hashes,
statement or citation IDs, origin, and audit manifest. The provider-free
adapter returns an idempotent `requires_review` record whose ID derives from the
canonical request hash. It cannot assign a reviewer, approve, persist, notify,
publish, call a model, or compose a verdict. The policy-known internal tool is
not enabled in deployed policy or exposed through an API or public form.

The bounded planning boundary is implemented locally through one canonical
research-intent matrix, `agent-plan-request.v1`, `agent-plan-result.v1`, and
`model-attempt.v1`. The plan request persists only a hash of the exact admitted
question and binds company, date, release, policy, tool, prompt, action, and
model-call scope. A model proposal can name only ordered intent-compatible
stages; it cannot include arguments, facts, citations, answers, URLs, code, or
verdicts. Deterministic validation accepts or rejects the proposal, and the
model-attempt record preserves provider/model/version, prompt and tool hashes,
usage, cost, output hash, and validation state without raw user or provider
text. The provider-free evaluation boundary performs no model or tool call,
retry, persistence, API action, or deployment. Connecting a pinned planner and
executing independently typed tool requests remain separately gated work.

## Build an offline public-release candidate

The candidate coordinator compiles reviewed local ETF-flow and ETF-holdings
inputs in dependency order, validates the pinned investor catalog and active
index, records replay and rollback bindings, and atomically writes a staging
directory:

~~~shell
python scripts/build_public_release_candidate.py \
  --investor-catalog web/src/data/investorCatalog.json \
  --etf-flow-input tests/fixtures/public_data/etf_flows_2026-03-31.json \
  --etf-holdings-input tests/fixtures/public_data/etf_holdings_2026q2.json \
  --security-metadata scripts/investor_security_metadata.json \
  --active-release-index web/src/data/publicReleaseIndex.json \
  --target-directory /tmp/quantify-release-candidate-2026-08-14 \
  --run-at 2026-08-14T05:00:00Z
~~~

The command performs no network acquisition, active-index mutation,
publication, or deployment. The generated manifest remains
`ready_for_review`.

For a reviewed Form 13F bundle, replace `--investor-catalog` with
`--investor-source-manifest /path/to/bundle/manifest.json`. The coordinator
then compiles the investor catalog cache-only, records the source-manifest and
security-metadata hashes, and rebuilds the crypto-exposure projection bound to
that investor release. Every SEC resource must be declared by URL, relative
path, media type, and SHA-256 in `investor-sec-source-bundle.v1`; missing,
changed, undeclared, or unused resources fail closed. Creating or updating the
bundle from SEC remains a separate explicitly run acquisition step.

That acquisition step is the only command in this workflow that may contact
SEC. It requires an identifying user agent and never overwrites an existing
target:

~~~shell
python scripts/acquire_investor_sec_bundle.py \
  --user-agent "Quantify Research htang7415@gmail.com" \
  --cache-dir /path/to/sec-cache \
  --target-directory /path/to/new-13f-bundle \
  --created-at 2026-08-14T02:00:00Z \
  --quarters 5
~~~

Review the resulting `manifest.json` and declared files before passing the
bundle to compilation. Acquisition preserves the exact evidence even when the
tracked managers have different latest reporting periods; compilation still
fails closed until their latest periods align. Acquisition does not publish a
catalog or approve a release.

Check a target quarter offline before attempting compilation:

~~~shell
python scripts/check_investor_filing_readiness.py \
  --source-manifest /path/to/new-13f-bundle/manifest.json \
  --target-report-period 2026-06-30 \
  --checked-at 2026-08-14T03:30:00Z \
  --output /path/to/new-readiness-report.json
~~~

The content-addressed report classifies each configured manager as `ready`,
`waiting`, or `ahead` from the exact bundle snapshot. It always records
`candidate_build_authorized: false`; readiness is not source review,
publication approval, or deployment authorization.

The cache-only investor compiler can also be reviewed independently:

~~~shell
python scripts/build_investor_catalog.py \
  --source-manifest /path/to/bundle/manifest.json \
  --metadata scripts/investor_security_metadata.json \
  --output /tmp/investorCatalog.json \
  --compilation-record /tmp/investorCompilationRecord.json
~~~

The venture compiler is also cache-only. It accepts one reviewed official-source
bundle, validates strict identities, fields, hosts, hashes, dates, and compiled
sector counts, then writes a catalog and a replay-visible compilation record:

~~~shell
python scripts/build_vc_catalog.py \
  --source tests/fixtures/public_data/vc_portfolio_sources_2026-08-13.json \
  --output /tmp/vcCatalog.json \
  --record-output /tmp/vcCompilationRecord.json
~~~

The compilation record always states `publication_authorized: false`. The
compiler performs no network retrieval, active-index mutation, publication, or
deployment.

To stage a reviewed Venture change with the rest of the public release, add the
source bundle to the coordinator command:

~~~shell
python scripts/build_public_release_candidate.py \
  --investor-catalog web/src/data/investorCatalog.json \
  --venture-source tests/fixtures/public_data/vc_portfolio_sources_candidate_2026-08-14.json \
  --etf-flow-input tests/fixtures/public_data/etf_flows_2026-03-31.json \
  --etf-holdings-input tests/fixtures/public_data/etf_holdings_2026q2.json \
  --security-metadata scripts/investor_security_metadata.json \
  --active-release-index web/src/data/publicReleaseIndex.json \
  --target-directory /tmp/quantify-release-candidate-2026-08-14 \
  --run-at 2026-08-14T05:00:00Z
~~~

The checked-in candidate adds Thrive Capital and General Catalyst from frozen
firm-operated pages. It is candidate evidence only: it does not change the
active four-firm Venture release. Any Venture identity or relationship-scope
change is a Lane B change and requires full review before a separately
authorized promotion.

## Review a public-release candidate

The deterministic review gate replays the candidate, validates every artifact
and rollback binding, compares it with the exact active index and catalogs, and
classifies it under the versioned public gate policy:

~~~shell
python scripts/review_public_release_candidate.py \
  --candidate-directory /tmp/quantify-release-candidate-2026-08-14 \
  --active-release-index web/src/data/publicReleaseIndex.json \
  --active-catalog-directory web/src/data \
  --policy policies/public_candidate_gate_policy.v2.json \
  --reviewed-at 2026-08-14T06:00:00Z \
  --output /tmp/publicCandidateReview.json
~~~

Lane A means the deterministic routine thresholds passed and a spot review is
still required. Lane B means structural changes or thresholds require full
review. Every record is content-addressed, carries exact rollback bindings,
and states `promotion_authorized: false`. The command cannot approve, publish,
deploy, or mutate the active index.

`public-refresh-candidate.v2`, `public-candidate-review.v2`, and
`public-candidate-gate-policy.v2` add the optional Venture compilation and its
exact firm/relationship diff. Omitting `--venture-source` preserves the active
Venture binding.

## What Quantify can do

### Verify factual company claims

Give Quantify a short company analysis or a specific claim. It identifies
eligible factual assertions and determines whether the declared evidence
supports them.

Examples:

- “Is this revenue-growth statement supported by the available filings?”
- “Can this period-comparison claim be published as written?”
- “Which facts in this company note need review before publication?”

### Find what changes the conclusion

Quantify does more than locate supporting passages. It evaluates compatible
counterevidence and important disclosed qualifications, so users can see when a
claim is incomplete, overstated, or defeated.

### Make AI-generated research safer

Use Quantify as a publication gate for analyst work or AI-generated company
research. It turns a draft claim into a clear evidence decision before that
claim is shared with an investment committee, client, research team, or wider
audience.

### Preserve an audit trail

Every result identifies its evidence scope and includes an audit reference. A
reader can understand what release, policy, and verification context produced
the conclusion.

## What you receive

| Outcome | Meaning |
| --- | --- |
| **Verified** | The declared evidence warrants the claim and compatible evidence does not defeat it. |
| **Qualified** | The claim is supportable only with an important disclosed limitation. |
| **Unsupported** | The declared evidence does not establish the claim. |
| **Defeated** | Compatible counterevidence defeats the claim. |
| **Review required** | The evidence or grounding is too ambiguous to publish safely. |

Quantify also separates:

- verified facts;
- qualifications;
- counterevidence;
- agent inferences;
- open research questions; and
- items that need human review.

This makes it clear what has been proven, what is interpretation, and what
still needs work.

## How Quantify earns trust

~~~
Your claim or analysis
        ↓
AI identifies structured candidate claims
        ↓
Evidence grounding and counterevidence checks
        ↓
Deterministic verdict, scope, and audit trail
~~~

The AI agent can organize the work and explain the result. It cannot decide
that a claim is verified. Quantify’s deterministic verification layer is the
only authority that can issue a verified outcome.

This means Quantify is designed to be:

- **Source-constrained** — conclusions stay inside a named evidence release.
- **Counterevidence-aware** — support and defeating evidence are treated
  separately.
- **Audit-ready** — results retain the context needed to understand the
  conclusion.
- **Conservative by default** — missing, ambiguous, or unavailable information
  produces a safe review state, not an invented answer.

## Built for serious research workflows

Quantify is designed for people and teams who need disciplined public-company
research:

- self-directed investors who want to check a thesis;
- research analysts preparing a company note;
- investment teams reviewing factual assertions;
- AI products that need an evidence-verification layer; and
- institutions that require clear provenance and reviewability.

The Quantify website is publicly accessible without sign-up. Submitting a
verification request through the current agent experience requires sign-in and
remains deliberately bounded to maintain reliability and responsible access.

## Clear boundaries

Quantify is an investment research product with deterministic verification as
its trust layer. It does not:

- predict prices or market movements;
- make buy, sell, hold, allocation, or position-size recommendations;
- execute trades or manage a portfolio;
- claim that no contrary information exists outside the declared evidence; or
- replace a user’s judgment, diligence process, or professional advice.

## The goal

Quantify makes investment research more understandable, inspectable,
reviewable, and trustworthy.

Instead of asking only, “Can an AI explain this?”

Ask, “What does the data show, how is the analysis grounded, and can this claim
be proven?”

[Visit Quantify](https://d3ljopjg1qmt4.cloudfront.net/)
