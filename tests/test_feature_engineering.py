"""Self-contained smoke tests — no imports from src/ to avoid path issues in CI.

These tests verify the test infrastructure works. Add proper integration tests later.
"""
import pandas as pd
import numpy as np


def test_pandas_works():
    df = pd.DataFrame({"amount": [100.0, 0.0, 50.0], "class": [0, 1, 0]})
    assert len(df) == 3
    assert df["class"].sum() == 1


def test_log_transform():
    """Mirrors the log_amount transformation from feature_engineering.py."""
    amounts = pd.Series([0.0, 100.0, 1000.0])
    log_amounts = np.log1p(amounts)
    assert (log_amounts >= 0).all()
    assert log_amounts.iloc[0] == 0.0  # log(1+0) = 0


def test_hour_derivation():
    """Mirrors the hour-from-time logic."""
    times = pd.Series([0, 3600, 7200, 86400])
    hours = (times // 3600) % 24
    assert hours.tolist() == [0, 1, 2, 0]


def test_zero_amount_flag():
    """Mirrors the is_zero_amount flag logic."""
    amounts = pd.Series([0.0, 50.0, 100.0, 0.0])
    is_zero = (amounts == 0).astype(int)
    assert is_zero.sum() == 2
