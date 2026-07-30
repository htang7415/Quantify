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

## Private AWS staging

The deployment contract lives in [`deploy/aws/`](deploy/aws/). It packages the
existing fixture-only FastAPI production factory as a digest-pinned AWS Lambda
container image, exposes only the two V1 routes through API Gateway HTTP API,
and requires AWS IAM SigV4 authentication. The Gemini API key is read only from
one immutable AWS Secrets Manager version at Lambda initialization. All scripts
refuse external actions unless their operation-specific authorization variable
is set; AWS CLI v2 deploys the CloudFormation stack directly, so no SAM CLI is
required. The repository currently has one IAM-authenticated private staging
stack; production creation, promotion, and access expansion remain separate
decisions.

## Public production candidate

The public release candidate is intentionally a narrow agent API, not an
anonymous verifier or investment chatbot:

```text
Cognito OAuth access token with verify scope
→ POST /v1/agent/verify
→ private IAM-authenticated Quantify core
```

The public Lambda validates a bounded `cik`, `analysis`, and `as_of_date`, then
returns only verdicts, frozen evidence scope, audit hash, and the required
non-investment-advice limitation. It cannot expose the core verifier response,
read the Gemini key, retrieve new evidence, or perform extra model calls.

[`deploy/aws/production.env.example`](deploy/aws/production.env.example),
[`deploy/aws/deploy_production_core.sh`](deploy/aws/deploy_production_core.sh),
and [`deploy/aws/deploy_public_agent.sh`](deploy/aws/deploy_public_agent.sh)
prepare separate production-core and public-edge stacks. The scripts require
explicit production authorization variables and are not deployment
instructions by themselves. A unique Cognito domain prefix and a separate
production Gemini key are required before any public ship.

The first authenticated production release is deployed. The public endpoint
requires a Cognito access token carrying the configured `verify` scope; a
missing token is rejected before Lambda runs. Keep the OAuth client secret
outside the repository and use the public smoke script only from a trusted
operator environment.

For a local external-agent integration on macOS, provision the existing client
secret once into the login Keychain, then invoke the narrow public adapter. The
secret is never written to the repository, shell output, or an environment file:

```bash
QUANTIFY_AUTHORIZE_PUBLIC_AGENT_KEYCHAIN_PROVISION=1 \
  deploy/aws/provision_public_agent_keychain.sh

deploy/aws/public_agent_verify.sh \
  --cik 0000789019 \
  --analysis-file ./analysis.txt \
  --as-of-date 2024-07-30
```

The adapter can call only `POST /v1/agent/verify` and prints only the safe
Quantify response contract. It does not receive AWS administrator credentials,
the private core URL, or the Gemini key.

## Controlled public beta monitoring

Run the read-only health gate while the first agent is operating. It checks both
CloudFormation stacks, all configured alarms, private audit-manifest presence,
and the current DynamoDB model-cost reservation without printing request or
audit content:

```bash
QUANTIFY_AUTHORIZE_AWS_PRODUCTION_BETA_CHECK=1 \
  deploy/aws/check_production_beta.sh
```

## Local agent tool

After loading the private staging environment values, a local agent can assume
`QuantifyCallerRole` and invoke the private verifier without storing report text:

```bash
python deploy/aws/agent_verify.py --cik 0000789019 \
  --analysis-file ./analysis.txt --as-of-date 2024-07-30
```

For a reproducible staging test, use `--analysis-fixture
fixtures/reports/msft_revenue_growth_v1.json` instead.

The output contains only verified claim verdicts, frozen evidence scope, audit
hash, and the required non-investment-advice limitation.

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

The Batch Quantify parity path must use the same versioned extraction
instruction, response schema, model, temperature, and input/output envelope as
the deployed extractor. A compact or separately worded Batch prompt is not
comparable production evidence. The prompt-only comparator remains a distinct
model-visible baseline by design.

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
