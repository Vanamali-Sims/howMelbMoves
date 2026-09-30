"""Read dbt marts from the local DuckDB warehouse."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from melbourne_footfall.paths import duckdb_path

MART_PRECINCT_HOUR = "main.mart_precinct_hour"


def read_precinct_hour(db_path: Path | None = None) -> pd.DataFrame:
    path = db_path or duckdb_path()
    if not path.exists():
        msg = f"warehouse not found: {path} (run make build after ingest)"
        raise FileNotFoundError(msg)
    con = duckdb.connect(str(path), read_only=True)
    try:
        frame = con.execute(f"select * from {MART_PRECINCT_HOUR}").fetchdf()
    finally:
        con.close()
    if frame.empty:
        msg = f"{MART_PRECINCT_HOUR} is empty"
        raise ValueError(msg)
    return frame
