from pathlib import Path


def test_private_pilot_template_has_no_api_gateway_and_has_recovery_controls():
 t=(Path(__file__).parents[1]/"deploy/aws/research_task_pilot_template.yaml").read_text()
 assert "AWS::ApiGateway" not in t and "AWS::Serverless::Api" not in t
 assert "AWS::DynamoDB::Table" in t and "PointInTimeRecoveryEnabled: true" in t
 assert "AWS::SQS::Queue" in t and "RedrivePolicy" in t
 assert "Tags: [{Key: QuantifyPilotMode, Value: inactive}, {Key: QuantifyPilotRevision, Value: event-source-v2}]" in t
 assert "WorkerReservedConcurrency" in t and "Default: 0" in t
 assert "PolicyControlTable" in t and "QUANTIFY_POLICY_CONTROL_TABLE_NAME" in t
 assert "QUANTIFY_POLICY_ARTIFACT_BUCKET_NAME" in t
 assert "PolicyArtifactBucket:" in t and "BlockPublicPolicy: true" in t
 assert "PolicySigningKey:" in t and "KeyUsage: SIGN_VERIFY" in t
 assert "evidence-releases/v1/*" in t
 assert "quantify.research_task_lambda.handler" in t
 assert "AWS::Lambda::EventSourceMapping" in t and "Condition: ConsumeTasks" in t
 assert "EnableTaskConsumption: {Type: String, Default: 'false'" in t
 assert "TaskMaximumConcurrency: {Type: Number, Default: 2, MinValue: 2, MaxValue: 2}" in t and "MaximumConcurrency: !Ref TaskMaximumConcurrency" in t
 assert "WorkerErrorsAlarm" in t and "DlqMessagesAlarm" in t
 assert "TreatMissingData: notBreaching" in t


def test_private_pilot_deploy_script_requires_explicit_authorization_and_digest_image():
 script=(Path(__file__).parents[1]/"deploy/aws/deploy_research_task_pilot.sh").read_text()
 assert "QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_DEPLOY" in script
 assert "IMAGE_URI must be an immutable @sha256 reference" in script
 assert '"${IMAGE_URI##*@}" == "$IMAGE_DIGEST"' in script
 assert '"WorkerReservedConcurrency=0"' in script and '"EnableTaskConsumption=false"' in script and '"TaskMaximumConcurrency=2"' in script
 assert "AWS_REGION must be us-east-2" in script
 assert "cloudformation deploy" in script


def test_private_pilot_readiness_check_is_guarded_and_read_only():
 script=(Path(__file__).parents[1]/"deploy/aws/check_research_task_pilot.sh").read_text()
 checker=(Path(__file__).parents[1]/"deploy/aws/check_research_task_pilot.py").read_text()
 assert "QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_CHECK" in script
 assert "get-function-concurrency" in checker and "list-event-source-mappings" in checker
 assert "cloudformation deploy" not in checker and "put-object" not in checker


def test_private_pilot_release_compiler_is_guarded_and_has_no_live_sec_path():
 script=(Path(__file__).parents[1]/"deploy/aws/compile_research_task_release.sh").read_text()
 compiler=(Path(__file__).parents[1]/"deploy/aws/compile_research_task_release.py").read_text()
 assert "QUANTIFY_AUTHORIZE_RESEARCH_TASK_RELEASE_COMPILE" in script
 assert "PYTHONPATH" in script
 assert "QUANTIFY_PYTHON_BIN" in script
 assert "EmbeddedSecSnapshotProvider" in compiler
 assert "SecCompanyFactsClient" not in compiler and "http" not in compiler


def test_private_pilot_release_gate_is_guarded_and_offline_only():
 script=(Path(__file__).parents[1]/"deploy/aws/gate_research_task_release.sh").read_text()
 gate=(Path(__file__).parents[1]/"deploy/aws/gate_research_task_release.py").read_text()
 assert "QUANTIFY_AUTHORIZE_RESEARCH_TASK_RELEASE_GATE" in script
 assert "PYTHONPATH" in script
 assert "QUANTIFY_PYTHON_BIN" in script
 assert "gate_release" in gate
 assert "boto3" not in gate and "put_object" not in gate


def test_private_pilot_bundle_validation_is_guarded_and_read_only():
 script=(Path(__file__).parents[1]/"deploy/aws/validate_research_task_bundle.sh").read_text()
 validator=(Path(__file__).parents[1]/"deploy/aws/validate_research_task_bundle.py").read_text()
 assert "QUANTIFY_AUTHORIZE_RESEARCH_TASK_BUNDLE_CHECK" in script
 assert "PYTHONPATH" in script
 assert "QUANTIFY_PYTHON_BIN" in script
 assert "validate_bundle" in validator
 assert "boto3" not in validator and "put_object" not in validator


def test_private_pilot_offline_admission_is_guarded_and_not_an_http_route():
 script=(Path(__file__).parents[1]/"deploy/aws/admit_research_task.sh").read_text()
 admission=(Path(__file__).parents[1]/"deploy/aws/admit_research_task.py").read_text()
 assert "QUANTIFY_AUTHORIZE_RESEARCH_TASK_ADMISSION" in script
 assert "--dry-run" in admission and "validated_no_write" in admission
 assert "FastAPI" not in admission and "http" not in admission


def test_private_pilot_activation_is_guarded_and_bounded():
 script=(Path(__file__).parents[1]/"deploy/aws/activate_research_task_pilot.sh").read_text()
 activation=(Path(__file__).parents[1]/"deploy/aws/activate_research_task_pilot.py").read_text()
 assert "QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_ACTIVATION" in script
 assert "MaximumConcurrency" in activation and "ReservedConcurrentExecutions" in activation
 assert "FastAPI" not in activation and "http" not in activation
