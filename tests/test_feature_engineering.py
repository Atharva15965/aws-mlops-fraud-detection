"""Smoke tests for feature engineering pipeline."""
import sys
from pathlib import Path

import pandas as pd
import pytest

# Make src importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from data.feature_engineering import (
    add_log_amount,
    add_time_features,
    add_zero_amount_flag,
    build_partitioned_key := None,  # placeholder if you don't have it
)


def make_sample_df():
    return pd.DataFrame({
        "time": [0, 3600, 7200, 10800],
        "amount": [100.0, 50.0, 0.0, 200.0],
        "class": [0, 0, 1, 0],
    })


def test_add_log_amount():
    df = make_sample_df()
    out = add_log_amount(df.copy())
    assert "log_amount" in out.columns
    assert (out["log_amount"] >= 0).all()


def test_add_zero_amount_flag():
    df = make_sample_df()
    out = add_zero_amount_flag(df.copy())
    assert out["is_zero_amount"].sum() == 1  # only the 0.0 row


def test_add_time_features():
    df = make_sample_df()
    out = add_time_features(df.copy())
    assert "hour" in out.columns
    assert (out["hour"] >= 0).all()
    assert (out["hour"] <= 23).all()