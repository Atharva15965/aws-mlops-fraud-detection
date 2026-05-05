"""Drift detection Lambda: read recent captures, compare means to baseline, publish CloudWatch metric."""
import json
import os
import statistics
from datetime import datetime, timedelta, timezone

import boto3

PROJECT_BUCKET = os.environ["PROJECT_BUCKET"]
LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "1"))
DRIFT_THRESHOLD_STD = float(os.environ.get("DRIFT_THRESHOLD_STD", "2.0"))

s3 = boto3.client("s3")
cloudwatch = boto3.client("cloudwatch")


def lambda_handler(event, context):
    # Load baseline
    baseline_obj = s3.get_object(
        Bucket=PROJECT_BUCKET, Key="monitoring/baseline-simple.json"
    )
    baseline = json.loads(baseline_obj["Body"].read())

    # List recent capture files
    now = datetime.now(timezone.utc)
    captures = []
    for h in range(LOOKBACK_HOURS):
        d = now - timedelta(hours=h)
        prefix = f"data-capture/year={d.year}/month={d.month:02d}/day={d.day:02d}/hour={d.hour:02d}/"
        for page in s3.get_paginator("list_objects_v2").paginate(
            Bucket=PROJECT_BUCKET, Prefix=prefix
        ):
            for obj in page.get("Contents", []):
                rec = json.loads(
                    s3.get_object(Bucket=PROJECT_BUCKET, Key=obj["Key"])["Body"].read()
                )
                captures.append(rec["features"])

    if not captures:
        print("No captures in lookback window.")
        return {"statusCode": 200, "drift_detected": False, "reason": "no data"}

    print(f"Analyzing {len(captures)} captured records")

    # Compute drift score per feature: |observed_mean - baseline_mean| / baseline_std
    drift_scores = {}
    for feat, stats_baseline in baseline.items():
        values = [c.get(feat) for c in captures if c.get(feat) is not None]
        if len(values) < 2:
            continue
        observed_mean = statistics.mean(values)
        if stats_baseline["std"] > 0:
            score = abs(observed_mean - stats_baseline["mean"]) / stats_baseline["std"]
        else:
            score = 0.0
        drift_scores[feat] = round(score, 4)

    max_drift = max(drift_scores.values())
    max_feature = max(drift_scores, key=drift_scores.get)
    drift_detected = max_drift > DRIFT_THRESHOLD_STD

    print(f"Max drift: {max_feature}={max_drift} (threshold={DRIFT_THRESHOLD_STD})")
    print(f"All drift scores: {drift_scores}")

    # Publish CloudWatch metric so we can build alarms on it
    cloudwatch.put_metric_data(
        Namespace="CreditcardFraudMonitor",
        MetricData=[
            {"MetricName": "MaxFeatureDrift", "Value": max_drift, "Unit": "None"},
            {"MetricName": "RecordsAnalyzed", "Value": len(captures), "Unit": "Count"},
        ],
    )

    return {
        "statusCode": 200,
        "drift_detected": drift_detected,
        "max_drift": max_drift,
        "max_feature": max_feature,
        "drift_scores": drift_scores,
        "records_analyzed": len(captures),
    }
