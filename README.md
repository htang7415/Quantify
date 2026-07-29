# Quantify

Quantify Research Referee audits factual company-analysis claims against a
declared, frozen evidence pool.

## Current deterministic foundation

The implemented engine accepts an immutable SEC evidence snapshot and typed
threshold or period-comparison claims. It provides:

- deterministic evidence selection under a named restatement policy;
- local-warrant and CE1 counterevidence analysis as separate audit outputs;
- final `verified`, `unsupported`, `defeated`, `qualified`, or agent-resolution
  verdict composition after disclosure assessment; and
- exact report-span and evidence-reference validation for future model output.

The offline `verify_report(...)` workflow connects those steps end to end for
frozen inputs. A provider-specific extractor may supply an `ExtractionResult`,
but it cannot bypass deterministic grounding, reference validation, or verdict
composition.

## Week 6 evaluation gates

`AutonomousResolutionLoop` can make one auditable disclosure-assessment attempt
for a fail-closed agent-resolution item. It never changes a claim, snapshot, or
verification policy; unresolved items stay unresolved. Its action record is
included in the replay manifest.

Prompting-parity artifacts compare the exact frozen 20 mechanical and 10
judgment cases using pinned model and prompt metadata. They are loaded and
scored offline—model execution belongs to a manual or scheduled evaluation,
not ordinary CI. `assess_readiness(...)` then applies versioned quality, cost,
latency, SEC-coverage, and parity thresholds to return `proceed` or `pause`.
`run_readiness_evaluation(...)` joins that artifact with the real frozen corpus
and explicit scheduled-evaluation measurements; it rejects mismatched case IDs
or expected outcomes instead of manufacturing a commercial decision.

Run the same gate from files with `python -m quantify.evaluation.readiness_cli`
and the mechanical/judgment case files, SEC snapshot directory, parity artifact,
and operational-measurement artifact. Add `--fail-on-pause` when a scheduled
release gate should return a nonzero status for a `pause` decision.

Before a provider run, `python -m quantify.evaluation.parity_worklist_cli`
emits only opaque request IDs and report text. Its required separate reference
mapping contains the frozen outcomes and must remain evaluator-side.

After both provider paths finish, `python -m quantify.evaluation.parity_compile_cli`
reconciles their opaque outcome files with that private mapping. It rejects
missing, duplicate, unknown, or mismatched request IDs and writes the versioned
parity artifact consumed by the readiness CLI.

The pinned scheduled-evaluation profile is Gemini 3.1 Flash-Lite Batch at
temperature `0`, with a $0.05 total token-cost cap for the 60-request run.
`estimate_evaluation_cost(...)` must pass before any provider work is started.

## SEC evidence path

`SecCompanyFactsClient` retrieves SEC Company Facts cache-first, preserves the
exact payload and SHA-256, and paces cache misses. `build_revenue_snapshot(...)`
normalizes the initial standardized US-GAAP revenue metric, applies the selected
restatement policy, and returns an immutable snapshot with a replayable audit
manifest. Both the SEC transport and structured extractor are provider-neutral
interfaces, keeping external calls outside the deterministic engine.

The metric router also supports gross profit, operating income, net income,
operating cash flow, capital expenditure, cash, and diluted share count. Debt
is derived only by aggregating normalized current and noncurrent components;
gross, operating, and cash-flow margins are derived only from compatible,
eligible numerator and revenue facts. Every derived value preserves its input
evidence IDs rather than silently inferring a value from a single XBRL fact.

The SEC adapter also resolves 10-K and 10-Q filing records from cached company
submissions at the requested cutoff date, retaining amendments for later
restatement selection. Before snapshot construction, the engine records an
explicit eligibility result for provenance, entity scope, units, period
alignment, filing cutoff, and transformation status.

Normalization preserves SEC reporting periods: 10-K facts use `FY`, while
10-Q facts use `Q1`–`Q3`. Interim start and end dates are retained exactly,
including year-to-date durations; Quantify does not infer standalone quarters.

Snapshots reject unresolved competing eligible facts by default. The Quantum
restatement fixture explicitly opts into such a conflict only as a regression
case for CE1 behavior; normal snapshots apply a restatement policy first.

The raw `msft_companyfacts.json` and `aapl_companyfacts.json` fixtures are exact
SEC Company Facts response bytes. Their hashes, CIKs, and source endpoints are
locked in `fixtures/sec/manifest.json` and tested offline. Compact
`*_revenue_regression.json` files are deliberately separate, curated subsets
used by focused engine tests. Quantum includes a later FY2023 restatement to
prove the counterevidence path without fabricated financial data.

Run the slice with:

```sh
python3 -m pytest
```
