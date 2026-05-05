"""Lambda triggered by SNS when drift alarm fires. Re-runs the SageMaker Pipeline."""
import json
import os
import boto3

PIPELINE_NAME = os.environ.get("PIPELINE_NAME", "creditcard-fraud-pipeline")
sm = boto3.client("sagemaker")


def lambda_handler(event, context):
    print(f"Drift alarm received: {json.dumps(event)[:500]}")
    response = sm.start_pipeline_execution(
        PipelineName=PIPELINE_NAME,
        PipelineExecutionDescription="Auto-retrain triggered by drift alarm",
    )
    print(f"Started pipeline: {response['PipelineExecutionArn']}")
    return {
        "statusCode": 200,
        "body": json.dumps({"execution_arn": response["PipelineExecutionArn"]}),
    }
