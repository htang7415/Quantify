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

## Interactive latency control

The normal Gemini harness uses a four-second extraction request deadline and a
one-second bounded disclosure-assessment deadline. It performs no automatic
model retries: a timeout becomes an agent-resolution item or an ambiguous
disclosure assessment, never a published claim or omission accusation.

Gemini Batch is retained for offline prompting-parity and stability evaluation.
Its queue time is an auditable throughput metric, not interactive latency, and
Batch artifacts cannot satisfy the commercial readiness latency gate. That gate
requires a versioned `interactive_runtime` measurement from the normal
one-call extraction path.

## Interactive readiness evaluation

`quantify.evaluation.interactive_cli` is the only path that produces the
versioned `interactive_runtime` artifact accepted by the readiness gate. It
requires the fixed 20 mechanical plus 10 judgment cases, a matching repeated-
run stability artifact, a pinned model/prompt profile, explicit per-request
and total cost caps, and `--execute`. It uses the normal one-call extractor;
it never uses Batch latency, retries a model call, or saves credentials.

Run it only after separately authorizing the standard-provider spend. Store
the resulting no-secret artifact under `.quantify-private/` and pass it to the
readiness CLI together with the parity and stability artifacts.
