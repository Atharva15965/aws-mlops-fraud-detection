"""Manually register the locally-trained model in the SageMaker Model Registry."""
import os
import sys
from pathlib import Path

import boto3
from dotenv import load_dotenv
from sagemaker.image_uris import retrieve as retrieve_image_uri

load_dotenv()
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

if len(sys.argv) < 2:
    print("Usage: python src/pipeline/register_local_model.py <MODEL_S3_URI>")
    sys.exit(1)

MODEL_S3_URI = sys.argv[1]
MODEL_PACKAGE_GROUP_NAME = "creditcard-fraud-model-group"
xgb_image = retrieve_image_uri("xgboost", region=AWS_REGION, version="1.7-1")

sm = boto3.client("sagemaker", region_name=AWS_REGION)

# 1. Ensure Model Package Group exists
try:
    sm.create_model_package_group(
        ModelPackageGroupName=MODEL_PACKAGE_GROUP_NAME,
        ModelPackageGroupDescription="Credit card fraud detection model versions",
    )
    print(f"Created Model Package Group: {MODEL_PACKAGE_GROUP_NAME}")
except sm.exceptions.ResourceLimitExceeded:
    raise
except Exception as e:
    if "already exists" in str(e):
        print(f"Model Package Group already exists: {MODEL_PACKAGE_GROUP_NAME}")
    else:
        raise

# 2. Register a new model package
response = sm.create_model_package(
    ModelPackageGroupName=MODEL_PACKAGE_GROUP_NAME,
    ModelPackageDescription="Locally-trained XGBoost model (fallback while SageMaker training quota pending)",
    InferenceSpecification={
        "Containers": [{"Image": xgb_image, "ModelDataUrl": MODEL_S3_URI}],
        "SupportedContentTypes": ["text/csv"],
        "SupportedResponseMIMETypes": ["text/csv"],
        "SupportedRealtimeInferenceInstanceTypes": ["ml.m5.large"],
        "SupportedTransformInstanceTypes": ["ml.m5.large"],
    },
    ModelApprovalStatus="PendingManualApproval",
)
print(f"Registered: {response['ModelPackageArn']}")
