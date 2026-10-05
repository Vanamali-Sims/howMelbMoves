"""Tests for Tableau export."""

from pathlib import Path

import pandas as pd

from melbourne_footfall.export import tableau as tableau_export


def test_build_tableau_dataset_writes_parquet_and_csv(tmp_path: Path, monkeypatch) -> None:
    parquet = tmp_path / "out.parquet"
    csv = tmp_path / "out.csv"
    mart = pd.DataFrame(
        {
            "precinct": ["A"],
            "sensing_date": [pd.Timestamp("2026-08-01").date()],
            "hourday": [10],
            "pedestriancount": [100],
            "observed_at": [pd.Timestamp("2026-08-01 10:00:00")],
        }
    )

    monkeypatch.setattr(tableau_export, "read_precinct_hour", lambda: mart.copy())
    monkeypatch.setattr(tableau_export, "tableau_export_path", lambda: parquet)
    monkeypatch.setattr(tableau_export, "tableau_export_csv_path", lambda: csv)
    monkeypatch.setattr(tableau_export, "predictions_path", lambda: tmp_path / "none.parquet")
    monkeypatch.setattr(tableau_export, "metrics_path", lambda: tmp_path / "none.json")

    tableau_export.build_tableau_dataset()

    assert parquet.is_file()
    assert csv.is_file()
    assert "precinct" in csv.read_text(encoding="utf-8").splitlines()[0]
