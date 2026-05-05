"""Deploy the approved model as a single-variant serverless endpoint.

Serverless Inference supports only ONE production variant per endpoint.
For A/B testing, we'll deploy a second serverless endpoint when v2 is available
and route 90/10 traffic at the Lambda layer in Phase 5.
"""
import os
import time
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
SAGEMAKER_ROLE_ARN = os.environ["SAGEMAKER_ROLE_ARN"]

MODEL_PACKAGE_GROUP_NAME = "creditcard-fraud-model-group"
ENDPOINT_CONFIG_NAME = "creditcard-fraud-endpoint-config"
ENDPOINT_NAME = "creditcard-fraud-endpoint"
MODEL_NAME = "creditcard-fraud-model-a"

sm = boto3.client("sagemaker", region_name=AWS_REGION)

# 1. Find the latest APPROVED model package
response = sm.list_model_packages(
    ModelPackageGroupName=MODEL_PACKAGE_GROUP_NAME,
    ModelApprovalStatus="Approved",
    SortBy="CreationTime",
    SortOrder="Descending",
    MaxResults=1,
)
if not response["ModelPackageSummaryList"]:
    raise RuntimeError("No approved model packages found. Run approve_model.py first.")
latest_package = response["ModelPackageSummaryList"][0]
package_arn = latest_package["ModelPackageArn"]
print(f"Using model package: v{latest_package['ModelPackageVersion']}")


# 2. Create a SageMaker Model from the package
def create_model_from_package(model_name: str, package_arn: str) -> str:
    try:
        sm.delete_model(ModelName=model_name)
    except sm.exceptions.ClientError:
        pass
    sm.create_model(
        ModelName=model_name,
        ExecutionRoleArn=SAGEMAKER_ROLE_ARN,
        Containers=[{"ModelPackageName": package_arn}],
    )
    return model_name


model_a = create_model_from_package(MODEL_NAME, package_arn)
print(f"Created model: {model_a}")

# 3. Create an Endpoint Configuration with a single serverless variant
try:
    sm.delete_endpoint_config(EndpointConfigName=ENDPOINT_CONFIG_NAME)
except sm.exceptions.ClientError:
    pass

sm.create_endpoint_config(
    EndpointConfigName=ENDPOINT_CONFIG_NAME,
    ProductionVariants=[
        {
            "VariantName": "VariantA",
            "ModelName": model_a,
            "ServerlessConfig": {"MemorySizeInMB": 2048, "MaxConcurrency": 5},
        },
    ],
)
print(f"Created endpoint config: {ENDPOINT_CONFIG_NAME}")

# 4. Create or update the endpoint
try:
    sm.describe_endpoint(EndpointName=ENDPOINT_NAME)
    print("Endpoint exists, updating...")
    sm.update_endpoint(
        EndpointName=ENDPOINT_NAME, EndpointConfigName=ENDPOINT_CONFIG_NAME
    )
except sm.exceptions.ClientError:
    print("Creating new endpoint...")
    sm.create_endpoint(
        EndpointName=ENDPOINT_NAME, EndpointConfigName=ENDPOINT_CONFIG_NAME
    )

# 5. Wait for InService
print(
    "Waiting for endpoint to be InService (~5-8 minutes for serverless first deploy)..."
)
while True:
    desc = sm.describe_endpoint(EndpointName=ENDPOINT_NAME)
    status = desc["EndpointStatus"]
    print(f"  Status: {status}")
    if status == "InService":
        break
    if status == "Failed":
        raise RuntimeError(f"Endpoint failed: {desc.get('FailureReason')}")
    time.sleep(20)

print(f"Endpoint InService: {ENDPOINT_NAME}")
