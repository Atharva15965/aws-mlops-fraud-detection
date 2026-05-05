"""Deploy the auto-retrain Lambda and wire it to the SNS topic."""
import json
import os
import sys
import time
import zipfile
from io import BytesIO
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
ACCOUNT_ID = boto3.client("sts").get_caller_identity()["Account"]

if len(sys.argv) < 2:
    print("Usage: python src/monitoring/deploy_retrain_lambda.py <SNS_TOPIC_ARN>")
    sys.exit(1)
TOPIC_ARN = sys.argv[1]

LAMBDA_NAME = "creditcard-fraud-retrain"
ROLE_NAME = "MLOpsFraudRetrainRole"

iam = boto3.client("iam")
lam = boto3.client("lambda", region_name=AWS_REGION)
sns = boto3.client("sns", region_name=AWS_REGION)

# 1. IAM role
TRUST = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}
POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "sagemaker:StartPipelineExecution",
            "Resource": "*",
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
            ],
            "Resource": "*",
        },
    ],
}
try:
    role = iam.create_role(
        RoleName=ROLE_NAME, AssumeRolePolicyDocument=json.dumps(TRUST)
    )
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="StartPipeline",
        PolicyDocument=json.dumps(POLICY),
    )
    time.sleep(10)
    print(f"Created IAM role: {ROLE_NAME}")
except iam.exceptions.EntityAlreadyExistsException:
    role = iam.get_role(RoleName=ROLE_NAME)
ROLE_ARN = role["Role"]["Arn"]

# 2. Package Lambda
buf = BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(Path(__file__).parent / "retrain_handler.py", arcname="retrain_handler.py")
buf.seek(0)
zip_bytes = buf.read()

# 3. Create Lambda
try:
    lam.create_function(
        FunctionName=LAMBDA_NAME,
        Runtime="python3.11",
        Role=ROLE_ARN,
        Handler="retrain_handler.lambda_handler",
        Code={"ZipFile": zip_bytes},
        Timeout=60,
        MemorySize=256,
        Environment={"Variables": {"PIPELINE_NAME": "creditcard-fraud-pipeline"}},
    )
    print(f"Created Lambda: {LAMBDA_NAME}")
except lam.exceptions.ResourceConflictException:
    lam.update_function_code(FunctionName=LAMBDA_NAME, ZipFile=zip_bytes)
    print(f"Updated Lambda: {LAMBDA_NAME}")

while lam.get_function_configuration(FunctionName=LAMBDA_NAME)["State"] != "Active":
    time.sleep(2)
LAMBDA_ARN = lam.get_function_configuration(FunctionName=LAMBDA_NAME)["FunctionArn"]

# 4. Allow SNS to invoke Lambda
try:
    lam.add_permission(
        FunctionName=LAMBDA_NAME,
        StatementId="AllowSNS",
        Action="lambda:InvokeFunction",
        Principal="sns.amazonaws.com",
        SourceArn=TOPIC_ARN,
    )
except lam.exceptions.ResourceConflictException:
    pass

# 5. Subscribe Lambda to SNS topic
sns.subscribe(TopicArn=TOPIC_ARN, Protocol="lambda", Endpoint=LAMBDA_ARN)
print(f"Subscribed {LAMBDA_NAME} to {TOPIC_ARN}")
