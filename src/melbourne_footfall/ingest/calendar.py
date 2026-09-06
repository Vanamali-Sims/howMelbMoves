"""VIC public holidays, hand-maintained school terms, and major events.

Holidays come from the verified `holidays` package (AU/VIC).
School terms have no verified API — they are read from config/school_terms.csv.
Major events are read from config/events.csv. Both CSVs are config, not raw data.
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pandas as pd

from melbourne_footfall.config import get_source, project_root
from melbourne_footfall.ingest.store import (
    IngestResult,
    add_ingested_at,
    existing_max_date,
    log_ingest,
    raw_root,
    resolve_range,
    validate_columns,
    write_day_partitions,
    write_key_partitions,
)

HOLIDAYS = "vic_public_holidays"
EVENTS = "major_events"
SCHOOL_TERMS = "vic_school_terms"
HOLIDAY_DATE = "date"


def school_terms_path() -> Path:
    return project_root() / "config" / "school_terms.csv"


def events_path() -> Path:
    return project_root() / "config" / "events.csv"


def build_holidays_frame(start: date, end: date) -> pd.DataFrame:
    import holidays

    years = list(range(start.year, end.year + 1))
    mapping = holidays.country_holidays("AU", subdiv="VIC", years=years)
    rows = [
        {"date": day, "name": name}
        for day, name in sorted(mapping.items())
        if start <= day <= end
    ]
    return pd.DataFrame(rows, columns=["date", "name"])


def ingest_holidays(
    start: date | None = None,
    end: date | None = None,
    *,
    raw_dir: Path | None = None,
    frame: pd.DataFrame | None = None,
    default_start: date | None = None,
    default_end: date | None = None,
) -> IngestResult:
    t0 = time.perf_counter()
    source = get_source(HOLIDAYS)
    dest = raw_root(raw_dir) / HOLIDAYS
    existing = existing_max_date(dest, HOLIDAY_DATE)
    start, end = resolve_range(
        start,
        end,
        existing_max=existing,
        source_start=date(2019, 1, 1),
        source_end=None,
        default_start=default_start,
        default_end=default_end,
    )
    if frame is None:
        frame = build_holidays_frame(start, end)
    validate_columns(frame, source.expected_columns, HOLIDAYS)
    parsed = frame.copy()
    parsed[HOLIDAY_DATE] = pd.to_datetime(parsed[HOLIDAY_DATE]).dt.tz_localize(
        "Australia/Melbourne"
    )
    parsed = add_ingested_at(parsed)
    files = write_day_partitions(parsed, dest, HOLIDAY_DATE, start=start, end=end)
    result = IngestResult(
        HOLIDAYS, start, end, int(len(parsed)), files, time.perf_counter() - t0
    )
    log_ingest(result)
    return result


def ingest_events(
    start: date | None = None,
    end: date | None = None,
    *,
    raw_dir: Path | None = None,
    path: Path | None = None,
    frame: pd.DataFrame | None = None,
) -> IngestResult:
    t0 = time.perf_counter()
    dest = raw_root(raw_dir) / EVENTS
    if frame is None:
        frame = pd.read_csv(path or events_path(), comment="#")
    expected = {
        "event_id",
        "event_name",
        "venue",
        "start_date",
        "end_date",
        "notes",
    }
    validate_columns(frame, expected, EVENTS)
    out = frame.copy()
    out["start_date"] = pd.to_datetime(out["start_date"])
    out["end_date"] = pd.to_datetime(out["end_date"])
    if start is not None:
        out = out.loc[out["end_date"].dt.date >= start]
    if end is not None:
        out = out.loc[out["start_date"].dt.date <= end]
    out = add_ingested_at(out)
    years = sorted({int(y) for y in out["start_date"].dt.year.dropna().unique()})
    files = write_key_partitions(
        out.assign(year=out["start_date"].dt.year), dest, "year", years
    )
    result = IngestResult(
        EVENTS, start, end, int(len(out)), files, time.perf_counter() - t0
    )
    log_ingest(result)
    return result


def ingest_school_terms(
    start: date | None = None,
    end: date | None = None,
    *,
    raw_dir: Path | None = None,
    path: Path | None = None,
    frame: pd.DataFrame | None = None,
) -> IngestResult:
    t0 = time.perf_counter()
    dest = raw_root(raw_dir) / SCHOOL_TERMS
    if frame is None:
        frame = pd.read_csv(path or school_terms_path(), comment="#")
    expected = {
        "year",
        "term",
        "start_date",
        "end_date",
        "jurisdiction",
        "source_note",
    }
    validate_columns(frame, expected, SCHOOL_TERMS)
    out = frame.copy()
    out["start_date"] = pd.to_datetime(out["start_date"])
    out["end_date"] = pd.to_datetime(out["end_date"])
    if start is not None:
        out = out.loc[out["end_date"].dt.date >= start]
    if end is not None:
        out = out.loc[out["start_date"].dt.date <= end]
    out = add_ingested_at(out)
    years = sorted(
        {int(y) for y in pd.to_numeric(out["year"], errors="coerce").dropna()}
    )
    files = write_key_partitions(out, dest, "year", years)
    result = IngestResult(
        SCHOOL_TERMS, start, end, int(len(out)), files, time.perf_counter() - t0
    )
    log_ingest(result)
    return result


def ingest_calendar(
    start: date | None = None,
    end: date | None = None,
    *,
    raw_dir: Path | None = None,
    default_start: date | None = None,
    default_end: date | None = None,
) -> list[IngestResult]:
    return [
        ingest_holidays(
            start,
            end,
            raw_dir=raw_dir,
            default_start=default_start,
            default_end=default_end,
        ),
        ingest_school_terms(None, None, raw_dir=raw_dir),
        ingest_events(None, None, raw_dir=raw_dir),
    ]
