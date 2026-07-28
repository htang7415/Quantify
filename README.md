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
