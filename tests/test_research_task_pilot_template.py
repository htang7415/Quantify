from pathlib import Path
def test_private_pilot_template_has_no_api_gateway_and_has_recovery_controls():
 t=(Path(__file__).parents[1]/"deploy/aws/research_task_pilot_template.yaml").read_text()
 assert "AWS::ApiGateway" not in t and "AWS::Serverless::Api" not in t
 assert "AWS::DynamoDB::Table" in t and "PointInTimeRecoveryEnabled: true" in t
 assert "AWS::SQS::Queue" in t and "RedrivePolicy" in t and "ReservedConcurrentExecutions: 2" in t
