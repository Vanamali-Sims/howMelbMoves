"""Train seasonal-naive baseline and LightGBM on the feature matrix."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from melbourne_footfall.features.build import SEASONALITY_HOURS
from melbourne_footfall.paths import (
    features_path,
    lightgbm_model_path,
    models_dir,
    predictions_path,
)

logger = logging.getLogger("melbourne_footfall.models.train")

NUMERIC_FEATURES = [
    "hourday",
    "day_of_week",
    "temperature_2m",
    "precipitation",
    "rain",
    "wind_speed_10m",
    "cloud_cover",
    "sensor_count",
    "lag_24h",
    "is_public_holiday",
    "is_school_term",
    "is_event_day",
]
CATEGORICAL_FEATURES = ["precinct"]
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def feature_columns(frame: pd.DataFrame) -> list[str]:
    """Use numeric columns that are present; always keep precinct."""
    cols = list(CATEGORICAL_FEATURES)
    for col in NUMERIC_FEATURES:
        if frame[col].notna().any():
            cols.append(col)
    return cols


def load_feature_matrix(path: Path | None = None) -> pd.DataFrame:
    source = path or features_path()
    if not source.exists():
        msg = f"feature matrix not found: {source} (run make features)"
        raise FileNotFoundError(msg)
    return pd.read_parquet(source)


def _coerce_flags(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in ("is_public_holiday", "is_school_term", "is_event_day"):
        out[col] = out[col].astype(bool).astype(int)
    return out


def train_and_predict(
    frame: pd.DataFrame | None = None,
    *,
    features_file: Path | None = None,
    predictions_file: Path | None = None,
) -> tuple[pd.DataFrame, lgb.LGBMRegressor | None]:
    if frame is not None:
        data = _coerce_flags(frame)
    else:
        data = _coerce_flags(load_feature_matrix(features_file))
    data["baseline_pred"] = data["lag_24h"]
    data["lgbm_pred"] = np.nan

    train_rows = data.dropna(subset=["pedestriancount"])
    model: lgb.LGBMRegressor | None = None
    models_dir().mkdir(parents=True, exist_ok=True)
    model_path = lightgbm_model_path()
    features = feature_columns(train_rows)

    if len(train_rows.dropna(subset=features)) >= 10:
        work = train_rows.dropna(subset=features).copy()
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
        model.booster_.save_model(str(model_path))
        predict_rows = data.dropna(subset=features)
        if not predict_rows.empty:
            predict_work = predict_rows.copy()
            categories = work["precinct"].astype("category").cat.categories
            predict_work["precinct"] = pd.Categorical(
                predict_work["precinct"],
                categories=categories,
            )
            preds = model.predict(predict_work[features])
            data.loc[predict_work.index, "lgbm_pred"] = preds
    elif model_path.exists():
        model_path.unlink()

    dest = predictions_file or predictions_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(data, preserve_index=False), dest)
    return data, model


def train_summary(frame: pd.DataFrame) -> dict[str, object]:
    return {
        "rows": int(len(frame)),
        "rows_with_baseline": int(frame["baseline_pred"].notna().sum()),
        "rows_with_lgbm": int(frame["lgbm_pred"].notna().sum()),
        "seasonality_hours": SEASONALITY_HOURS,
        "model_path": str(lightgbm_model_path()),
    }


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    frame, _ = train_and_predict()
    print(json.dumps({"train": train_summary(frame)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
