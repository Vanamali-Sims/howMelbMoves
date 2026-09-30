"""Forecast error metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_SEASONALITY = 24


def effective_seasonality(length: int, requested: int = DEFAULT_SEASONALITY) -> int:
    if length <= 1:
        return 0
    return min(requested, length - 1)


def in_sample_mase_scale(
    values: np.ndarray,
    seasonality: int = DEFAULT_SEASONALITY,
) -> float:
    """Mean absolute one-step seasonal difference on an in-sample series."""
    if values.size <= seasonality:
        return float("nan")
    diffs = np.abs(values[seasonality:] - values[:-seasonality])
    if diffs.size == 0:
        return float("nan")
    scale = float(np.mean(diffs))
    if scale == 0.0:
        return float("nan")
    return scale


def mase(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    scale: float,
) -> float:
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if not mask.any() or not np.isfinite(scale) or scale == 0.0:
        return float("nan")
    return float(np.mean(np.abs(y_true[mask] - y_pred[mask])) / scale)


def panel_mase(
    test: pd.DataFrame,
    train: pd.DataFrame,
    *,
    y_col: str,
    pred_col: str,
    series_col: str = "precinct",
    seasonality: int = DEFAULT_SEASONALITY,
) -> float:
    """Pooled MASE on test rows with per-series scale from the training sample."""
    numer = 0.0
    denom = 0.0
    for series, test_group in test.groupby(series_col):
        train_group = train.loc[train[series_col] == series]
        if train_group.empty:
            continue
        ordered = train_group.sort_values(["sensing_date", "hourday"])
        values = ordered[y_col].to_numpy(dtype=float)
        m = effective_seasonality(values.size, seasonality)
        if m == 0:
            continue
        scale = in_sample_mase_scale(values, m)
        y = test_group[y_col].to_numpy(dtype=float)
        p = test_group[pred_col].to_numpy(dtype=float)
        mask = np.isfinite(y) & np.isfinite(p)
        if not mask.any() or not np.isfinite(scale):
            continue
        numer += float(np.sum(np.abs(y[mask] - p[mask])))
        denom += scale * float(mask.sum())
    if denom == 0.0:
        return float("nan")
    return numer / denom
