# Private research-task pilot runbook

Scope: IAM-only `verify_claims` tasks against one approved indexed release. No
public route, live retrieval, account/upload capability, or fallback model.

The initial foundation deploy sets worker reserved concurrency to `0` and has
no SQS event-source mapping. Enable consumption only after the indexed-release
verifier bootstrap, signed active policy artifacts, capacity allocation, and
the post-deploy checks below are complete. The currently authorized us-east-2
pilot is active with worker and mapping maxima both at `2`; use the active-mode
check below for ongoing readiness.

After the foundation is deployed, run the read-only inactive-pilot check before
publishing any control pointers or considering worker activation:

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_CHECK=1 \
  deploy/aws/check_research_task_pilot.sh \
  --env-file .quantify-private/research-task-pilot.env
~~~

For a deployed pilot whose private environment file is unavailable, pass only
the non-secret stack and audit-bucket identifiers directly; include
`--mode active` for the current pilot.

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_CHECK=1 \
  deploy/aws/check_research_task_pilot.sh \
  --stack-name quantify-research-task-pilot --region us-east-2 \
  --audit-bucket <pilot-audit-bucket> --mode active
~~~

It must report `mode: inactive`, worker concurrency `0`, no event-source
mapping, an immutable image digest, protected storage, and healthy alarms. It
does not publish a policy, enqueue work, enable the worker, or expose a route.

Before and after any authorized queue-saturation exercise, retain the result of
the read-only queue-depth check. Its maximums are supplied by the approved
exercise plan; it neither sends nor consumes messages and fails when the DLQ
contains any message.

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_QUEUE_LOAD_CHECK=1 \
  deploy/aws/check_research_task_queue_load.sh \
  --queue-url <pilot-task-queue-url> --dlq-url <pilot-task-dlq-url> \
  --region us-east-2 --maximum-in-flight <approved-limit> \
  --maximum-backlog <approved-limit>
~~~

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

An IAM-authorized operator can validate a candidate request without writing
task, counter, or queue state through the guarded offline admission command.
It takes a local JSON object with `cik`, `analysis`, and `as_of_date` and
prints only hashes and selected policy identifiers in `--dry-run` mode. It is
not a public API and must not be used to enqueue work while the pilot is
inactive. Admission proves both the base and any approved acquisition snapshot
exist in the selected immutable release before it reserves capacity or queues
work.

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_ADMISSION=1 \
  deploy/aws/admit_research_task.sh --dry-run \
  --request /approved/request.json --idempotency-key <operator-key> \
  --task-table <pilot-task-table> --task-queue-url <pilot-queue-url> \
  --task-dlq-url <pilot-dlq-url> --policy-bucket <pilot-policy-bucket> \
  --policy-table <pilot-policy-control-table> \
  --signing-key-arn <pilot-kms-signing-key-arn> \
  --shard-count 2 --daily-task-limit 10 \
  --monthly-reservation-limit-micro-usd 10000 --reservation-micro-usd 500
~~~

After the dry-run and bootstrap smoke succeed, an explicitly authorized
operator may activate the private consumer. The procedure verifies current
KMS-signed controls and the selected archive before it changes the stack. It
sets worker reserved concurrency to `2` and the SQS mapping maximum to `2`
(the AWS minimum); it does not create a public route or enqueue a task.

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_ACTIVATION=1 \
  deploy/aws/activate_research_task_pilot.sh \
  --stack-name quantify-research-task-pilot --region us-east-2
~~~

For a task already recorded as `failed_unresolved` or `unavailable`, use one
new idempotency key with `--retry-task-id <original-task-id>` instead of a new
request. The service links the retry to the original task and applies a new
bounded reservation; it never auto-retries or changes provider/model policy.

For safe status, queued-task cancellation, or explicit reconciliation, use the
operator lifecycle command. It never accepts research text and cannot enqueue
work. Reconciliation remains fail-closed when no attributable provider lookup
adapter is available.

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_OPERATION=1 \
  deploy/aws/operate_research_task.sh --operation status --task-id <task-id> \
  --task-table <pilot-task-table> --policy-bucket <pilot-policy-bucket> \
  --policy-table <pilot-policy-control-table> \
  --signing-key-arn <pilot-kms-signing-key-arn> \
  --shard-count 2 --daily-task-limit 10 \
  --monthly-reservation-limit-micro-usd 10000 --reservation-micro-usd 500
~~~

To pause consumption for an approved recovery exercise, use the guarded
deactivation control. It removes only the event-source mapping and sets the
worker cap to zero; it neither deletes messages nor changes policy pointers.
Re-activate only through the preflighted activation command above.

~~~
QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_DEACTIVATION=1 \
  deploy/aws/deactivate_research_task_pilot.sh \
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
  --reviewer-approval /approved/reviewer-approval.json \
  --approval-output /approved/release-approval.json
~~~

The command prints a canonical record containing the policy hash, source and
evaluation hashes, gate reasons, reviewer approval hash, and result. A failed
gate exits non-zero and cannot be used to publish an archive or select an
evidence pointer.

After the immutable gate record is approved, repeat the compiler command with
`--policy-bucket <pilot-policy-bucket> --approval-record /approved/release-approval.json`
instead of `--validate-only`. The compiler verifies that exact approved record
before it writes one encrypted, content-addressed archive and refuses a
conflicting archive under the same release identity. It never retrieves live
SEC data and must never run from the worker.

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

## Private release-catalog staging

The catalog is a separate post-gate action. Its authoritative staged copy is
stored only in the private artifact bucket and has no public-read permission.
A named reviewer signs the stage action with the offline KMS key. The initial
stage creates its pointer only if absent; replacement or revocation requires
the previous action hash, so another reviewer cannot overwrite it silently.

~~~
QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_STAGE=1 \
  deploy/aws/stage_private_release_catalog.sh \
  --action promote --stage private-pilot --reviewer-id <reviewer-id> \
  --release-id <release-id> --release-manifest-hash <approved-release-hash> \
  --approval-record /approved/release-approval.json \
  --catalog-bucket <pilot-policy-bucket> \
  --signing-key-arn <pilot-kms-signing-key-arn>
~~~

To revoke staged serving, use `--action revoke` with no release inputs and
`--expected-current-action-hash <previous-action-hash>`. This records an
immutable signed revocation and moves only the private stage pointer. Public
delivery remains prohibited until a separate authorization.

Verify the selected pointer, signed action, and referenced catalog through the
read-only verifier. It returns only hashes, action state, and reviewer identity.

~~~
QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_CHECK=1 \
  deploy/aws/check_private_release_catalog.sh \
  --stage private-pilot --catalog-bucket <pilot-policy-bucket> \
  --signing-key-arn <pilot-kms-signing-key-arn>
~~~

### Private signed-URL catalog delivery

The private delivery stack is separate from staging. It creates a dedicated,
versioned, public-blocked delivery bucket with a customer-managed KMS key, a
CloudFront Origin Access Control, a trusted key group, and a distribution
bound to the existing global CloudFront WAF. The delivery bucket policy permits
only `s3:GetObject` for `release-catalogs/v1/*` from that distribution. Never
give the distribution access to the policy-artifact bucket or use this flow to
promote a catalog publicly.

Generate and retain an RSA private key outside the repository. Create its
CloudFront public-key resource once, using only the public PEM:

~~~
QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_KEY_CREATE=1 \
CATALOG_PUBLIC_KEY_FILE=/secure/path/catalog-public-key.pem \
CATALOG_PUBLIC_KEY_NAME=quantify-private-catalog-readers \
CATALOG_PUBLIC_KEY_CALLER_REFERENCE=<immutable-random-value> \
deploy/aws/create_private_catalog_public_key.sh
~~~

Deploy the private distribution with the returned public-key ID and the
approved global WAF ARN. This action does not copy catalog content or grant
public read access.

~~~
QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_DELIVERY_DEPLOY=1 \
AWS_STACK_NAME=quantify-private-catalog-delivery \
CATALOG_PUBLIC_KEY_ID=<cloudfront-public-key-id> \
CLOUDFRONT_WAF_WEB_ACL_ARN=<global-cloudfront-waf-arn> \
deploy/aws/deploy_private_catalog_delivery.sh
~~~

After each separately approved stage or revocation, copy only the catalog
prefix to the delivery bucket. Retrieve `DeliveryBucketName` and
`DeliveryKmsKeyArn` from the delivery stack outputs. The command is additive:
it never deletes an object version.

~~~
QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_DELIVERY_SYNC=1 \
CATALOG_SOURCE_BUCKET=<pilot-policy-bucket> \
CATALOG_DELIVERY_BUCKET=<delivery-stack-output> \
CATALOG_DELIVERY_KMS_KEY_ARN=<delivery-stack-output> \
deploy/aws/sync_private_catalog_delivery.sh
~~~

Before accepting a delivery change, verify an unsigned URL returns `403`, an
expired signed URL returns `403`, and a short-lived valid signed URL returns
`200`. Do not log a signed URL, its policy, its signature, or any catalog
body. The RSA private key is never a CloudFormation parameter, stack output,
or repository artifact.

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
