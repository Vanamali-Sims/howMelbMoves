"""Assemble a model matrix from mart_precinct_hour."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from melbourne_footfall.paths import features_path
from melbourne_footfall.warehouse import read_precinct_hour

SEASONALITY_HOURS = 24


def add_lag_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["observed_at"] = pd.to_datetime(out["observed_at"])
    out = out.sort_values(["precinct", "observed_at"])
    out["day_of_week"] = out["observed_at"].dt.dayofweek.astype("int64")
    prior = out[["precinct", "observed_at", "pedestriancount"]].rename(
        columns={"pedestriancount": "lag_24h"}
    )
    prior["observed_at"] = prior["observed_at"] + pd.Timedelta(hours=SEASONALITY_HOURS)
    out = out.merge(prior, on=["precinct", "observed_at"], how="left")
    return out


def build_feature_matrix(
    mart: pd.DataFrame | None = None,
    *,
    dest: Path | None = None,
) -> pd.DataFrame:
    source = mart if mart is not None else read_precinct_hour()
    frame = add_lag_features(source)
    path = dest or features_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(table, path)
    return frame
