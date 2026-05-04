"""Ingest a stratified 10K sample into Feature Store using direct boto3 put_record.

This bypasses the SageMaker SDK's fg.ingest() method, which is unreliable on
recent macOS + pandas 3.x combinations. Direct boto3 calls are slower per-record
but much more stable, with clearer error messages.
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

PROJECT_BUCKET = os.environ["PROJECT_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
FEATURE_GROUP_NAME = "creditcard-fraud-features"
SAMPLE_SIZE = 10_000
MAX_PARALLEL = 8  # number of concurrent put_record calls

# 1. Find latest Parquet file under processed/creditcard/
s3 = boto3.client("s3", region_name=AWS_REGION)
prefix = "processed/creditcard/"
print(f"Listing s3://{PROJECT_BUCKET}/{prefix} ...")
paginator = s3.get_paginator("list_objects_v2")
parquet_keys = []
for page in paginator.paginate(Bucket=PROJECT_BUCKET, Prefix=prefix):
    for obj in page.get("Contents", []):
        if obj["Key"].endswith(".parquet"):
            parquet_keys.append(obj["Key"])

if not parquet_keys:
    raise FileNotFoundError(
        f"No .parquet files found under s3://{PROJECT_BUCKET}/{prefix}"
    )

latest_key = sorted(parquet_keys)[-1]
parquet_uri = f"s3://{PROJECT_BUCKET}/{latest_key}"
print(f"Reading {parquet_uri} ...")
df = pd.read_parquet(parquet_uri)
print(f"Loaded {len(df):,} rows")
# Drop Hive partition columns (year/month/day) — they're path metadata, not features
df = df.drop(columns=[c for c in ["year", "month", "day"] if c in df.columns])
print(f"Columns: {list(df.columns)}")


# 2. Stratified sample
fraud = df[df["class"] == 1]
legit_n = SAMPLE_SIZE - len(fraud)
legit = df[df["class"] == 0].sample(legit_n, random_state=42)
sample = (
    pd.concat([fraud, legit]).sample(frac=1, random_state=42).reset_index(drop=True)
)
print(
    f"Sample: {len(sample):,} rows ({sample['class'].sum()} fraud + {len(sample) - sample['class'].sum()} legit)"
)

# 3. Add event_time
sample["event_time"] = float(time.time())

# 4. Type casts (everything will be sent as string in the PutRecord API anyway,
#    but we want consistent types in the DataFrame for safety)
sample["transaction_id"] = sample["transaction_id"].astype("int64")
sample["is_zero_amount"] = sample["is_zero_amount"].astype("int64")
sample["hour"] = sample["hour"].astype("int64")
sample["class"] = sample["class"].astype("int64")
sample["time_bucket"] = sample["time_bucket"].astype("string")


# 5. Convert each row to the Feature Store record format
def row_to_record(row: pd.Series) -> list:
    record = []
    for col, value in row.items():
        if pd.isna(value):
            continue
        record.append({"FeatureName": col, "ValueAsString": str(value)})
    return record


records = [row_to_record(row) for _, row in sample.iterrows()]
print(f"Built {len(records):,} records")

# 6. Ingest via direct boto3 put_record in a thread pool
fs_client = boto3.client("sagemaker-featurestore-runtime", region_name=AWS_REGION)


def put_one(record):
    try:
        fs_client.put_record(FeatureGroupName=FEATURE_GROUP_NAME, Record=record)
        return None
    except Exception as e:
        return str(e)


print(f"Ingesting with {MAX_PARALLEL} parallel workers...")
start = time.time()
errors = []
completed = 0
with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
    futures = [executor.submit(put_one, r) for r in records]
    for fut in as_completed(futures):
        completed += 1
        err = fut.result()
        if err:
            errors.append(err)
        if completed % 1000 == 0 or completed == len(records):
            elapsed = time.time() - start
            print(f"  {completed:,}/{len(records):,} ingested ({elapsed:.0f}s elapsed)")

elapsed = time.time() - start
print(f"\nIngest complete in {elapsed:.0f}s")
print(f"Successful: {len(records) - len(errors):,}")
print(f"Failed:     {len(errors):,}")
if errors:
    print("Sample errors:")
    for e in errors[:5]:
        print(f"  {e}")
