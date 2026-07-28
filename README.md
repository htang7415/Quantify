# Quantify

Quantify Research Referee audits factual company-analysis claims against a
declared, frozen evidence pool.

## Current deterministic foundation

The implemented engine accepts an immutable SEC evidence snapshot and typed
threshold or period-comparison claims. It provides:

- deterministic evidence selection under a named restatement policy;
- local-warrant and CE1 counterevidence analysis as separate audit outputs;
- final `verified`, `unsupported`, `defeated`, `qualified`, or human-review
  verdict composition after disclosure assessment; and
- exact report-span and evidence-reference validation for future model output.

The offline `verify_report(...)` workflow connects those steps end to end for
frozen inputs. A provider-specific extractor may supply an `ExtractionResult`,
but it cannot bypass deterministic grounding, reference validation, or verdict
composition.

## SEC evidence path

`SecCompanyFactsClient` retrieves SEC Company Facts cache-first, preserves the
exact payload and SHA-256, and paces cache misses. `build_revenue_snapshot(...)`
normalizes the initial standardized US-GAAP revenue metric, applies the selected
restatement policy, and returns an immutable snapshot with a replayable audit
manifest. Both the SEC transport and structured extractor are provider-neutral
interfaces, keeping external calls outside the deterministic engine.

Snapshots reject unresolved competing eligible facts by default. The Quantum
restatement fixture explicitly opts into such a conflict only as a regression
case for CE1 behavior; normal snapshots apply a restatement policy first.

Offline fixtures contain real SEC XBRL revenue facts for Microsoft, Apple, and
Quantum Corporation. Quantum includes a later FY2023 restatement to prove the
counterevidence path without fabricated financial data. Each fixture is listed
with its SEC payload SHA-256 in `fixtures/sec/manifest.json`.

Run the slice with:

```sh
python3 -m pytest
```
