# Private research-task pilot runbook

Scope: IAM-only `verify_claims` tasks against one approved indexed release. No
public route, live retrieval, account/upload capability, or fallback model.

The initial foundation deploy sets worker reserved concurrency to `0` and has
no SQS event-source mapping. Enable consumption only after the indexed-release
verifier bootstrap, signed active policy artifacts, capacity allocation, and
the post-deploy checks below are complete.

After the foundation is deployed, run the read-only inactive-pilot check before
publishing any control pointers or considering worker activation:

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_CHECK=1 \
  deploy/aws/check_research_task_pilot.sh \
  --env-file .quantify-private/research-task-pilot.env
~~~

It must report `mode: inactive`, worker concurrency `0`, no event-source
mapping, an immutable image digest, protected storage, and healthy alarms. It
does not publish a policy, enqueue work, enable the worker, or expose a route.

Before deployment, verify:

- Signed active runtime and release-gate policy hashes match the selected release.
- DynamoDB task/idempotency state and sharded counters have point-in-time recovery.
- SQS queue and DLQ have bounded receive counts; worker concurrency is reserved.
- Audit and policy buckets use KMS, deny public access, and retain immutable records.
- Worker IAM can read only the selected policy/release/audit resources and invoke no web retrieval.
- Alarms cover queue age/depth, DLQ messages, Lambda errors/throttles, admission rejection, audit-write failure, and policy revocation.

Before enabling consumption, separately confirm the selected release archive
replays the embedded V1 corpus exactly, then publish active signed policy and
evidence pointers through the authorized offline control path. Re-run the
read-only infrastructure check and retain its aggregate output with the
deployment record. Only a separately authorized activation procedure may set
non-zero worker concurrency and create the event-source mapping.

After control-plane selection and before any consumption activation, an
authorized operator may perform one empty-event bootstrap smoke. It temporarily
sets only Lambda reserved concurrency to `2`, leaves the event-source mapping
absent, invokes `{\"Records\":[]}`, then restores concurrency to `0` even when
the invocation fails. It must report `restored_mode: inactive`.

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_WORKER_BOOTSTRAP_SMOKE=1 \
  deploy/aws/smoke_research_task_worker.sh \
  --stack-name quantify-research-task-pilot --region us-east-2
~~~

For the frozen V1 fixture release, the checked-in
`fixtures/sec/release_v1_requests.json` declares the complete compile set.
First compile and replay-check it without AWS writes:

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_RELEASE_COMPILE=1 \
  deploy/aws/compile_research_task_release.sh \
  --fixtures-directory fixtures/sec \
  --release-declaration fixtures/sec/release_v1.json \
  --requests fixtures/sec/release_v1_requests.json \
  --validate-only
~~~

After the release-gate record is approved, repeat the same command with
`--policy-bucket <pilot-policy-bucket>` instead of `--validate-only`. The
compiler writes a single encrypted, content-addressed archive and refuses a
conflicting archive under the same release identity. It never retrieves live
SEC data and must never run from the worker.

Before archive persistence, produce and retain an immutable release-gate record
from validated source metadata, measured evaluation results, the exact
release-gate policy payload, and the required Lane A/B reviewer approval:

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_RELEASE_GATE=1 \
  deploy/aws/gate_research_task_release.sh \
  --fixtures-directory fixtures/sec \
  --release-declaration fixtures/sec/release_v1.json \
  --source-validations /approved/source-validations.json \
  --evaluation /approved/release-evaluation.json \
  --release-gate-policy /approved/release-gate-policy.json \
  --lane lane_a \
  --reviewer-approval /approved/reviewer-approval.json
~~~

The command prints a canonical record containing the policy hash, source and
evaluation hashes, gate reasons, reviewer approval hash, and result. A failed
gate exits non-zero and cannot be used to publish an archive or select an
evidence pointer.

Before the authorized archive and policy writes, validate the complete local
handoff bundle. It checks that the archive, approved gate record, runtime
policy, release-gate policy, and three-hash pointer document select exactly the
same release:

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_BUNDLE_CHECK=1 \
  deploy/aws/validate_research_task_bundle.sh \
  --archive /approved/indexed-release.json \
  --runtime-policy /approved/runtime-policy.json \
  --release-gate-policy /approved/release-gate-policy.json \
  --approval-record /approved/release-approval.json \
  --pointers /approved/pointers.json
~~~

Create `/approved/indexed-release.json` with the compiler's guarded
`--archive-output` mode, and retain the checker output with the release record.
The validator performs no AWS calls and does not verify a KMS signature; the
subsequent publisher and worker checks perform those cryptographic checks.

The offline publication command is deliberately separate from the worker and
requires credentials with `kms:Sign`, private artifact-bucket write access, and
policy-control-table transactional write access. The deployed worker role must
not receive those permissions. For the initial pointer publication, an
authorized operator runs:

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_POLICY_PUBLISH=1 \
  deploy/aws/publish_research_task_policy.sh \
  --runtime-policy /approved/runtime-policy.json \
  --release-gate-policy /approved/release-gate-policy.json \
  --evidence-release-manifest-hash <approved-release-hash> \
  --policy-bucket <pilot-policy-bucket> \
  --policy-table <pilot-policy-control-table> \
  --signing-key-arn <pilot-kms-signing-key-arn> \
  --signer-key-id <offline-publisher-identity> \
  --initial-publication
~~~

For every replacement, use `--expected-current-pointers` with the complete
three-hash pointer document retrieved and approved from the current control
state. The publisher refuses a replacement without that compare-and-swap
document. It is not a worker action and must not be run from Lambda.

Rollback criteria: any audit persistence failure, policy/release revocation, DLQ growth,
capacity breach, replay mismatch, or unbounded provider ambiguity. Disable the runtime
policy pointer first; do not delete audit records. Re-enable only with a new approved
policy pointer and replay evidence.

For an immediate, reversible worker stop, use the separately guarded emergency
procedure with the exact current policy payloads and pointers. It only publishes
a freshly signed runtime policy with `verify_claims` disabled. It first confirms
that every selected control is active, uses a three-hash compare-and-swap, and
prints the disabled pointer document. Retain that document: restoring service
requires an approved standard publication with it as `--expected-current-pointers`.

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_EMERGENCY_DISABLE=1 \
  deploy/aws/emergency_disable_research_task.sh \
  --runtime-policy /approved/current-runtime-policy.json \
  --release-gate-policy /approved/current-release-gate-policy.json \
  --expected-current-pointers /approved/current-pointers.json \
  --policy-bucket <pilot-policy-bucket> \
  --policy-table <pilot-policy-control-table> \
  --signing-key-arn <pilot-kms-signing-key-arn> \
  --signer-key-id <offline-publisher-identity>
~~~
