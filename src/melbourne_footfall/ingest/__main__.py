"""CLI: python -m melbourne_footfall.ingest --start YYYY-MM-DD --end YYYY-MM-DD."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date
from pathlib import Path

from melbourne_footfall.ingest.calendar import (
    ingest_events,
    ingest_holidays,
    ingest_school_terms,
)
from melbourne_footfall.ingest.clue import (
    ingest_establishments_address,
    ingest_establishments_per_block,
    ingest_jobs_per_block,
)
from melbourne_footfall.ingest.pedestrian import ingest_pedestrian_counts
from melbourne_footfall.ingest.sensors import ingest_sensor_locations
from melbourne_footfall.ingest.store import IngestResult
from melbourne_footfall.ingest.weather import ingest_weather
from melbourne_footfall.quality.checks import run_all_checks
from melbourne_footfall.quality.runner import (
    load_raw_counts,
    load_raw_sensors,
    summarise,
)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Ingest verified melbourne-footfall sources"
    )
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--raw-dir", type=Path, default=None)
    parser.add_argument(
        "--skip-clue-address",
        action="store_true",
        help="Skip the 413k-row address table (still ingest the two block tables).",
    )
    args = parser.parse_args(argv)

    results: list[IngestResult] = []
    results.append(
        ingest_pedestrian_counts(
            args.start,
            args.end,
            raw_dir=args.raw_dir,
            default_start=args.start,
            default_end=args.end,
        )
    )
    results.append(ingest_sensor_locations(args.start, args.end, raw_dir=args.raw_dir))
    results.append(
        ingest_weather(
            args.start,
            args.end,
            raw_dir=args.raw_dir,
            default_start=args.start,
            default_end=args.end,
        )
    )
    holiday_start = date(args.start.year, 1, 1) if args.start else args.start
    holiday_end = date(args.end.year, 12, 31) if args.end else args.end
    results.append(
        ingest_holidays(
            holiday_start,
            holiday_end,
            raw_dir=args.raw_dir,
            default_start=holiday_start,
            default_end=holiday_end,
        )
    )
    results.append(ingest_school_terms(None, None, raw_dir=args.raw_dir))
    results.append(ingest_events(None, None, raw_dir=args.raw_dir))
    clue_start = date(2024, 1, 1)
    clue_end = date(2024, 12, 31)
    results.append(
        ingest_establishments_per_block(clue_start, clue_end, raw_dir=args.raw_dir)
    )
    results.append(ingest_jobs_per_block(clue_start, clue_end, raw_dir=args.raw_dir))
    if not args.skip_clue_address:
        results.append(
            ingest_establishments_address(clue_start, clue_end, raw_dir=args.raw_dir)
        )

    payload = [
        {
            "source": r.source,
            "start": r.start.isoformat() if r.start else None,
            "end": r.end.isoformat() if r.end else None,
            "rows_written": r.rows_written,
            "files": [str(p) for p in r.files],
            "elapsed_s": round(r.elapsed_s, 3),
        }
        for r in results
    ]
    print(json.dumps({"ingest": payload}, indent=2))

    counts = load_raw_counts(args.raw_dir)
    sensors = load_raw_sensors(args.raw_dir)
    checks = run_all_checks(counts, sensors)
    print(json.dumps({"quality": summarise(checks)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
