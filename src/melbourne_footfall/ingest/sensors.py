"""Pedestrian sensor locations snapshot."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pandas as pd

from melbourne_footfall.config import get_source
from melbourne_footfall.ingest.opendatasoft import OpenDataSoftClient
from melbourne_footfall.ingest.store import (
    IngestResult,
    add_ingested_at,
    log_ingest,
    raw_root,
    validate_columns,
    write_single_parquet,
)

SOURCE_NAME = "pedestrian_sensor_locations"


def ingest_sensor_locations(
    start: date | None = None,
    end: date | None = None,
    *,
    raw_dir: Path | None = None,
    client: OpenDataSoftClient | None = None,
    frame: pd.DataFrame | None = None,
) -> IngestResult:
    """Full snapshot overwrite. Date range is accepted and ignored (no history)."""
    t0 = time.perf_counter()
    source = get_source(SOURCE_NAME)
    dest = raw_root(raw_dir) / SOURCE_NAME
    if frame is None:
        ods = client or OpenDataSoftClient(source.base_url)
        ods.dataset_meta(source.dataset_id)
        rows = ods.export_json(source.dataset_id)
        frame = pd.DataFrame(rows)
    validate_columns(frame, source.expected_columns, SOURCE_NAME)
    frame = add_ingested_at(frame)
    path = write_single_parquet(frame, dest / "sensors.parquet")
    result = IngestResult(
        SOURCE_NAME, start, end, int(len(frame)), [path], time.perf_counter() - t0
    )
    log_ingest(result)
    return result
