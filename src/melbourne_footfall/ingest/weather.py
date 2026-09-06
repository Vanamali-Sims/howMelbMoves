"""Open-Meteo historical archive at the verified Melbourne CBD point."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

from melbourne_footfall.config import get_source
from melbourne_footfall.ingest.opendatasoft import OpenDataSoftError
from melbourne_footfall.ingest.store import (
    IngestResult,
    add_ingested_at,
    existing_max_date,
    log_ingest,
    parse_open_meteo_time,
    raw_root,
    resolve_range,
    validate_columns,
    write_day_partitions,
)

SOURCE_NAME = "open_meteo_archive"
# Lat/lon/hourly vars/timezone recorded in docs/source_verification.md.
LATITUDE = -37.8136
LONGITUDE = 144.9631
TIMEZONE = "Australia/Melbourne"
HOURLY = "temperature_2m,precipitation,rain,wind_speed_10m,cloud_cover"
TIME_COL = "time"


def archive_url(start: date, end: date) -> str:
    source = get_source(SOURCE_NAME)
    params = {
        "latitude": str(LATITUDE),
        "longitude": str(LONGITUDE),
        "timezone": TIMEZONE,
        "hourly": HOURLY,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    return f"{source.base_url}/{source.dataset_id}?{urllib.parse.urlencode(params)}"


def flatten_hourly(payload: dict) -> pd.DataFrame:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        msg = "Open-Meteo response missing hourly object"
        raise ValueError(msg)
    return pd.DataFrame(hourly)


def fetch_archive(start: date, end: date) -> pd.DataFrame:
    url = archive_url(start, end)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, TimeoutError, json.JSONDecodeError, urllib.error.URLError) as exc:
        raise OpenDataSoftError(f"Open-Meteo request failed: {exc}") from exc
    if isinstance(payload, dict) and payload.get("error"):
        raise OpenDataSoftError(str(payload.get("reason") or payload))
    if not isinstance(payload, dict):
        raise OpenDataSoftError("Open-Meteo did not return a JSON object")
    return flatten_hourly(payload)


def ingest_weather(
    start: date | None = None,
    end: date | None = None,
    *,
    raw_dir: Path | None = None,
    frame: pd.DataFrame | None = None,
    default_start: date | None = None,
    default_end: date | None = None,
) -> IngestResult:
    t0 = time.perf_counter()
    source = get_source(SOURCE_NAME)
    dest = raw_root(raw_dir) / SOURCE_NAME
    src_start = source.date_range.start if source.date_range else None
    src_end = source.date_range.end if source.date_range else None
    existing = existing_max_date(dest, TIME_COL)
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
        frame = fetch_archive(start, end)
    validate_columns(frame, source.expected_columns, SOURCE_NAME)
    parsed = frame.copy()
    parsed[TIME_COL] = [parse_open_meteo_time(v) for v in parsed[TIME_COL]]
    parsed = add_ingested_at(parsed)
    files = write_day_partitions(parsed, dest, TIME_COL, start=start, end=end)
    result = IngestResult(
        SOURCE_NAME, start, end, int(len(parsed)), files, time.perf_counter() - t0
    )
    log_ingest(result)
    return result
