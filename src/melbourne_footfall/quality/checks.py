"""Quality checks for issues recorded in docs/source_verification.md.

Join key is `location_id` (the API field). There is no `sensor_id` column.
Zero-versus-outage follows ADR-002.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pandas as pd

from melbourne_footfall.ingest.store import OBSERVED_AT, dst_kind, localize_melbourne

GRAIN = ("location_id", "sensing_date", "hourday")
DOCUMENTED_DUP_IDS = (67, 68, 69)


@dataclass
class CheckResult:
    name: str
    passed: bool
    count_affected: int
    sample_rows: list[dict[str, Any]] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


def _as_date(value: object) -> date | None:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()


def _sample(frame: pd.DataFrame, n: int = 5) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return frame.head(n).to_dict(orient="records")


def expected_hours_for_day(day: date) -> list[int]:
    """Wall-clock hours 0-23, excluding a nonexistent October 2:00."""
    hours = []
    for hour in range(24):
        if dst_kind(day.year, day.month, day.day, hour) == "nonexistent":
            continue
        hours.append(hour)
    return hours


def sensor_churn(counts: pd.DataFrame) -> CheckResult:
    """Per year, location_ids present for every expected hour of that year."""
    if counts.empty:
        return CheckResult("sensor_churn", True, 0, detail={"years": {}})
    work = counts.copy()
    work["_date"] = pd.to_datetime(work["sensing_date"], errors="coerce")
    years: dict[int, dict[str, Any]] = {}
    affected = 0
    sample = pd.DataFrame()
    for year, group in work.groupby(work["_date"].dt.year):
        if pd.isna(year):
            continue
        year_i = int(year)
        start = date(year_i, 1, 1)
        end = date(year_i, 12, 31)
        expected: set[tuple[date, int]] = set()
        day = start
        while day <= end:
            for hour in expected_hours_for_day(day):
                expected.add((day, hour))
            day += timedelta(days=1)
        n_expected = len(expected)
        full: list[int] = []
        partial: list[int] = []
        for loc, loc_rows in group.groupby("location_id"):
            present = {
                (_as_date(d), int(h))
                for d, h in zip(
                    loc_rows["sensing_date"], loc_rows["hourday"], strict=True
                )
                if _as_date(d) is not None and pd.notna(h)
            }
            if present >= expected:
                full.append(int(loc))
            else:
                partial.append(int(loc))
        years[year_i] = {
            "expected_hours": n_expected,
            "full_year_location_ids": sorted(full),
            "partial_location_ids": sorted(partial),
        }
        affected += len(partial)
        if not sample.empty or not partial:
            continue
        sample = group.loc[group["location_id"].isin(partial[:3])]
    return CheckResult(
        name="sensor_churn",
        passed=True,
        count_affected=affected,
        sample_rows=_sample(sample),
        detail={"years": years},
    )


def zero_versus_outage(counts: pd.DataFrame) -> CheckResult:
    """ADR-002: present 0 is a genuine zero; missing expected hour is a gap."""
    work = counts.copy()
    zeros = work.loc[work["pedestriancount"] == 0]
    nulls = work.loc[work["pedestriancount"].isna()]
    work["_date"] = pd.to_datetime(work["sensing_date"], errors="coerce")
    if work["_date"].isna().all():
        gaps = pd.DataFrame()
    else:
        start = work["_date"].min().date()
        end = work["_date"].max().date()
        locations = work["location_id"].dropna().unique()
        present = {
            (int(loc), _as_date(d), int(h))
            for loc, d, h in zip(
                work["location_id"], work["sensing_date"], work["hourday"], strict=True
            )
            if pd.notna(loc) and _as_date(d) is not None and pd.notna(h)
        }
        gap_rows = []
        day = start
        while day <= end:
            for hour in expected_hours_for_day(day):
                for loc in locations:
                    key = (int(loc), day, hour)
                    if key not in present:
                        gap_rows.append(
                            {
                                "location_id": int(loc),
                                "sensing_date": day.isoformat(),
                                "hourday": hour,
                                "class": "gap",
                            }
                        )
            day += timedelta(days=1)
        gaps = pd.DataFrame(gap_rows)

    sample = pd.concat(
        [
            zeros.assign(class_="genuine_zero") if not zeros.empty else pd.DataFrame(),
            nulls.assign(class_="null_count") if not nulls.empty else pd.DataFrame(),
            gaps.head(5) if not gaps.empty else pd.DataFrame(),
        ],
        ignore_index=True,
    )
    n_gaps = int(len(gaps))
    n_nulls = int(len(nulls))
    return CheckResult(
        name="zero_versus_outage",
        passed=n_nulls == 0,
        count_affected=n_gaps + n_nulls,
        sample_rows=_sample(sample),
        detail={
            "genuine_zeros": int(len(zeros)),
            "null_counts": n_nulls,
            "gaps": n_gaps,
            "rule": (
                "present pedestriancount==0 → genuine zero; "
                "present null → unknown; "
                "missing expected hour for a location_id in the extract → gap"
            ),
        },
    )


def duplicate_records(counts: pd.DataFrame) -> CheckResult:
    if counts.empty:
        return CheckResult("duplicate_records", True, 0)
    grouped = counts.groupby(list(GRAIN), dropna=False).size().reset_index(name="n")
    dups = grouped.loc[grouped["n"] > 1]
    flagged = dups.loc[dups["location_id"].isin(DOCUMENTED_DUP_IDS)]
    return CheckResult(
        name="duplicate_records",
        passed=dups.empty,
        count_affected=int(dups["n"].sum()) if not dups.empty else 0,
        sample_rows=_sample(dups),
        detail={
            "duplicate_groups": int(len(dups)),
            "groups_location_id_67_68_69": int(len(flagged)),
            "grain": list(GRAIN),
        },
    )


def timestamp_continuity(counts: pd.DataFrame) -> CheckResult:
    """Missing hours, plus DST April ambiguous / October nonexistent labels."""
    if counts.empty:
        return CheckResult("timestamp_continuity", True, 0)
    work = counts.copy()
    work["_date"] = pd.to_datetime(work["sensing_date"], errors="coerce")
    start = work["_date"].min().date()
    end = work["_date"].max().date()
    observed = (
        work[OBSERVED_AT]
        if OBSERVED_AT in work.columns
        else pd.Series([pd.NaT] * len(work), index=work.index)
    )
    nat_rows = work.loc[observed.isna() & work["hourday"].notna()]
    dst_april = []
    dst_october = []
    day = start
    while day <= end:
        two_am = localize_melbourne(day.year, day.month, day.day, 2)
        if pd.isna(two_am):
            if day.month == 4:
                dst_april.append(day.isoformat())
            if day.month == 10:
                dst_october.append(day.isoformat())
        day += timedelta(days=1)

    gap_count = 0
    gap_sample: list[dict[str, Any]] = []
    for loc, loc_rows in work.groupby("location_id"):
        loc_start = loc_rows["_date"].min().date()
        loc_end = loc_rows["_date"].max().date()
        present = {
            (_as_date(d), int(h))
            for d, h in zip(loc_rows["sensing_date"], loc_rows["hourday"], strict=True)
            if _as_date(d) is not None and pd.notna(h)
        }
        cursor = loc_start
        while cursor <= loc_end:
            for hour in expected_hours_for_day(cursor):
                if (cursor, hour) not in present:
                    gap_count += 1
                    if len(gap_sample) < 5:
                        gap_sample.append(
                            {
                                "location_id": int(loc),
                                "sensing_date": cursor.isoformat(),
                                "hourday": hour,
                            }
                        )
            cursor += timedelta(days=1)

    passed = gap_count == 0 and nat_rows.empty
    return CheckResult(
        name="timestamp_continuity",
        passed=passed,
        count_affected=gap_count + int(len(nat_rows)),
        sample_rows=gap_sample or _sample(nat_rows),
        detail={
            "gaps": gap_count,
            "observed_at_nat": int(len(nat_rows)),
            "april_fallback_dates": dst_april,
            "october_spring_forward_dates": dst_october,
        },
    )


def _lon_lat(row: pd.Series) -> tuple[float | None, float | None]:
    loc = row.get("location")
    if isinstance(loc, dict) and "lon" in loc and "lat" in loc:
        return float(loc["lon"]), float(loc["lat"])
    lon = row.get("longitude")
    lat = row.get("latitude")
    if pd.notna(lon) and pd.notna(lat):
        return float(lon), float(lat)
    return None, None


def sensor_relocation(
    counts: pd.DataFrame, sensors: pd.DataFrame | None = None
) -> CheckResult:
    """Flag location_id with more than one distinct (lon, lat) in the extract."""
    frames = []
    if counts is not None and not counts.empty:
        frames.append(counts)
    if sensors is not None and not sensors.empty:
        frames.append(sensors)
    if not frames:
        return CheckResult("sensor_relocation", True, 0)
    combined = pd.concat(frames, ignore_index=True)
    moved = []
    for loc, group in combined.groupby("location_id"):
        pairs = {_lon_lat(row) for _, row in group.iterrows()}
        pairs.discard((None, None))
        rounded = {
            (round(lon, 6), round(lat, 6)) for lon, lat in pairs if lon is not None
        }
        if len(rounded) > 1:
            moved.append(
                {
                    "location_id": int(loc),
                    "n_coordinates": len(rounded),
                    "coordinates": sorted(rounded),
                }
            )
    return CheckResult(
        name="sensor_relocation",
        passed=not moved,
        count_affected=len(moved),
        sample_rows=moved[:5],
        detail={"n_location_ids_checked": int(combined["location_id"].nunique())},
    )


def run_all_checks(
    counts: pd.DataFrame,
    sensors: pd.DataFrame | None = None,
) -> list[CheckResult]:
    return [
        sensor_churn(counts),
        zero_versus_outage(counts),
        duplicate_records(counts),
        timestamp_continuity(counts),
        sensor_relocation(counts, sensors),
    ]
