"""Resolved paths for data, warehouse, and model artefacts."""

from __future__ import annotations

import os
from pathlib import Path

from melbourne_footfall.config import project_root


def data_dir() -> Path:
    root = os.environ.get("DATA_DIR", "data")
    path = Path(root)
    return path if path.is_absolute() else project_root() / path


def duckdb_path() -> Path:
    raw = os.environ.get("DUCKDB_PATH", "data/warehouse/melbourne_footfall.duckdb")
    path = Path(raw)
    return path if path.is_absolute() else project_root() / path


def staged_dir() -> Path:
    return data_dir() / "staged"


def models_dir() -> Path:
    return staged_dir() / "models"


def features_path() -> Path:
    return staged_dir() / "precinct_hour_features.parquet"


def predictions_path() -> Path:
    return staged_dir() / "precinct_hour_predictions.parquet"


def metrics_path() -> Path:
    return staged_dir() / "metrics.json"


def export_dir() -> Path:
    return staged_dir() / "export"


def tableau_export_path() -> Path:
    return export_dir() / "tableau_precinct_hour.parquet"


def tableau_export_csv_path() -> Path:
    """Tableau Public connects via Text file; Parquet is the pipeline canonical copy."""
    return export_dir() / "tableau_precinct_hour.csv"


def lightgbm_model_path() -> Path:
    return models_dir() / "lightgbm.txt"
