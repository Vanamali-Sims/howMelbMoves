"""Load ingested Parquet and summarise quality checks."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

from melbourne_footfall.ingest.store import raw_root
from melbourne_footfall.quality.checks import CheckResult


def _read_parquet_tree(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    files = list(path.rglob("*.parquet"))
    if not files:
        return pd.DataFrame()
    return ds.dataset(str(path), format="parquet").to_table().to_pandas()


def load_raw_counts(raw_dir: Path | None = None) -> pd.DataFrame:
    return _read_parquet_tree(raw_root(raw_dir) / "pedestrian_hourly_counts")


def load_raw_sensors(raw_dir: Path | None = None) -> pd.DataFrame:
    return _read_parquet_tree(raw_root(raw_dir) / "pedestrian_sensor_locations")


def _jsonable(value: object) -> object:
    if isinstance(value, pd.Timestamp | datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if pd.isna(value):
        return None
    return value


def summarise(results: list[CheckResult]) -> list[dict]:
    return [
        {
            "name": r.name,
            "passed": r.passed,
            "count_affected": r.count_affected,
            "sample_rows": _jsonable(r.sample_rows),
            "detail": _jsonable(r.detail),
        }
        for r in results
    ]
