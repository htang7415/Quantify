# Quantify

Quantify Research Referee audits factual company-analysis claims against a
declared, frozen evidence pool.

## First deterministic slice

The initial engine accepts an immutable SEC evidence snapshot and a typed
threshold claim. It returns one of:

- `verified`: the cited fact warrants the claim and every compatible eligible
  fact in the snapshot agrees;
- `unsupported`: the cited fact is missing, ineligible, or does not warrant the
  claim; or
- `counterevidence`: the cited fact warrants the claim, but another compatible
  eligible fact in the same snapshot directly defeats it.

`counterevidence` is intentionally a pre-disclosure outcome. The future
disclosure step will compose it into a final `defeated`, `qualified`, or
human-review verdict.

The included fixture contains real SEC XBRL revenue facts for Quantum
Corporation, including a later restatement of FY2023 revenue. It proves the
counterevidence path without fabricated financial data.

Run the slice with:

```sh
python3 -m pytest
```
