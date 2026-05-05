"""Approve the latest model package in the registry."""
import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
MODEL_PACKAGE_GROUP_NAME = "creditcard-fraud-model-group"

sm = boto3.client("sagemaker", region_name=AWS_REGION)

# Get the latest model package version
response = sm.list_model_packages(
    ModelPackageGroupName=MODEL_PACKAGE_GROUP_NAME,
    SortBy="CreationTime",
    SortOrder="Descending",
    MaxResults=10,
)
packages = response["ModelPackageSummaryList"]
if not packages:
    raise RuntimeError("No model packages found.")

latest = packages[0]
print(f"Latest version: v{latest['ModelPackageVersion']}")
print(f"Current approval: {latest['ModelApprovalStatus']}")

if latest["ModelApprovalStatus"] == "Approved":
    print("Already approved.")
else:
    sm.update_model_package(
        ModelPackageArn=latest["ModelPackageArn"],
        ModelApprovalStatus="Approved",
        ApprovalDescription="Approved for serverless deployment with A/B variants (Phase 4)",
    )
    print(f"Approved: {latest['ModelPackageArn']}")
