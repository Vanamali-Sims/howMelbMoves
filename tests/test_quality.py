from pathlib import Path

import pandas as pd

from melbourne_footfall.ingest.pedestrian import add_observed_at
from melbourne_footfall.quality.checks import (
    duplicate_records,
    expected_hours_for_day,
    sensor_churn,
    sensor_relocation,
    timestamp_continuity,
    zero_versus_outage,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> pd.DataFrame:
    return add_observed_at(pd.read_json(FIXTURES / name))


def test_duplicates_flags_sensor_67() -> None:
    result = duplicate_records(_load("pedestrian_duplicates.json"))
    assert result.passed is False
    assert result.count_affected == 2
    assert result.detail["groups_location_id_67_68_69"] == 1
    assert result.sample_rows[0]["location_id"] == 67


def test_relocation_flags_moving_coordinates() -> None:
    result = sensor_relocation(_load("pedestrian_relocation.json"))
    assert result.passed is False
    assert result.count_affected == 1
    assert result.sample_rows[0]["location_id"] == 14


def test_zero_versus_outage_classifies_zero_and_gap() -> None:
    result = zero_versus_outage(_load("pedestrian_zeros_gaps.json"))
    assert result.detail["genuine_zeros"] == 1
    assert result.detail["gaps"] >= 1
    assert result.count_affected >= 1


def test_timestamp_continuity_finds_missing_hour() -> None:
    result = timestamp_continuity(_load("pedestrian_zeros_gaps.json"))
    assert result.passed is False
    assert result.detail["gaps"] >= 1
    hours_missing = {row["hourday"] for row in result.sample_rows}
    assert 1 in hours_missing


def test_sensor_churn_marks_partial_year() -> None:
    result = sensor_churn(_load("pedestrian_sample.json"))
    assert result.passed is True
    year = result.detail["years"][2026]
    assert 52 in year["partial_location_ids"]
    assert 52 not in year["full_year_location_ids"]
    assert year["expected_hours"] > 8000


def test_october_transition_drops_hour_2() -> None:
    from datetime import date

    hours = expected_hours_for_day(date(2026, 10, 4))
    assert 2 not in hours
    assert expected_hours_for_day(date(2026, 4, 5)) == list(range(24))
