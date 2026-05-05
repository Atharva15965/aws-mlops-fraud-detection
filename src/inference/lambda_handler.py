"""Lambda handler with built-in data capture (since serverless can't use SageMaker DataCapture)."""
import json
import os
import random
import time
import uuid
from datetime import datetime, timezone

import boto3

ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]
ENDPOINT_NAME_B = os.environ.get("ENDPOINT_NAME_B", "")
VARIANT_B_TRAFFIC_PCT = float(os.environ.get("VARIANT_B_TRAFFIC_PCT", "0"))
DATA_CAPTURE_BUCKET = os.environ["DATA_CAPTURE_BUCKET"]
DATA_CAPTURE_PREFIX = os.environ.get("DATA_CAPTURE_PREFIX", "data-capture/")

runtime = boto3.client("sagemaker-runtime")
s3 = boto3.client("s3")

FEATURE_ORDER = (
    ["time"]
    + [f"v{i}" for i in range(1, 29)]
    + ["amount", "log_amount", "amount_zscore", "is_zero_amount", "hour"]
)


def lambda_handler(event, context):
    capture_id = str(uuid.uuid4())
    try:
        body = json.loads(event.get("body", "{}"))

        if "features" in body:
            features = body["features"]
        elif "transaction" in body:
            features = [body["transaction"][n] for n in FEATURE_ORDER]
        else:
            return _error(400, "Request must contain 'features' or 'transaction'")
        if len(features) != len(FEATURE_ORDER):
            return _error(
                400, f"Expected {len(FEATURE_ORDER)} features, got {len(features)}"
            )

        if ENDPOINT_NAME_B and random.random() * 100 < VARIANT_B_TRAFFIC_PCT:
            target_endpoint, variant = ENDPOINT_NAME_B, "VariantB"
        else:
            target_endpoint, variant = ENDPOINT_NAME, "VariantA"

        payload = ",".join(map(str, features))
        response = runtime.invoke_endpoint(
            EndpointName=target_endpoint,
            ContentType="text/csv",
            Body=payload,
        )
        score = float(response["Body"].read().decode("utf-8").strip())

        # Capture to S3
        ts = time.time()
        d = datetime.fromtimestamp(ts, tz=timezone.utc)
        capture_record = {
            "capture_id": capture_id,
            "timestamp": ts,
            "endpoint": target_endpoint,
            "variant": variant,
            "features": dict(zip(FEATURE_ORDER, features)),
            "score": score,
        }
        key = (
            f"{DATA_CAPTURE_PREFIX}"
            f"year={d.year}/month={d.month:02d}/day={d.day:02d}/hour={d.hour:02d}/"
            f"{capture_id}.json"
        )
        s3.put_object(
            Bucket=DATA_CAPTURE_BUCKET, Key=key, Body=json.dumps(capture_record)
        )

        return _ok(
            {
                "fraud_probability": round(score, 6),
                "is_fraud": score >= 0.5,
                "variant": variant,
                "capture_id": capture_id,
            }
        )

    except Exception as e:
        return _error(500, f"Internal error: {type(e).__name__}: {e}")


def _ok(body):
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _error(status, message):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({"error": message}),
    }
