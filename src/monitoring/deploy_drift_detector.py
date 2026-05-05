"""Deploy drift_detector Lambda + schedule it via EventBridge."""
import json
import os
import time
import zipfile
from io import BytesIO
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
PROJECT_BUCKET = os.environ["PROJECT_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
ACCOUNT_ID = boto3.client("sts").get_caller_identity()["Account"]

LAMBDA_NAME = "creditcard-fraud-drift-detector"
ROLE_NAME = "MLOpsFraudDriftRole"
RULE_NAME = "creditcard-fraud-drift-schedule"

iam = boto3.client("iam")
lam = boto3.client("lambda", region_name=AWS_REGION)
eventbridge = boto3.client("events", region_name=AWS_REGION)

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
            "Action": ["s3:GetObject", "s3:ListBucket"],
            "Resource": [
                f"arn:aws:s3:::{PROJECT_BUCKET}",
                f"arn:aws:s3:::{PROJECT_BUCKET}/*",
            ],
        },
        {"Effect": "Allow", "Action": "cloudwatch:PutMetricData", "Resource": "*"},
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
        RoleName=ROLE_NAME, PolicyName="DriftPolicy", PolicyDocument=json.dumps(POLICY)
    )
    time.sleep(10)
    print(f"Created role: {ROLE_NAME}")
except iam.exceptions.EntityAlreadyExistsException:
    role = iam.get_role(RoleName=ROLE_NAME)
ROLE_ARN = role["Role"]["Arn"]

# 2. Package + deploy Lambda
buf = BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(Path(__file__).parent / "drift_detector.py", arcname="drift_detector.py")
buf.seek(0)
zip_bytes = buf.read()

env = {
    "PROJECT_BUCKET": PROJECT_BUCKET,
    "LOOKBACK_HOURS": "1",
    "DRIFT_THRESHOLD_STD": "2.0",
}

try:
    lam.create_function(
        FunctionName=LAMBDA_NAME,
        Runtime="python3.11",
        Role=ROLE_ARN,
        Handler="drift_detector.lambda_handler",
        Code={"ZipFile": zip_bytes},
        Timeout=120,
        MemorySize=512,
        Environment={"Variables": env},
    )
    print(f"Created Lambda: {LAMBDA_NAME}")
except lam.exceptions.ResourceConflictException:
    lam.update_function_code(FunctionName=LAMBDA_NAME, ZipFile=zip_bytes)
    time.sleep(3)
    lam.update_function_configuration(
        FunctionName=LAMBDA_NAME, Environment={"Variables": env}
    )
    print(f"Updated Lambda: {LAMBDA_NAME}")

while lam.get_function_configuration(FunctionName=LAMBDA_NAME)["State"] != "Active":
    time.sleep(2)
LAMBDA_ARN = lam.get_function_configuration(FunctionName=LAMBDA_NAME)["FunctionArn"]

# 3. EventBridge rule (hourly schedule)
eventbridge.put_rule(
    Name=RULE_NAME,
    ScheduleExpression="rate(1 hour)",
    State="ENABLED",
    Description="Hourly drift check on fraud-detection captures",
)
eventbridge.put_targets(Rule=RULE_NAME, Targets=[{"Id": "1", "Arn": LAMBDA_ARN}])

try:
    lam.add_permission(
        FunctionName=LAMBDA_NAME,
        StatementId="AllowEventBridge",
        Action="lambda:InvokeFunction",
        Principal="events.amazonaws.com",
        SourceArn=f"arn:aws:events:{AWS_REGION}:{ACCOUNT_ID}:rule/{RULE_NAME}",
    )
except lam.exceptions.ResourceConflictException:
    pass

print(f"Scheduled {LAMBDA_NAME} hourly via {RULE_NAME}")
print(
    f"\nManual run:  aws lambda invoke --function-name {LAMBDA_NAME} /tmp/out.json && cat /tmp/out.json"
)
