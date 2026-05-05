"""Update predict Lambda's IAM permissions and redeploy with capture env vars."""
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

LAMBDA_NAME = "creditcard-fraud-predict"
ROLE_NAME = "MLOpsFraudLambdaRole"

iam = boto3.client("iam")
lam = boto3.client("lambda", region_name=AWS_REGION)

# 1. Add S3 write permission to the existing role
S3_WRITE_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "s3:PutObject",
            "Resource": f"arn:aws:s3:::{PROJECT_BUCKET}/data-capture/*",
        }
    ],
}
iam.put_role_policy(
    RoleName=ROLE_NAME,
    PolicyName="S3DataCaptureWrite",
    PolicyDocument=json.dumps(S3_WRITE_POLICY),
)
print("Added S3 write permission to Lambda role")
time.sleep(5)

# 2. Re-package and update Lambda code + env vars
handler_path = Path(__file__).resolve().parents[1] / "inference" / "lambda_handler.py"
buf = BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(handler_path, arcname="lambda_handler.py")
buf.seek(0)
zip_bytes = buf.read()

lam.update_function_code(FunctionName=LAMBDA_NAME, ZipFile=zip_bytes)
print("Updated Lambda code")

# Wait for code update to settle before changing config
time.sleep(5)
while True:
    cfg = lam.get_function_configuration(FunctionName=LAMBDA_NAME)
    if cfg.get("LastUpdateStatus") == "Successful":
        break
    time.sleep(2)

lam.update_function_configuration(
    FunctionName=LAMBDA_NAME,
    Environment={
        "Variables": {
            "ENDPOINT_NAME": "creditcard-fraud-endpoint",
            "ENDPOINT_NAME_B": "",
            "VARIANT_B_TRAFFIC_PCT": "0",
            "DATA_CAPTURE_BUCKET": PROJECT_BUCKET,
            "DATA_CAPTURE_PREFIX": "data-capture/",
        }
    },
)
print("Updated Lambda env vars (data capture enabled)")
