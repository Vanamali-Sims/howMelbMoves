"""Export a Tableau-ready dataset from marts and model outputs."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from melbourne_footfall.paths import (
    metrics_path,
    predictions_path,
    tableau_export_csv_path,
    tableau_export_path,
)
from melbourne_footfall.warehouse import read_precinct_hour

logger = logging.getLogger("melbourne_footfall.export.tableau")


def _add_precinct_profile(mart: pd.DataFrame) -> pd.DataFrame:
    """Precompute the precinct comparison fields so Tableau only has to display them.

    - `precinct_hourly_index`: that precinct-hour's mean pedestriancount divided by
      the precinct's own overall mean (1.0 = typical for that precinct). Lets a
      precinct x hour heatmap compare shapes across precincts whose raw volumes
      span two orders of magnitude (CBD vs residential fringe).
    - `precinct_rank`: dense rank of precincts by mean pedestriancount, 1 = busiest.
      Drives small-multiple ordering without a Tableau calculated field.
    """
    out = mart.copy()
    precinct_mean = out.groupby("precinct")["pedestriancount"].transform("mean")
    hour_mean = out.groupby(["precinct", "hourday"])["pedestriancount"].transform(
        "mean"
    )
    out["precinct_hourly_index"] = hour_mean / precinct_mean.mask(precinct_mean == 0)

    rank_by_precinct = (
        out.groupby("precinct")["pedestriancount"]
        .mean()
        .rank(ascending=False, method="dense")
        .astype("Int64")
    )
    out["precinct_rank"] = out["precinct"].map(rank_by_precinct)
    return out


def build_tableau_dataset(
    *,
    predictions_file: Path | None = None,
    metrics_file: Path | None = None,
    dest: Path | None = None,
) -> pd.DataFrame:
    mart = read_precinct_hour()
    keys = ["precinct", "sensing_date", "hourday"]
    mart["sensing_date"] = pd.to_datetime(mart["sensing_date"]).dt.date

    pred_path = predictions_file or predictions_path()
    if pred_path.exists():
        preds = pd.read_parquet(pred_path)
        preds["sensing_date"] = pd.to_datetime(preds["sensing_date"]).dt.date
        keep = keys + ["baseline_pred", "lgbm_pred", "lag_24h"]
        keep = [c for c in keep if c in preds.columns]
        mart = mart.merge(preds[keep], on=keys, how="left")
    else:
        mart["baseline_pred"] = pd.NA
        mart["lgbm_pred"] = pd.NA
        mart["lag_24h"] = pd.NA

    metrics_file = metrics_file or metrics_path()
    if metrics_file.exists():
        metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
        mart["mase_baseline"] = metrics.get("mase_baseline")
        mart["mase_lgbm"] = metrics.get("mase_lgbm")
        mart["mase_baseline_precinct"] = mart["precinct"].map(
            metrics.get("mase_baseline_by_precinct") or {}
        )
        mart["mase_lgbm_precinct"] = mart["precinct"].map(
            metrics.get("mase_lgbm_by_precinct") or {}
        )
    else:
        mart["mase_baseline"] = pd.NA
        mart["mase_lgbm"] = pd.NA
        mart["mase_baseline_precinct"] = pd.NA
        mart["mase_lgbm_precinct"] = pd.NA

    if "baseline_pred" in mart.columns:
        mart["baseline_error"] = mart["pedestriancount"] - mart["baseline_pred"]
    if "lgbm_pred" in mart.columns:
        mart["lgbm_error"] = mart["pedestriancount"] - mart["lgbm_pred"]

    mart = _add_precinct_profile(mart)

    path = dest or tableau_export_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(mart, preserve_index=False), path)
    csv_path = tableau_export_csv_path()
    mart.to_csv(csv_path, index=False)
    return mart


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    frame = build_tableau_dataset()
    payload = {
        "rows": int(len(frame)),
        "parquet": str(tableau_export_path()),
        "csv": str(tableau_export_csv_path()),
    }
    print(json.dumps({"export": payload}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
