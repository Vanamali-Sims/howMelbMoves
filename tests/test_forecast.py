from datetime import date, timedelta

import numpy as np
import pandas as pd

from melbourne_footfall.features.build import add_lag_features
from melbourne_footfall.models.metrics import in_sample_mase_scale, mase, panel_mase


def test_lag_24h_aligns_same_hour_prior_day() -> None:
    base = date(2026, 8, 1)
    rows = []
    for day_offset in (0, 1):
        d = base + timedelta(days=day_offset)
        for hour in (9, 10):
            rows.append(
                {
                    "precinct": "A",
                    "sensing_date": d,
                    "hourday": hour,
                    "observed_at": pd.Timestamp(
                        d.year, d.month, d.day, hour
                    ).tz_localize("Australia/Melbourne"),
                    "pedestriancount": day_offset * 100 + hour,
                    "temperature_2m": 10.0,
                    "precipitation": 0.0,
                    "rain": 0.0,
                    "wind_speed_10m": 5.0,
                    "cloud_cover": 0,
                    "sensor_count": 1,
                    "is_public_holiday": False,
                    "is_school_term": False,
                    "is_event_day": False,
                }
            )
    frame = add_lag_features(pd.DataFrame(rows))
    second_day = frame.loc[frame["sensing_date"] == base + timedelta(days=1)]
    assert second_day["lag_24h"].tolist() == [9.0, 10.0]


def test_mase_matches_manual_ratio() -> None:
    y = np.array([0.0, 1.0, 2.0, 3.0])
    pred = np.array([1.0, 1.0, 2.0, 2.0])
    scale = in_sample_mase_scale(y, seasonality=1)
    assert scale == 1.0
    assert mase(y, pred, scale=scale) == 0.5


def test_panel_mase_uses_train_scale() -> None:
    train = pd.DataFrame(
        {
            "precinct": ["A"] * 4,
            "sensing_date": [date(2026, 8, 1)] * 4,
            "hourday": [0, 1, 2, 3],
            "pedestriancount": [0.0, 1.0, 2.0, 3.0],
            "baseline_pred": [0.0, 0.0, 1.0, 2.0],
        }
    )
    test = pd.DataFrame(
        {
            "precinct": ["A"],
            "sensing_date": [date(2026, 8, 2)],
            "hourday": [0],
            "pedestriancount": [2.0],
            "baseline_pred": [1.0],
        }
    )
    score = panel_mase(
        test,
        train,
        y_col="pedestriancount",
        pred_col="baseline_pred",
        seasonality=1,
    )
    assert score == 1.0
