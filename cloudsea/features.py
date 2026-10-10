"""Features for the call made on evening D about sunrise on D+1, using only what exists by 20:30 IST on D.

Sources and cut-offs:
* Airport reports (METAR) up to 20:00 IST on D. The 20:30 report may not have arrived when the job runs.
* The 00 UTC ECMWF IFS run of day D (published by ~08 UTC = 13:30 IST): its values for the night and for
  D+1 dawn (+24..+26 h).
* The outcome of D's own dawn (known by 07:30 on D), airport part only.

`tests/test_leakage.py` scrambles every observation after the cut-off and checks the features don't move.
"""
from __future__ import annotations

from datetime import time

import numpy as np
import pandas as pd

OBS_CUTOFF = time(20, 0)        # last airport report used, IST
EVENING_START = time(17, 30)
AFTERNOON = (time(11, 30), time(17, 30))

OBS_FEATURES = [
    "eve_temp_c", "eve_dew_c", "eve_spread_c", "eve_spread_min_c", "eve_wind_kmh", "eve_wind_max_kmh",
    "eve_vis_km", "eve_ceiling_kft", "eve_lowest_layer_kft", "eve_deck_reports",
    "afternoon_tmax_c", "cooling_c", "rain_reports_24h", "rain_reports_72h",
    "today_low_layer_reports", "today_min_vis_km", "today_sea_airport",
    "doy_sin", "doy_cos",
]
NWP_FEATURES = [
    "nwp_dawn_low_cloud_max", "nwp_dawn_vis_min_km", "nwp_dawn_spread_min_c", "nwp_dawn_wind_mean",
    "nwp_dawn_blh_min", "nwp_night_tmin_c", "nwp_night_wind_mean", "nwp_night_cloud_mean",
    "nwp_night_low_cloud_max", "nwp_precip_24h_mm",
]


def _call_day_of_report(ist: pd.Series) -> pd.Series:
    """The call day whose 24 h window (previous 20:00, this 20:00] contains each report."""
    shifted = ist + pd.Timedelta(hours=4) - pd.Timedelta(seconds=1)
    return pd.to_datetime(shifted.dt.date)


def obs_features(reports: pd.DataFrame, dawn: pd.DataFrame) -> pd.DataFrame:
    """Airport-based features per call day D (index = D, a date at midnight)."""
    t = reports["ist"].dt.time
    day = pd.to_datetime(reports["date"])
    r = reports.assign(day=day)

    eve = r[(t >= EVENING_START) & (t <= OBS_CUTOFF)]
    g = eve.groupby("day")
    last = eve.sort_values("utc").groupby("day").tail(1).set_index("day")
    f = pd.DataFrame({
        "eve_temp_c": last["temp_c"],
        "eve_dew_c": last["dew_c"],
        "eve_spread_c": last["spread_c"],
        "eve_spread_min_c": g["spread_c"].min(),
        "eve_wind_kmh": g["wind_kmh"].mean(),
        "eve_wind_max_kmh": g["wind_kmh"].max(),
        "eve_vis_km": g["vis_m"].min() / 1000,
        "eve_ceiling_kft": g["ceiling_ft"].min() / 1000,
        "eve_lowest_layer_kft": g["lowest_layer_ft"].min() / 1000,
        "eve_deck_reports": g["deck_near_summit"].sum(),
    })
    aft = r[(t >= AFTERNOON[0]) & (t < AFTERNOON[1])].groupby("day")["temp_c"].max()
    f["afternoon_tmax_c"] = aft
    f["cooling_c"] = f["afternoon_tmax_c"] - f["eve_temp_c"]

    rain = r.assign(call_day=_call_day_of_report(r["ist"])).groupby("call_day")["precip"].sum()
    rain = rain.asfreq("D", fill_value=0)
    f["rain_reports_24h"] = rain
    f["rain_reports_72h"] = rain.rolling(3, min_periods=1).sum()

    # D's own dawn is over by 07:30, long before the call. Airport part only (no model humidity).
    f["today_low_layer_reports"] = dawn["low_layer_reports"]
    f["today_min_vis_km"] = dawn["min_vis_m"] / 1000
    f["today_sea_airport"] = dawn["A_low_layer"].astype("Float64").astype(float)

    doy = f.index.dayofyear
    f["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    f["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    return f[OBS_FEATURES]


def nwp_features(runs: pd.DataFrame) -> pd.DataFrame:
    """Per run day D (00 UTC run): night (+15..+24 h, 20:30-05:30 IST) and D+1 dawn (+24..+26 h)."""
    r = runs.copy()
    r["spread"] = r["temperature_2m"] - r["dew_point_2m"]
    dawn = r[r["lead_h"].between(24, 26)].groupby("run_day")
    night = r[r["lead_h"].between(15, 24)].groupby("run_day")
    day_rain = r[r["lead_h"].between(0, 23)].groupby("run_day")["precipitation"].sum()
    f = pd.DataFrame({
        "nwp_dawn_low_cloud_max": dawn["cloud_cover_low"].max(),
        "nwp_dawn_vis_min_km": dawn["visibility"].min() / 1000,
        "nwp_dawn_spread_min_c": dawn["spread"].min(),
        "nwp_dawn_wind_mean": dawn["wind_speed_10m"].mean(),
        "nwp_dawn_blh_min": dawn["boundary_layer_height"].min(),
        "nwp_night_tmin_c": night["temperature_2m"].min(),
        "nwp_night_wind_mean": night["wind_speed_10m"].mean(),
        "nwp_night_cloud_mean": night["cloud_cover"].mean(),
        "nwp_night_low_cloud_max": night["cloud_cover_low"].max(),
        "nwp_precip_24h_mm": day_rain,
    })
    f.index = pd.to_datetime(f.index)
    return f[NWP_FEATURES]


def build_table(reports: pd.DataFrame, dawn: pd.DataFrame, runs: pd.DataFrame | None,
                label_col: str) -> pd.DataFrame:
    """One row per call day D: features known at 20:30 IST on D, and the target = label for D+1's dawn."""
    table = obs_features(reports, dawn)
    if runs is not None and len(runs):
        table = table.join(nwp_features(runs), how="left")
    else:
        for c in NWP_FEATURES:
            table[c] = np.nan
    target = dawn[label_col].astype("Float64").astype(float)
    table["target_date"] = table.index + pd.Timedelta(days=1)
    table["y"] = target.reindex(table["target_date"]).to_numpy()
    return table
