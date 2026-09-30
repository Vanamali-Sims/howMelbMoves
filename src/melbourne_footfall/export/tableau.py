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
    tableau_export_path,
)
from melbourne_footfall.warehouse import read_precinct_hour

logger = logging.getLogger("melbourne_footfall.export.tableau")


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
    else:
        mart["mase_baseline"] = pd.NA
        mart["mase_lgbm"] = pd.NA

    path = dest or tableau_export_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(mart, preserve_index=False), path)
    return mart


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    frame = build_tableau_dataset()
    payload = {
        "rows": int(len(frame)),
        "path": str(tableau_export_path()),
    }
    print(json.dumps({"export": payload}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
