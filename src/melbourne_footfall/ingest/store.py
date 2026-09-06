"""Parquet writes, range resolution, and Melbourne timezone helpers."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from melbourne_footfall.config import project_root

MELBOURNE = ZoneInfo("Australia/Melbourne")
INGESTED_AT = "ingested_at_utc"
OBSERVED_AT = "observed_at"

logger = logging.getLogger("melbourne_footfall.ingest")


@dataclass
class IngestResult:
    source: str
    start: date | None
    end: date | None
    rows_written: int
    files: list[Path] = field(default_factory=list)
    elapsed_s: float = 0.0


class ColumnMismatchError(ValueError):
    """Returned columns do not contain the expected set."""


def raw_root(raw_dir: Path | None = None) -> Path:
    return Path(raw_dir) if raw_dir is not None else project_root() / "data" / "raw"


def validate_columns(frame: pd.DataFrame, expected: set[str], source: str) -> None:
    missing = expected - set(frame.columns)
    if missing:
        msg = (
            f"{source}: missing columns {sorted(missing)}; got {sorted(frame.columns)}"
        )
        raise ColumnMismatchError(msg)


def localize_melbourne(
    year: int,
    month: int,
    day: int,
    hour: int,
) -> pd.Timestamp:
    """Localize a wall-clock hour to Australia/Melbourne.

    DST in this zone: clocks fall back on the first Sunday in April (the 2:00
    hour occurs twice) and spring forward on the first Sunday in October (the
    2:00 hour does not exist). Pedestrian `hourday` is a wall-clock label with
    no offset, so we cannot tell which April 2:00 a row means, and an October
    2:00 cannot be represented. Both cases become NaT; quality checks report
    them. See ADR-003.
    """
    naive = pd.Timestamp(year=year, month=month, day=day, hour=hour)
    return naive.tz_localize(MELBOURNE, ambiguous="NaT", nonexistent="NaT")


def dst_kind(year: int, month: int, day: int, hour: int) -> str:
    """Classify a wall-clock hour: ok, ambiguous (April), or nonexistent (October)."""
    naive = pd.Timestamp(year=year, month=month, day=day, hour=hour)
    as_dst = naive.tz_localize(MELBOURNE, ambiguous=True, nonexistent="NaT")
    as_std = naive.tz_localize(MELBOURNE, ambiguous=False, nonexistent="NaT")
    if pd.isna(as_dst) and pd.isna(as_std):
        return "nonexistent"
    if (
        pd.notna(as_dst)
        and pd.notna(as_std)
        and as_dst.tz_convert("UTC") != as_std.tz_convert("UTC")
    ):
        return "ambiguous"
    return "ok"


def parse_open_meteo_time(value: object) -> pd.Timestamp:
    """Parse Open-Meteo hourly `time` (`YYYY-MM-DDTHH:00`, no offset)."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        return ts.tz_convert(MELBOURNE)
    return ts.tz_localize(MELBOURNE, ambiguous="NaT", nonexistent="NaT")


def add_ingested_at(frame: pd.DataFrame, when: datetime | None = None) -> pd.DataFrame:
    stamp = when or datetime.now(tz=UTC)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    out = frame.copy()
    out[INGESTED_AT] = pd.Timestamp(stamp)
    return out


def resolve_range(
    start: date | None,
    end: date | None,
    *,
    existing_max: date | None,
    source_start: date | None,
    source_end: date | None,
    default_start: date | None = None,
    default_end: date | None = None,
) -> tuple[date, date]:
    """Inclusive [start, end]. Incremental when both bounds are omitted."""
    if start is None and end is None and existing_max is not None:
        start = existing_max + timedelta(days=1)
        end = source_end or date.today()
    elif start is None and end is None:
        start = default_start or source_start or date.today()
        end = default_end or source_end or start
    elif start is None:
        start = (
            existing_max + timedelta(days=1) if existing_max else (source_start or end)
        )
    elif end is None:
        end = source_end or date.today()
    assert start is not None and end is not None
    if source_start and start < source_start:
        start = source_start
    if source_end and end > source_end:
        end = source_end
    return start, end


def existing_max_date(source_dir: Path, column: str) -> date | None:
    if not source_dir.exists():
        return None
    files = list(source_dir.rglob("*.parquet"))
    if not files:
        return None
    table = ds.dataset(str(source_dir), format="parquet").to_table(columns=[column])
    if table.num_rows == 0:
        return None
    series = table.column(column).to_pandas()
    values = pd.to_datetime(series, errors="coerce")
    if values.isna().all():
        return None
    return values.max().date()


def write_day_partitions(
    frame: pd.DataFrame,
    source_dir: Path,
    date_column: str,
    *,
    start: date,
    end: date,
) -> list[Path]:
    """Idempotent write: replace partitions for each date in [start, end]."""
    source_dir.mkdir(parents=True, exist_ok=True)
    if date_column not in frame.columns:
        msg = f"cannot partition: {date_column!r} missing"
        raise KeyError(msg)
    dates = pd.to_datetime(frame[date_column], errors="coerce")
    written: list[Path] = []
    day = start
    while day <= end:
        part_dir = source_dir / f"date={day.isoformat()}"
        if part_dir.exists():
            shutil.rmtree(part_dir)
        mask = dates.dt.date == day
        chunk = frame.loc[mask]
        if not chunk.empty:
            part_dir.mkdir(parents=True, exist_ok=True)
            path = part_dir / "part.parquet"
            _to_parquet(chunk, path)
            written.append(path)
        day += timedelta(days=1)
    return written


def write_single_parquet(frame: pd.DataFrame, path: Path) -> Path:
    """Overwrite one file. Used for snapshot sources."""
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    _to_parquet(frame, path)
    return path


def write_key_partitions(
    frame: pd.DataFrame,
    source_dir: Path,
    key_column: str,
    keys: list[object],
) -> list[Path]:
    """Replace partitions for the given keys only."""
    source_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for key in keys:
        part_dir = source_dir / f"{key_column}={key}"
        if part_dir.exists():
            shutil.rmtree(part_dir)
        series = frame[key_column]
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().any() and not isinstance(key, str):
            chunk = frame.loc[numeric == key]
        else:
            chunk = frame.loc[series.astype(str) == str(key)]
        if chunk.empty:
            continue
        part_dir.mkdir(parents=True, exist_ok=True)
        path = part_dir / "part.parquet"
        _to_parquet(chunk, path)
        written.append(path)
    return written


def _to_parquet(frame: pd.DataFrame, path: Path) -> None:
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(table, path)


def log_ingest(result: IngestResult) -> None:
    logger.info(
        "ingest source=%s start=%s end=%s rows=%s files=%s elapsed_s=%.3f",
        result.source,
        result.start,
        result.end,
        result.rows_written,
        len(result.files),
        result.elapsed_s,
    )
