"""Ingest verified sources into immutable Parquet under data/raw."""

from melbourne_footfall.ingest.calendar import ingest_calendar
from melbourne_footfall.ingest.clue import ingest_clue
from melbourne_footfall.ingest.pedestrian import ingest_pedestrian_counts
from melbourne_footfall.ingest.sensors import ingest_sensor_locations
from melbourne_footfall.ingest.weather import ingest_weather

__all__ = [
    "ingest_calendar",
    "ingest_clue",
    "ingest_pedestrian_counts",
    "ingest_sensor_locations",
    "ingest_weather",
]
