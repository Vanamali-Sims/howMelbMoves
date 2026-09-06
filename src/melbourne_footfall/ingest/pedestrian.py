"""Hourly pedestrian counts from the verified Opendatasoft export."""

from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from melbourne_footfall.config import get_source
from melbourne_footfall.ingest.opendatasoft import OpenDataSoftClient
from melbourne_footfall.ingest.store import (
    OBSERVED_AT,
    IngestResult,
    add_ingested_at,
    existing_max_date,
    localize_melbourne,
    log_ingest,
    raw_root,
    resolve_range,
    validate_columns,
    write_day_partitions,
)

SOURCE_NAME = "pedestrian_hourly_counts"
DATE_COL = "sensing_date"


def _where(start: date, end: date) -> str:
    # Syntax confirmed in docs/source_verification.md (August 2026 export).
    exclusive = end + timedelta(days=1)
    return (
        f"{DATE_COL} >= '{start.isoformat()}' AND "
        f"{DATE_COL} < '{exclusive.isoformat()}'"
    )


def add_observed_at(frame: pd.DataFrame) -> pd.DataFrame:
    """Build tz-aware observed_at from sensing_date + hourday. Source cols kept."""
    out = frame.copy()
    stamps: list[pd.Timestamp] = []
    dates = pd.to_datetime(out[DATE_COL], errors="coerce")
    hours = out["hourday"]
    for ts, hour in zip(dates, hours, strict=True):
        if pd.isna(ts) or pd.isna(hour):
            stamps.append(pd.NaT)
            continue
        stamps.append(
            localize_melbourne(int(ts.year), int(ts.month), int(ts.day), int(hour))
        )
    out[OBSERVED_AT] = stamps
    return out


def ingest_pedestrian_counts(
    start: date | None = None,
    end: date | None = None,
    *,
    raw_dir: Path | None = None,
    client: OpenDataSoftClient | None = None,
    frame: pd.DataFrame | None = None,
    default_start: date | None = None,
    default_end: date | None = None,
) -> IngestResult:
    t0 = time.perf_counter()
    source = get_source(SOURCE_NAME)
    dest = raw_root(raw_dir) / SOURCE_NAME
    src_start = source.date_range.start if source.date_range else None
    src_end = source.date_range.end if source.date_range else None
    existing = existing_max_date(dest, DATE_COL)
    start, end = resolve_range(
        start,
        end,
        existing_max=existing,
        source_start=src_start,
        source_end=src_end,
        default_start=default_start,
        default_end=default_end,
    )
    if start > end:
        result = IngestResult(SOURCE_NAME, start, end, 0, [], time.perf_counter() - t0)
        log_ingest(result)
        return result

    if frame is None:
        ods = client or OpenDataSoftClient(source.base_url)
        ods.dataset_meta(source.dataset_id)
        rows = ods.export_json(source.dataset_id, where=_where(start, end))
        frame = pd.DataFrame(rows)

    validate_columns(frame, source.expected_columns, SOURCE_NAME)
    frame = add_observed_at(frame)
    frame = add_ingested_at(frame)
    files = write_day_partitions(frame, dest, DATE_COL, start=start, end=end)
    result = IngestResult(
        SOURCE_NAME, start, end, int(len(frame)), files, time.perf_counter() - t0
    )
    log_ingest(result)
    return result
