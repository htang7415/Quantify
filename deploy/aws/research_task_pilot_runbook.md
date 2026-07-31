# Private research-task pilot runbook

Scope: IAM-only `verify_claims` tasks against one approved indexed release. No
public route, live retrieval, account/upload capability, or fallback model.

The initial foundation deploy sets worker reserved concurrency to `0` and has
no SQS event-source mapping. Enable consumption only after the indexed-release
verifier bootstrap, signed active policy artifacts, capacity allocation, and
the post-deploy checks below are complete.

Before deployment, verify:

- Signed active runtime and release-gate policy hashes match the selected release.
- DynamoDB task/idempotency state and sharded counters have point-in-time recovery.
- SQS queue and DLQ have bounded receive counts; worker concurrency is reserved.
- Audit and policy buckets use KMS, deny public access, and retain immutable records.
- Worker IAM can read only the selected policy/release/audit resources and invoke no web retrieval.
- Alarms cover queue age/depth, DLQ messages, Lambda errors/throttles, admission rejection, audit-write failure, and policy revocation.

Rollback criteria: any audit persistence failure, policy/release revocation, DLQ growth,
capacity breach, replay mismatch, or unbounded provider ambiguity. Disable the runtime
policy pointer first; do not delete audit records. Re-enable only with a new approved
policy pointer and replay evidence.
