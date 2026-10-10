"""Live data for the nightly and grader jobs: recent airport reports, today's ECMWF run, summit forecasts."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx
import pandas as pd

from cloudsea import metar
from cloudsea.config import SUMMIT
from cloudsea.data import iem, openmeteo

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def recent_reports(days: int = 5) -> pd.DataFrame:
    now = datetime.now(UTC)
    return metar.from_csv_bytes(iem.fetch_range(now - timedelta(days=days), now))


def todays_run(day: date) -> pd.DataFrame:
    """The 00 UTC ECMWF IFS run of `day`, in the same long format as `openmeteo.load_runs`."""
    with httpx.Client(headers={"User-Agent": openmeteo.UA}, timeout=60) as http:
        data = openmeteo.fetch_run(http, day)
    df = openmeteo._hourly_frame(data)
    df["run_day"] = pd.Timestamp(day)
    df["lead_h"] = ((df["time"] - pd.Timestamp(day, tz="UTC")) / pd.Timedelta(hours=1)).astype(int)
    return df


def _summit_hourly(day: date, variables: list[str], timezone: str) -> pd.DataFrame:
    params = {"latitude": SUMMIT.lat, "longitude": SUMMIT.lon, "elevation": SUMMIT.elev_m,
              "hourly": ",".join(variables), "timezone": timezone,
              "start_date": day.isoformat(), "end_date": day.isoformat()}
    with httpx.Client(headers={"User-Agent": openmeteo.UA}, timeout=60) as http:
        r = http.get(FORECAST_URL, params=params)
        r.raise_for_status()
    df = pd.DataFrame(r.json()["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    return df


def summit_conditions(target: date, sunrise: datetime) -> dict:
    """Summit temperature, wind and rain chance at the sunrise hour, for 'what to carry' only (not a model input)."""
    try:
        df = _summit_hourly(target, ["temperature_2m", "wind_speed_10m", "precipitation_probability"],
                            "Asia/Kolkata")
        row = df[df["time"].dt.hour == sunrise.hour].iloc[0]
        return {"summit_temp_c": round(float(row["temperature_2m"])), "wind_kmh": round(float(row["wind_speed_10m"])),
                "rain_chance_pct": round(float(row["precipitation_probability"]))}
    except (httpx.HTTPError, IndexError, KeyError, ValueError, TypeError):
        return {"summit_temp_c": None, "wind_kmh": None, "rain_chance_pct": None}


def summit_rh850(day: date) -> float | None:
    """850 hPa humidity at 06:30 IST (01 UTC) on `day`, for grading. Model-derived, like the training labels."""
    try:
        df = _summit_hourly(day, ["relative_humidity_850hPa"], "UTC")
        v = df.loc[df["time"].dt.hour == 1, "relative_humidity_850hPa"].iloc[0]
        return None if pd.isna(v) else float(v)
    except (httpx.HTTPError, IndexError, KeyError):
        return None
