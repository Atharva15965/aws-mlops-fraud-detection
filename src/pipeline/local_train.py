"""Local fallback: train + evaluate XGBoost end-to-end on this machine.
Saves a SageMaker-compatible model.tar.gz and an evaluation.json to S3.
"""
import json
import os
import tarfile
import time
from pathlib import Path

import boto3
import pandas as pd
import xgboost as xgb
from dotenv import load_dotenv
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

load_dotenv()
PROJECT_BUCKET = os.environ["PROJECT_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

# 1. Load latest processed Parquet from S3
s3 = boto3.client("s3", region_name=AWS_REGION)
keys = []
for page in s3.get_paginator("list_objects_v2").paginate(
    Bucket=PROJECT_BUCKET, Prefix="processed/creditcard/"
):
    for obj in page.get("Contents", []):
        if obj["Key"].endswith(".parquet"):
            keys.append(obj["Key"])
latest = sorted(keys)[-1]
print(f"Reading s3://{PROJECT_BUCKET}/{latest}")
df = pd.read_parquet(f"s3://{PROJECT_BUCKET}/{latest}")
df = df.drop(
    columns=[
        c
        for c in ["year", "month", "day", "transaction_id", "time_bucket"]
        if c in df.columns
    ]
)
print(f"Loaded {len(df):,} rows × {df.shape[1]} cols")

# 2. Stratified split (same as the pipeline preprocess step)
feature_cols = [c for c in df.columns if c != "class"]
X = df[feature_cols].values
y = df["class"].values
X_train, X_temp, y_train, y_temp = train_test_split(
    X, y, test_size=0.3, stratify=y, random_state=42
)
X_val, X_test, y_val, y_test = train_test_split(
    X_temp, y_temp, test_size=0.5, stratify=y_temp, random_state=42
)
print(f"Train {len(X_train):,} | Val {len(X_val):,} | Test {len(X_test):,}")

# 3. Train XGBoost (same hyperparameters as the pipeline)
params = {
    "objective": "binary:logistic",
    "eval_metric": "aucpr",
    "max_depth": 6,
    "eta": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "scale_pos_weight": 577,
}
dtrain = xgb.DMatrix(X_train, label=y_train)
dval = xgb.DMatrix(X_val, label=y_val)
dtest = xgb.DMatrix(X_test, label=y_test)
print("Training...")
booster = xgb.train(
    params, dtrain, num_boost_round=200, evals=[(dval, "val")], verbose_eval=50
)

# 4. Evaluate
y_proba = booster.predict(dtest)
y_pred = (y_proba >= 0.5).astype(int)
metrics = {
    "metrics": {
        "pr_auc": {"value": float(average_precision_score(y_test, y_proba))},
        "roc_auc": {"value": float(roc_auc_score(y_test, y_proba))},
        "f1": {"value": float(f1_score(y_test, y_pred))},
        "precision": {"value": float(precision_score(y_test, y_pred, zero_division=0))},
        "recall": {"value": float(recall_score(y_test, y_pred))},
    },
    "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
}
print("\nMetrics on test set:")
print(json.dumps(metrics, indent=2))

# 5. Save in SageMaker-compatible format and upload
out_dir = Path("data/local-model")
out_dir.mkdir(parents=True, exist_ok=True)
booster.save_model(str(out_dir / "xgboost-model"))

tar_path = out_dir / "model.tar.gz"
with tarfile.open(tar_path, "w:gz") as tar:
    tar.add(out_dir / "xgboost-model", arcname="xgboost-model")
print(f"Packaged: {tar_path}")

ts = int(time.time())
s3_model_key = f"local-models/creditcard-{ts}/model.tar.gz"
s3_eval_key = f"local-models/creditcard-{ts}/evaluation.json"

s3.upload_file(str(tar_path), PROJECT_BUCKET, s3_model_key)
(out_dir / "evaluation.json").write_text(json.dumps(metrics, indent=2))
s3.upload_file(str(out_dir / "evaluation.json"), PROJECT_BUCKET, s3_eval_key)

print(f"\nUploaded model:   s3://{PROJECT_BUCKET}/{s3_model_key}")
print(f"Uploaded metrics: s3://{PROJECT_BUCKET}/{s3_eval_key}")
print(
    f"\nFor next step (manual register):  MODEL_S3_URI=s3://{PROJECT_BUCKET}/{s3_model_key}"
)
