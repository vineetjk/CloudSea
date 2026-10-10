"""Leakage check: features for call day D must not change when everything after D's cut-off is scrambled."""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from cloudsea import features
from cloudsea.config import IST


def fake_reports(days: int = 10, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = datetime(2025, 1, 1, tzinfo=IST)
    times = [start + timedelta(minutes=30 * i) for i in range(days * 48)]
    n = len(times)
    df = pd.DataFrame({"ist": pd.to_datetime(times)})
    df["utc"] = df["ist"].dt.tz_convert("UTC")
    df["date"] = df["ist"].dt.date
    df["temp_c"] = rng.normal(20, 4, n)
    df["dew_c"] = df["temp_c"] - rng.uniform(0, 6, n)
    df["spread_c"] = df["temp_c"] - df["dew_c"]
    df["wind_kmh"] = rng.uniform(0, 20, n)
    df["vis_m"] = rng.uniform(100, 8000, n)
    df["ceiling_ft"] = rng.choice([np.nan, 300, 800, 2500], n)
    df["lowest_layer_ft"] = df["ceiling_ft"]
    df["deck_near_summit"] = rng.random(n) < 0.1
    df["precip"] = rng.random(n) < 0.05
    return df


def fake_dawn(reports: pd.DataFrame) -> pd.DataFrame:
    days = pd.to_datetime(sorted(set(reports["date"])))
    rng = np.random.default_rng(1)
    return pd.DataFrame({"low_layer_reports": rng.integers(0, 5, len(days)),
                         "min_vis_m": rng.uniform(100, 8000, len(days)),
                         "A_low_layer": rng.integers(0, 2, len(days)).astype(float)}, index=days)


def scramble_after(reports: pd.DataFrame, cutoff: pd.Timestamp, seed: int = 99) -> pd.DataFrame:
    out = reports.copy()
    late = out["ist"] > cutoff
    rng = np.random.default_rng(seed)
    for col in ["temp_c", "dew_c", "spread_c", "wind_kmh", "vis_m"]:
        out.loc[late, col] = rng.normal(0, 50, late.sum())
    out.loc[late, "precip"] = True
    out.loc[late, "deck_near_summit"] = True
    out.loc[late, "ceiling_ft"] = 100.0
    out.loc[late, "lowest_layer_ft"] = 100.0
    return out


@pytest.mark.parametrize("day_offset", [2, 5, 8])
def test_obs_features_ignore_everything_after_cutoff(day_offset):
    reports = fake_reports()
    dawn = fake_dawn(reports)
    day = pd.Timestamp("2025-01-01") + pd.Timedelta(days=day_offset)
    cutoff = pd.Timestamp(datetime.combine(day.date(), features.OBS_CUTOFF), tz=IST)

    before = features.obs_features(reports, dawn).loc[day]
    # Also scramble the *next* dawn summary, which is the target and must never feed a feature.
    dawn2 = dawn.copy()
    dawn2.loc[dawn2.index > day, :] = [99, 1.0, 1.0]
    after = features.obs_features(scramble_after(reports, cutoff), dawn2).loc[day]
    pd.testing.assert_series_equal(before, after, check_names=False)


def test_target_is_next_dawn_and_not_a_feature():
    reports = fake_reports()
    dawn = fake_dawn(reports)
    dawn["B"] = dawn["A_low_layer"]
    table = features.build_table(reports, dawn, None, "B")
    assert "B" not in features.OBS_FEATURES + features.NWP_FEATURES
    d = pd.Timestamp("2025-01-03")
    assert table.loc[d, "y"] == dawn.loc[d + pd.Timedelta(days=1), "B"]


def test_nwp_features_use_only_the_days_00utc_run():
    rows = []
    for run_day in pd.to_datetime(["2025-01-01", "2025-01-02"]):
        for lead in range(36):
            rows.append({"run_day": run_day, "lead_h": lead, "temperature_2m": 15.0, "dew_point_2m": 14.0,
                         "wind_speed_10m": 5.0, "cloud_cover": 10.0, "cloud_cover_low": 80.0 if lead == 25 else 0.0,
                         "visibility": 500.0 if lead == 25 else 20000.0, "boundary_layer_height": 100.0,
                         "precipitation": 0.0})
    f = features.nwp_features(pd.DataFrame(rows))
    assert f.loc["2025-01-01", "nwp_dawn_low_cloud_max"] == 80.0
    assert f.loc["2025-01-01", "nwp_dawn_vis_min_km"] == 0.5
