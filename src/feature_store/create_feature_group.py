"""Create the SageMaker Feature Group for credit card fraud features (explicit schema)."""
import os
import time
from pathlib import Path

import boto3
from dotenv import load_dotenv
from sagemaker.feature_store.feature_group import FeatureGroup
from sagemaker.feature_store.feature_definition import (
    FeatureDefinition,
    FeatureTypeEnum,
)
from sagemaker.session import Session

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

PROJECT_BUCKET = os.environ["PROJECT_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
SAGEMAKER_ROLE_ARN = os.environ["SAGEMAKER_ROLE_ARN"]
FEATURE_GROUP_NAME = "creditcard-fraud-features"
OFFLINE_STORE_S3_URI = f"s3://{PROJECT_BUCKET}/feature-store/"

boto_session = boto3.Session(region_name=AWS_REGION)
sagemaker_session = Session(boto_session=boto_session)

# ---- Explicit feature definitions ----
# SageMaker supports 3 types: INTEGRAL (int), FRACTIONAL (float), STRING.
INT_FEATURES = ["transaction_id", "is_zero_amount", "hour", "class"]
FLOAT_FEATURES = ["time", "amount", "log_amount", "amount_zscore", "event_time"] + [
    f"v{i}" for i in range(1, 29)
]
STRING_FEATURES = ["time_bucket"]

feature_definitions = (
    [
        FeatureDefinition(feature_name=f, feature_type=FeatureTypeEnum.INTEGRAL)
        for f in INT_FEATURES
    ]
    + [
        FeatureDefinition(feature_name=f, feature_type=FeatureTypeEnum.FRACTIONAL)
        for f in FLOAT_FEATURES
    ]
    + [
        FeatureDefinition(feature_name=f, feature_type=FeatureTypeEnum.STRING)
        for f in STRING_FEATURES
    ]
)


def create_feature_group():
    fg = FeatureGroup(
        name=FEATURE_GROUP_NAME,
        sagemaker_session=sagemaker_session,
        feature_definitions=feature_definitions,
    )

    print(f"Creating feature group '{FEATURE_GROUP_NAME}' (online + offline stores)...")
    fg.create(
        s3_uri=OFFLINE_STORE_S3_URI,
        record_identifier_name="transaction_id",
        event_time_feature_name="event_time",
        role_arn=SAGEMAKER_ROLE_ARN,
        enable_online_store=True,
    )

    print("Waiting for feature group to be ACTIVE (~1-2 min)...")
    while True:
        status = fg.describe().get("FeatureGroupStatus")
        print(f"  Status: {status}")
        if status == "Created":
            break
        if status == "CreateFailed":
            raise RuntimeError(f"Creation failed: {fg.describe().get('FailureReason')}")
        time.sleep(15)
    print("Feature group ACTIVE.")
    return fg


if __name__ == "__main__":
    create_feature_group()
