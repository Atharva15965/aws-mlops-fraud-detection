"""SageMaker Processing step: load model + test set, compute metrics, write JSON.

Inputs:  /opt/ml/processing/model/model.tar.gz
         /opt/ml/processing/test/test.csv
Outputs: /opt/ml/processing/evaluation/evaluation.json
"""
import json
import os
import pickle
import tarfile
from pathlib import Path

import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
    f1_score,
    precision_score,
    recall_score,
    confusion_matrix,
)

MODEL_DIR = Path("/opt/ml/processing/model")
TEST_DIR = Path("/opt/ml/processing/test")
OUTPUT_DIR = Path("/opt/ml/processing/evaluation")


def load_model():
    """Extract model.tar.gz and load the XGBoost model inside."""
    tar_path = MODEL_DIR / "model.tar.gz"
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(MODEL_DIR)
    # SageMaker XGBoost saves as 'xgboost-model'
    model_files = (
        list(MODEL_DIR.rglob("xgboost-model"))
        + list(MODEL_DIR.rglob("*.bst"))
        + list(MODEL_DIR.rglob("*.json"))
    )
    if not model_files:
        raise FileNotFoundError(
            f"No model file in {MODEL_DIR}: {list(MODEL_DIR.iterdir())}"
        )
    booster = xgb.Booster()
    booster.load_model(str(model_files[0]))
    return booster


def main():
    print("Loading model...")
    booster = load_model()

    print("Loading test set...")
    test_df = pd.read_csv(TEST_DIR / "test.csv", header=None)
    y_true = test_df.iloc[:, 0].values
    X = test_df.iloc[:, 1:].values
    print(f"Test set: {len(y_true):,} rows ({y_true.mean():.4%} fraud)")

    print("Predicting...")
    dtest = xgb.DMatrix(X)
    y_proba = booster.predict(dtest)
    y_pred = (y_proba >= 0.5).astype(int)

    pr_auc = float(average_precision_score(y_true, y_proba))
    roc_auc = float(roc_auc_score(y_true, y_proba))
    f1 = float(f1_score(y_true, y_pred))
    precision = float(precision_score(y_true, y_pred, zero_division=0))
    recall = float(recall_score(y_true, y_pred))
    cm = confusion_matrix(y_true, y_pred).tolist()

    metrics = {
        "metrics": {
            "pr_auc": {"value": pr_auc},
            "roc_auc": {"value": roc_auc},
            "f1": {"value": f1},
            "precision": {"value": precision},
            "recall": {"value": recall},
        },
        "confusion_matrix": cm,
    }

    print(json.dumps(metrics, indent=2))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "evaluation.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Wrote {OUTPUT_DIR / 'evaluation.json'}")


if __name__ == "__main__":
    main()
