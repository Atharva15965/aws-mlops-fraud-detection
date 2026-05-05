"""Send a few sample transactions to the endpoint and observe variant routing."""
import json
import os
from collections import Counter
from pathlib import Path

import boto3
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

PROJECT_BUCKET = os.environ["PROJECT_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
ENDPOINT_NAME = "creditcard-fraud-endpoint"

# 1. Get a few sample rows from the processed Parquet
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

# Pick 10 samples — 5 fraud, 5 legit
fraud_samples = df[df["class"] == 1].sample(5, random_state=1)
legit_samples = df[df["class"] == 0].sample(5, random_state=1)
samples = pd.concat([fraud_samples, legit_samples]).reset_index(drop=True)

# 2. Build CSV payloads (XGBoost endpoint expects: target column dropped, comma-separated)
feature_cols = [c for c in df.columns if c != "class"]
X = samples[feature_cols]
y_true = samples["class"].values

# 3. Invoke endpoint
runtime = boto3.client("sagemaker-runtime", region_name=AWS_REGION)
print(f"Sending {len(X)} requests to {ENDPOINT_NAME}...\n")

variant_counter = Counter()
results = []
for i in range(len(X)):
    payload = ",".join(map(str, X.iloc[i].values))
    response = runtime.invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType="text/csv",
        Body=payload,
    )
    body = response["Body"].read().decode("utf-8").strip()
    score = float(body)
    pred = 1 if score >= 0.5 else 0
    served_by = response.get("InvokedProductionVariant", "?")
    variant_counter[served_by] += 1
    results.append(
        {
            "sample": i,
            "true_class": int(y_true[i]),
            "score": round(score, 4),
            "pred_class": pred,
            "variant": served_by,
        }
    )

# 4. Print a results table
print(f"{'sample':>6} {'true':>5} {'score':>7} {'pred':>5} {'variant':>10}")
for r in results:
    print(
        f"{r['sample']:>6} {r['true_class']:>5} {r['score']:>7} {r['pred_class']:>5} {r['variant']:>10}"
    )

# 5. Variant traffic distribution
print("\nVariant routing distribution:")
total = sum(variant_counter.values())
for variant, count in variant_counter.items():
    pct = 100 * count / total
    print(f"  {variant}: {count}/{total} ({pct:.0f}%)")
