"""Hit the public API with real samples from the dataset."""
import json
import os
import sys
from pathlib import Path

import boto3
import pandas as pd
import urllib.request
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

if len(sys.argv) < 3:
    print("Usage: python src/inference/test_api.py <API_URL> <API_KEY>")
    sys.exit(1)

API_URL, API_KEY = sys.argv[1], sys.argv[2]
PROJECT_BUCKET = os.environ["PROJECT_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

# Pull samples from the processed Parquet
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
        for c in ["year", "month", "day", "transaction_id", "time_bucket"]
        if c in df.columns
    ]
)
feature_cols = [c for c in df.columns if c != "class"]

# 5 fraud + 5 legit
samples = pd.concat(
    [
        df[df["class"] == 1].sample(5, random_state=2),
        df[df["class"] == 0].sample(5, random_state=2),
    ]
)

print(f"{'true':>5} {'prob':>10} {'pred':>5} {'variant':>10}")
for _, row in samples.iterrows():
    payload = {"features": [float(row[c]) for c in feature_cols]}
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": API_KEY},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    print(
        f"{int(row['class']):>5} {data['fraud_probability']:>10} {data['is_fraud']:>5} {data['variant']:>10}"
    )
