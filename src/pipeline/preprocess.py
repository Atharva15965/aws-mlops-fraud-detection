"""SageMaker Processing step: read processed Parquet, stratified split, write CSVs.

Runs inside a SKLearn container on SageMaker Processing.
Inputs:  /opt/ml/processing/input/  (S3 Parquet mounted by SageMaker)
Outputs: /opt/ml/processing/train/train.csv
         /opt/ml/processing/validation/validation.csv
         /opt/ml/processing/test/test.csv
"""
import argparse
import os
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

INPUT_DIR = Path("/opt/ml/processing/input")
TRAIN_OUT = Path("/opt/ml/processing/train")
VAL_OUT = Path("/opt/ml/processing/validation")
TEST_OUT = Path("/opt/ml/processing/test")

# Columns to drop before training. transaction_id is just an ID.
# time_bucket is categorical and we already encoded its info in `hour`.
DROP_COLS = ["transaction_id", "time_bucket", "year", "month", "day"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-frac", type=float, default=0.7)
    parser.add_argument("--val-frac", type=float, default=0.15)
    args = parser.parse_args()

    print("Reading Parquet inputs from", INPUT_DIR)
    parquet_files = list(INPUT_DIR.rglob("*.parquet"))
    print(f"Found {len(parquet_files)} parquet file(s)")
    df = pd.concat([pd.read_parquet(p) for p in parquet_files], ignore_index=True)
    print(f"Loaded {len(df):,} rows × {df.shape[1]} cols")

    # Drop columns we don't want as features
    drop = [c for c in DROP_COLS if c in df.columns]
    df = df.drop(columns=drop)
    print(f"Dropped: {drop}")

    # XGBoost CSV format: target column FIRST, no header, no index
    feature_cols = [c for c in df.columns if c != "class"]
    df = df[["class"] + feature_cols]
    print(f"Final columns (target first): {list(df.columns)}")

    # Stratified split: train / val / test
    test_frac = 1 - args.train_frac - args.val_frac
    train_df, temp_df = train_test_split(
        df, test_size=(1 - args.train_frac), stratify=df["class"], random_state=42
    )
    val_relative = args.val_frac / (args.val_frac + test_frac)
    val_df, test_df = train_test_split(
        temp_df, train_size=val_relative, stratify=temp_df["class"], random_state=42
    )

    print(f"Train: {len(train_df):,} ({train_df['class'].mean():.4%} fraud)")
    print(f"Val:   {len(val_df):,} ({val_df['class'].mean():.4%} fraud)")
    print(f"Test:  {len(test_df):,} ({test_df['class'].mean():.4%} fraud)")

    TRAIN_OUT.mkdir(parents=True, exist_ok=True)
    VAL_OUT.mkdir(parents=True, exist_ok=True)
    TEST_OUT.mkdir(parents=True, exist_ok=True)

    train_df.to_csv(TRAIN_OUT / "train.csv", header=False, index=False)
    val_df.to_csv(VAL_OUT / "validation.csv", header=False, index=False)
    test_df.to_csv(TEST_OUT / "test.csv", header=False, index=False)
    print("Wrote train/val/test CSVs.")


if __name__ == "__main__":
    main()
