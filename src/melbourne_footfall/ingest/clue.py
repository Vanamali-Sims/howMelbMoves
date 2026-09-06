"""The three verified CLUE datasets."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pandas as pd

from melbourne_footfall.config import Source, get_source
from melbourne_footfall.ingest.opendatasoft import OpenDataSoftClient
from melbourne_footfall.ingest.store import (
    IngestResult,
    add_ingested_at,
    log_ingest,
    raw_root,
    validate_columns,
    write_key_partitions,
)

ADDRESS = "clue_establishments_address_industry"
BLOCK_EST = "clue_establishments_per_block_anzsic"
BLOCK_JOBS = "clue_jobs_per_block_anzsic"
YEAR_COL = "census_year"


def _years_from_range(
    start: date | None, end: date | None, source: Source
) -> list[int]:
    src_start = (
        source.date_range.start.year
        if source.date_range and source.date_range.start
        else 2002
    )
    src_end = (
        source.date_range.end.year
        if source.date_range and source.date_range.end
        else 2024
    )
    if start is None and end is None:
        return list(range(src_start, src_end + 1))
    lo = start.year if start else src_start
    hi = end.year if end else src_end
    years = [y for y in range(lo, hi + 1) if src_start <= y <= src_end]
    if not years:
        # Requested window is after the last CLUE census; keep the latest year.
        years = [src_end]
    return years


def _ingest_clue_dataset(
    name: str,
    start: date | None,
    end: date | None,
    *,
    raw_dir: Path | None,
    client: OpenDataSoftClient | None,
    frame: pd.DataFrame | None,
) -> IngestResult:
    t0 = time.perf_counter()
    source = get_source(name)
    dest = raw_root(raw_dir) / name
    years = _years_from_range(start, end, source)
    if frame is None:
        ods = client or OpenDataSoftClient(source.base_url)
        ods.dataset_meta(source.dataset_id)
        rows = ods.export_json(source.dataset_id)
        frame = pd.DataFrame(rows)
    validate_columns(frame, source.expected_columns, name)
    year_num = pd.to_numeric(frame[YEAR_COL], errors="coerce")
    selected = frame.loc[year_num.isin(years)].copy()
    selected = add_ingested_at(selected)
    keys = sorted({int(y) for y in year_num.loc[selected.index].dropna().unique()})
    files = write_key_partitions(selected, dest, YEAR_COL, keys)
    result = IngestResult(
        name,
        date(min(keys), 1, 1) if keys else start,
        date(max(keys), 1, 1) if keys else end,
        int(len(selected)),
        files,
        time.perf_counter() - t0,
    )
    log_ingest(result)
    return result


def ingest_establishments_address(
    start: date | None = None,
    end: date | None = None,
    *,
    raw_dir: Path | None = None,
    client: OpenDataSoftClient | None = None,
    frame: pd.DataFrame | None = None,
) -> IngestResult:
    return _ingest_clue_dataset(
        ADDRESS, start, end, raw_dir=raw_dir, client=client, frame=frame
    )


def ingest_establishments_per_block(
    start: date | None = None,
    end: date | None = None,
    *,
    raw_dir: Path | None = None,
    client: OpenDataSoftClient | None = None,
    frame: pd.DataFrame | None = None,
) -> IngestResult:
    return _ingest_clue_dataset(
        BLOCK_EST, start, end, raw_dir=raw_dir, client=client, frame=frame
    )


def ingest_jobs_per_block(
    start: date | None = None,
    end: date | None = None,
    *,
    raw_dir: Path | None = None,
    client: OpenDataSoftClient | None = None,
    frame: pd.DataFrame | None = None,
) -> IngestResult:
    return _ingest_clue_dataset(
        BLOCK_JOBS, start, end, raw_dir=raw_dir, client=client, frame=frame
    )


def ingest_clue(
    start: date | None = None,
    end: date | None = None,
    *,
    raw_dir: Path | None = None,
    client: OpenDataSoftClient | None = None,
    frames: dict[str, pd.DataFrame] | None = None,
) -> list[IngestResult]:
    frames = frames or {}
    return [
        _ingest_clue_dataset(
            name,
            start,
            end,
            raw_dir=raw_dir,
            client=client,
            frame=frames.get(name),
        )
        for name in (ADDRESS, BLOCK_EST, BLOCK_JOBS)
    ]
