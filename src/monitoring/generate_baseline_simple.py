"""Compute mean + stddev for each feature from training data; save as baseline JSON."""
import json
import os
from pathlib import Path

import boto3
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
PROJECT_BUCKET = os.environ["PROJECT_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

s3 = boto3.client("s3", region_name=AWS_REGION)
keys = []
for page in s3.get_paginator("list_objects_v2").paginate(
    Bucket=PROJECT_BUCKET, Prefix="processed/creditcard/"
):
    for obj in page.get("Contents", []):
        if obj["Key"].endswith(".parquet"):
            keys.append(obj["Key"])
df = pd.read_parquet(f"s3://{PROJECT_BUCKET}/{sorted(keys)[-1]}")
df = df.drop(
    columns=[
        c
        for c in ["year", "month", "day", "transaction_id", "time_bucket", "class"]
        if c in df.columns
    ]
)

baseline = {
    col: {"mean": float(df[col].mean()), "std": float(df[col].std())}
    for col in df.columns
}
baseline_uri = f"s3://{PROJECT_BUCKET}/monitoring/baseline-simple.json"
s3.put_object(
    Bucket=PROJECT_BUCKET,
    Key="monitoring/baseline-simple.json",
    Body=json.dumps(baseline, indent=2),
)
print(f"Baseline saved to {baseline_uri}")
print(json.dumps(baseline, indent=2)[:500] + "...")
