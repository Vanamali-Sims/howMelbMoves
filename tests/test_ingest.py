from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from melbourne_footfall.ingest.pedestrian import (
    add_observed_at,
    ingest_pedestrian_counts,
)
from melbourne_footfall.ingest.sensors import ingest_sensor_locations
from melbourne_footfall.ingest.store import (
    ColumnMismatchError,
    dst_kind,
    existing_max_date,
    localize_melbourne,
)
from melbourne_footfall.ingest.weather import ingest_weather

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> pd.DataFrame:
    return pd.read_json(FIXTURES / name)


def test_idempotent_overwrite(tmp_path: Path) -> None:
    frame = _load("pedestrian_sample.json")
    first = ingest_pedestrian_counts(
        date(2026, 7, 5),
        date(2026, 7, 5),
        raw_dir=tmp_path,
        frame=frame,
    )
    second = ingest_pedestrian_counts(
        date(2026, 7, 5),
        date(2026, 7, 5),
        raw_dir=tmp_path,
        frame=frame,
    )
    assert first.rows_written == 2
    assert second.rows_written == 2
    written = pd.read_parquet(tmp_path / "pedestrian_hourly_counts")
    assert len(written) == 2
    grain = written.groupby(["location_id", "sensing_date", "hourday"]).size()
    assert (grain == 1).all()


def test_incremental_starts_after_existing(tmp_path: Path) -> None:
    frame = _load("pedestrian_sample.json")
    ingest_pedestrian_counts(
        date(2026, 7, 5),
        date(2026, 7, 5),
        raw_dir=tmp_path,
        frame=frame,
    )
    assert existing_max_date(
        tmp_path / "pedestrian_hourly_counts", "sensing_date"
    ) == date(2026, 7, 5)


def test_column_validation_failure(tmp_path: Path) -> None:
    frame = _load("pedestrian_sample.json").drop(columns=["pedestriancount"])
    with pytest.raises(ColumnMismatchError, match="pedestriancount"):
        ingest_pedestrian_counts(
            date(2026, 7, 5),
            date(2026, 7, 5),
            raw_dir=tmp_path,
            frame=frame,
        )


def test_dst_april_ambiguous_and_october_missing() -> None:
    assert dst_kind(2026, 4, 5, 2) == "ambiguous"
    assert dst_kind(2026, 10, 4, 2) == "nonexistent"
    assert dst_kind(2026, 8, 1, 2) == "ok"
    assert pd.isna(localize_melbourne(2026, 4, 5, 2))
    assert pd.isna(localize_melbourne(2026, 10, 4, 2))
    assert pd.notna(localize_melbourne(2026, 8, 1, 2))


def test_observed_at_nat_on_dst_fixture() -> None:
    frame = add_observed_at(_load("pedestrian_dst.json"))
    assert frame["observed_at"].isna().all()


def test_sensor_snapshot_overwrite(tmp_path: Path) -> None:
    frame = _load("sensors_sample.json")
    first = ingest_sensor_locations(raw_dir=tmp_path, frame=frame)
    second = ingest_sensor_locations(raw_dir=tmp_path, frame=frame)
    assert first.rows_written == second.rows_written == 2
    written = pd.read_parquet(tmp_path / "pedestrian_sensor_locations")
    assert len(written) == 2
    assert "ingested_at_utc" in written.columns


def test_weather_parses_melbourne_tz(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "time": ["2026-08-01T00:00", "2026-08-01T01:00"],
            "temperature_2m": [8.1, 7.9],
            "precipitation": [0.0, 0.0],
            "rain": [0.0, 0.0],
            "wind_speed_10m": [10.0, 9.0],
            "cloud_cover": [10, 12],
        }
    )
    result = ingest_weather(
        date(2026, 8, 1),
        date(2026, 8, 1),
        raw_dir=tmp_path,
        frame=frame,
    )
    assert result.rows_written == 2
    written = pd.read_parquet(tmp_path / "open_meteo_archive")
    tz = str(written["time"].dt.tz)
    assert "Australia" in tz or "Melbourne" in tz
