"""Rolling-origin evaluation with MASE."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from melbourne_footfall.features.build import SEASONALITY_HOURS
from melbourne_footfall.models.metrics import panel_mase
from melbourne_footfall.models.train import (
    CATEGORICAL_FEATURES,
    _coerce_flags,
    feature_columns,
    load_feature_matrix,
)
from melbourne_footfall.paths import metrics_path

logger = logging.getLogger("melbourne_footfall.models.evaluate")


def _json_safe(value: object) -> object:
    if isinstance(value, (float, np.floating)) and np.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _as_dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.date


def rolling_origins(dates: pd.Series) -> list[date]:
    unique = sorted(_as_dates(dates).unique())
    if len(unique) < 2:
        return []
    return list(unique[1:])


def _fit_fold(train: pd.DataFrame) -> tuple[lgb.LGBMRegressor | None, list[str]]:
    features = feature_columns(train)
    rows = train.dropna(subset=features + ["pedestriancount"])
    if len(rows) < 10:
        return None, features
    work = rows.copy()
    work["precinct"] = work["precinct"].astype("category")
    model = lgb.LGBMRegressor(
        n_estimators=64,
        max_depth=6,
        learning_rate=0.1,
        random_state=42,
        verbosity=-1,
    )
    model.fit(
        work[features],
        work["pedestriancount"],
        categorical_feature=CATEGORICAL_FEATURES,
    )
    return model, features


def evaluate_rolling_origin(
    frame: pd.DataFrame | None = None,
    *,
    features_file: Path | None = None,
    dest: Path | None = None,
) -> dict[str, object]:
    if frame is not None:
        data = _coerce_flags(frame)
    else:
        data = _coerce_flags(load_feature_matrix(features_file))
    data["sensing_date"] = _as_dates(data["sensing_date"])
    data["baseline_pred"] = data["lag_24h"]

    folds: list[dict[str, object]] = []
    all_test = []

    for origin in rolling_origins(data["sensing_date"]):
        train = data.loc[data["sensing_date"] < origin].copy()
        test = data.loc[data["sensing_date"] == origin].copy()
        if test.empty or train.empty:
            continue
        test["baseline_pred"] = test["lag_24h"]
        test["lgbm_pred"] = np.nan
        model, features = _fit_fold(train)
        if model is not None:
            predict_rows = test.dropna(subset=features)
            if not predict_rows.empty:
                work = predict_rows.copy()
                categories = train["precinct"].astype("category").cat.categories
                work["precinct"] = pd.Categorical(
                    work["precinct"],
                    categories=categories,
                )
                test.loc[work.index, "lgbm_pred"] = model.predict(work[features])

        baseline_mase = panel_mase(
            test.dropna(subset=["baseline_pred"]),
            train,
            y_col="pedestriancount",
            pred_col="baseline_pred",
            seasonality=SEASONALITY_HOURS,
        )
        lgbm_mase = panel_mase(
            test.dropna(subset=["lgbm_pred"]),
            train,
            y_col="pedestriancount",
            pred_col="lgbm_pred",
            seasonality=SEASONALITY_HOURS,
        )
        folds.append(
            {
                "test_date": origin.isoformat(),
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "mase_baseline": baseline_mase,
                "mase_lgbm": lgbm_mase,
            }
        )
        all_test.append(test)

    if all_test:
        pooled_test = pd.concat(all_test, ignore_index=True)
        last_test_date = pooled_test["sensing_date"].max()
        pooled_train = data.loc[data["sensing_date"] < last_test_date]
        summary = {
            "seasonality_hours": SEASONALITY_HOURS,
            "folds": folds,
            "mase_baseline": panel_mase(
                pooled_test.dropna(subset=["baseline_pred"]),
                pooled_train,
                y_col="pedestriancount",
                pred_col="baseline_pred",
                seasonality=SEASONALITY_HOURS,
            ),
            "mase_lgbm": panel_mase(
                pooled_test.dropna(subset=["lgbm_pred"]),
                pooled_train,
                y_col="pedestriancount",
                pred_col="lgbm_pred",
                seasonality=SEASONALITY_HOURS,
            ),
        }
    else:
        summary = {
            "seasonality_hours": SEASONALITY_HOURS,
            "folds": folds,
            "mase_baseline": None,
            "mase_lgbm": None,
            "note": (
                "Need at least two distinct sensing_date values "
                "for rolling-origin evaluation."
            ),
        }

    out = dest or metrics_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    safe = _json_safe(summary)
    out.write_text(json.dumps(safe, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    summary = evaluate_rolling_origin()
    print(json.dumps({"evaluate": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
