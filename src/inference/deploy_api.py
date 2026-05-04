"""Deploy Lambda + API Gateway in front of the SageMaker endpoint."""
import json
import os
import time
import zipfile
from io import BytesIO
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
ACCOUNT_ID = boto3.client("sts").get_caller_identity()["Account"]

ENDPOINT_NAME = "creditcard-fraud-endpoint"
LAMBDA_ROLE_NAME = "MLOpsFraudLambdaRole"
LAMBDA_NAME = "creditcard-fraud-predict"
API_NAME = "creditcard-fraud-api"
USAGE_PLAN_NAME = "creditcard-fraud-usage-plan"
API_KEY_NAME = "creditcard-fraud-api-key"
STAGE_NAME = "prod"

iam = boto3.client("iam")
lam = boto3.client("lambda", region_name=AWS_REGION)
apigw = boto3.client("apigateway", region_name=AWS_REGION)


# --- 1. Create / get Lambda IAM role ---------------------------------
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
INVOKE_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {"Effect": "Allow", "Action": "sagemaker:InvokeEndpoint", "Resource": "*"},
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
        RoleName=LAMBDA_ROLE_NAME, AssumeRolePolicyDocument=json.dumps(TRUST)
    )
    print(f"Created IAM role: {LAMBDA_ROLE_NAME}")
    iam.put_role_policy(
        RoleName=LAMBDA_ROLE_NAME,
        PolicyName="InvokeSagemaker",
        PolicyDocument=json.dumps(INVOKE_POLICY),
    )
    time.sleep(10)  # wait for IAM eventual consistency
except iam.exceptions.EntityAlreadyExistsException:
    role = iam.get_role(RoleName=LAMBDA_ROLE_NAME)
    print(f"IAM role exists: {LAMBDA_ROLE_NAME}")
LAMBDA_ROLE_ARN = role["Role"]["Arn"]


# --- 2. Package Lambda code into a zip --------------------------------
handler_path = Path(__file__).parent / "lambda_handler.py"
buf = BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(handler_path, arcname="lambda_handler.py")
buf.seek(0)
zip_bytes = buf.read()
print(f"Packaged Lambda zip: {len(zip_bytes)} bytes")


# --- 3. Create or update Lambda function ------------------------------
env_vars = {
    "ENDPOINT_NAME": ENDPOINT_NAME,
    "ENDPOINT_NAME_B": "",
    "VARIANT_B_TRAFFIC_PCT": "0",
}
try:
    lam.create_function(
        FunctionName=LAMBDA_NAME,
        Runtime="python3.11",
        Role=LAMBDA_ROLE_ARN,
        Handler="lambda_handler.lambda_handler",
        Code={"ZipFile": zip_bytes},
        Timeout=30,
        MemorySize=512,
        Environment={"Variables": env_vars},
    )
    print(f"Created Lambda: {LAMBDA_NAME}")
except lam.exceptions.ResourceConflictException:
    lam.update_function_code(FunctionName=LAMBDA_NAME, ZipFile=zip_bytes)
    lam.update_function_configuration(
        FunctionName=LAMBDA_NAME, Environment={"Variables": env_vars}
    )
    print(f"Updated Lambda: {LAMBDA_NAME}")

# Wait until Lambda is Active
while True:
    cfg = lam.get_function_configuration(FunctionName=LAMBDA_NAME)
    if cfg["State"] == "Active" and cfg.get("LastUpdateStatus") in ("Successful", None):
        break
    print(f"  Lambda state: {cfg['State']}/{cfg.get('LastUpdateStatus')}")
    time.sleep(3)
LAMBDA_ARN = cfg["FunctionArn"]


# --- 4. Create or get API Gateway REST API ----------------------------
apis = apigw.get_rest_apis()["items"]
api = next((a for a in apis if a["name"] == API_NAME), None)
if api is None:
    api = apigw.create_rest_api(name=API_NAME, description="Public fraud detection API")
    print(f"Created API: {API_NAME}")
else:
    print(f"API exists: {API_NAME}")
API_ID = api["id"]

# Get root resource
resources = apigw.get_resources(restApiId=API_ID)["items"]
root_id = next(r["id"] for r in resources if r["path"] == "/")

# Create /predict resource if missing
predict_resource = next((r for r in resources if r["path"] == "/predict"), None)
if predict_resource is None:
    predict_resource = apigw.create_resource(
        restApiId=API_ID, parentId=root_id, pathPart="predict"
    )
    print("Created /predict resource")
PREDICT_ID = predict_resource["id"]

# POST method on /predict (with API key required)
try:
    apigw.put_method(
        restApiId=API_ID,
        resourceId=PREDICT_ID,
        httpMethod="POST",
        authorizationType="NONE",
        apiKeyRequired=True,
    )
    print("Created POST /predict")
except apigw.exceptions.ConflictException:
    print("POST /predict already exists")

# Lambda integration
integration_uri = f"arn:aws:apigateway:{AWS_REGION}:lambda:path/2015-03-31/functions/{LAMBDA_ARN}/invocations"
apigw.put_integration(
    restApiId=API_ID,
    resourceId=PREDICT_ID,
    httpMethod="POST",
    type="AWS_PROXY",
    integrationHttpMethod="POST",
    uri=integration_uri,
)

# Allow API Gateway to invoke Lambda
try:
    lam.add_permission(
        FunctionName=LAMBDA_NAME,
        StatementId="AllowApiGateway",
        Action="lambda:InvokeFunction",
        Principal="apigateway.amazonaws.com",
        SourceArn=f"arn:aws:execute-api:{AWS_REGION}:{ACCOUNT_ID}:{API_ID}/*/POST/predict",
    )
except lam.exceptions.ResourceConflictException:
    pass


# --- 5. Deploy the API to a stage -------------------------------------
apigw.create_deployment(restApiId=API_ID, stageName=STAGE_NAME)
print(f"Deployed to stage: {STAGE_NAME}")


# --- 6. Create API Key + Usage Plan -----------------------------------
keys = apigw.get_api_keys(includeValues=True)["items"]
api_key = next((k for k in keys if k["name"] == API_KEY_NAME), None)
if api_key is None:
    api_key = apigw.create_api_key(
        name=API_KEY_NAME, enabled=True, generateDistinctId=True
    )
    print(f"Created API key: {API_KEY_NAME}")
else:
    print(f"API key exists: {API_KEY_NAME}")
API_KEY_VALUE = api_key["value"]
API_KEY_ID = api_key["id"]

plans = apigw.get_usage_plans()["items"]
plan = next((p for p in plans if p["name"] == USAGE_PLAN_NAME), None)
if plan is None:
    plan = apigw.create_usage_plan(
        name=USAGE_PLAN_NAME,
        apiStages=[{"apiId": API_ID, "stage": STAGE_NAME}],
        throttle={"rateLimit": 10, "burstLimit": 20},
        quota={"limit": 10000, "period": "DAY"},
    )
    print(f"Created usage plan: {USAGE_PLAN_NAME}")
PLAN_ID = plan["id"]

try:
    apigw.create_usage_plan_key(
        usagePlanId=PLAN_ID, keyId=API_KEY_ID, keyType="API_KEY"
    )
except apigw.exceptions.ConflictException:
    pass


# --- 7. Print the public URL and API key ------------------------------
URL = f"https://{API_ID}.execute-api.{AWS_REGION}.amazonaws.com/{STAGE_NAME}/predict"
print("\n" + "=" * 70)
print(f"PUBLIC API URL:  {URL}")
print(f"API KEY:         {API_KEY_VALUE}")
print("=" * 70)
print("\nTest with curl:")
print(
    f"""
curl -X POST '{URL}' \\
  -H 'x-api-key: {API_KEY_VALUE}' \\
  -H 'Content-Type: application/json' \\
  -d '{{"features": [0.0, -1.36, -0.07, 2.54, 1.38, -0.34, 0.46, 0.24, 0.10, 0.36, 0.09, -0.55, -0.62, -0.99, -0.31, 1.47, -0.47, 0.21, 0.03, 0.40, 0.25, -0.02, 0.28, -0.11, 0.07, 0.13, -0.19, 0.13, -0.02, 149.62, 5.01, 0.24, 0, 0]}}'
"""
)
