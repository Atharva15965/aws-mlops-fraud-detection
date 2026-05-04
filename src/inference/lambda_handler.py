"""Lambda handler for the public fraud-detection API.

Request shape (POST /predict):
    {"features": [v1, v2, ..., v28, amount, ...]}
    OR
    {"transaction": {"v1": ..., "v2": ..., ..., "amount": ...}}

Response shape:
    {"fraud_probability": 0.987, "is_fraud": true, "variant": "VariantA"}
"""
import json
import os
import random
import boto3

ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]
ENDPOINT_NAME_B = os.environ.get("ENDPOINT_NAME_B", "")  # optional second endpoint
VARIANT_B_TRAFFIC_PCT = float(os.environ.get("VARIANT_B_TRAFFIC_PCT", "0"))

runtime = boto3.client("sagemaker-runtime")

# Expected feature order — must match training (the SageMaker preprocess script's column order minus 'class')
FEATURE_ORDER = (
    ["time"]
    + [f"v{i}" for i in range(1, 29)]
    + ["amount", "log_amount", "amount_zscore", "is_zero_amount", "hour"]
)


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))

        # Accept either ordered list or named dict
        if "features" in body:
            features = body["features"]
            if len(features) != len(FEATURE_ORDER):
                return _error(
                    400, f"Expected {len(FEATURE_ORDER)} features, got {len(features)}"
                )
        elif "transaction" in body:
            tx = body["transaction"]
            try:
                features = [tx[name] for name in FEATURE_ORDER]
            except KeyError as e:
                return _error(400, f"Missing field: {e}")
        else:
            return _error(400, "Request must contain 'features' or 'transaction'")

        # A/B routing decision
        if ENDPOINT_NAME_B and random.random() * 100 < VARIANT_B_TRAFFIC_PCT:
            target_endpoint = ENDPOINT_NAME_B
            variant = "VariantB"
        else:
            target_endpoint = ENDPOINT_NAME
            variant = "VariantA"

        # Build CSV payload (XGBoost endpoint expects target column ABSENT, comma-separated)
        payload = ",".join(map(str, features))

        # Invoke SageMaker
        response = runtime.invoke_endpoint(
            EndpointName=target_endpoint,
            ContentType="text/csv",
            Body=payload,
        )
        score = float(response["Body"].read().decode("utf-8").strip())

        return _ok(
            {
                "fraud_probability": round(score, 6),
                "is_fraud": score >= 0.5,
                "variant": variant,
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
