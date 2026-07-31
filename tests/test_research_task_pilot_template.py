from pathlib import Path


def test_private_pilot_template_has_no_api_gateway_and_has_recovery_controls():
 t=(Path(__file__).parents[1]/"deploy/aws/research_task_pilot_template.yaml").read_text()
 assert "AWS::ApiGateway" not in t and "AWS::Serverless::Api" not in t
 assert "AWS::DynamoDB::Table" in t and "PointInTimeRecoveryEnabled: true" in t
 assert "AWS::SQS::Queue" in t and "RedrivePolicy" in t
 assert "WorkerReservedConcurrency" in t and "Default: 0" in t
 assert "PolicyControlTable" in t and "QUANTIFY_POLICY_CONTROL_TABLE_NAME" in t
 assert "QUANTIFY_POLICY_ARTIFACT_BUCKET_NAME" in t
 assert "PolicyArtifactBucket:" in t and "BlockPublicPolicy: true" in t
 assert "PolicySigningKey:" in t and "KeyUsage: SIGN_VERIFY" in t
 assert "evidence-releases/v1/*" in t
 assert "quantify.research_task_lambda.handler" in t
 assert "AWS::Lambda::EventSourceMapping" in t and "Condition: ConsumeTasks" in t
 assert "EnableTaskConsumption: {Type: String, Default: 'false'" in t
 assert "TaskMaximumConcurrency" in t and "MaximumConcurrency: !Ref TaskMaximumConcurrency" in t
 assert "WorkerErrorsAlarm" in t and "DlqMessagesAlarm" in t


def test_private_pilot_deploy_script_requires_explicit_authorization_and_digest_image():
 script=(Path(__file__).parents[1]/"deploy/aws/deploy_research_task_pilot.sh").read_text()
 assert "QUANTIFY_AUTHORIZE_RESEARCH_TASK_PILOT_DEPLOY" in script
 assert "IMAGE_URI must be an immutable @sha256 reference" in script
 assert "AWS_REGION must be us-east-2" in script
 assert "cloudformation deploy" in script
