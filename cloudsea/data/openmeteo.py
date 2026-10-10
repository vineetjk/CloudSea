"""Open-Meteo downloads.

Two different uses, kept apart on purpose:

* `label`: the Historical Forecast API (first hours of each model run, stitched together). Close to an
  analysis, so it is fine for judging after the fact what the air at summit height was like at dawn
  (850 hPa humidity), and NOT used as a forecast feature (it would leak skill the 8:30 PM call never has).
* `runs`: the Single Runs API, one archived ECMWF IFS run per day. The 00 UTC run is out by ~08 UTC, so it
  is genuinely available at 20:30 IST; its +24-26 h values are tomorrow's dawn. Training and the live
  nightly job both use exactly this run, so features match (no train/serve skew).

Weather data by Open-Meteo.com (CC BY 4.0).
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd

from cloudsea.config import PLAINS, SUMMIT

UA = "CloudSea/0.1 (https://github.com/vineetjk/CloudSea) python-httpx"
HF_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
RUNS_URL = "https://single-runs-api.open-meteo.com/v1/forecast"

LABEL_VARS = ["relative_humidity_850hPa", "relative_humidity_900hPa", "relative_humidity_925hPa",
              "cloud_cover_low", "cloud_cover_mid", "temperature_850hPa", "temperature_2m", "dew_point_2m"]
LABEL_START = date(2021, 3, 23)  # best_match pressure-level fields start here at our point

RUN_VARS = ["temperature_2m", "dew_point_2m", "relative_humidity_2m", "wind_speed_10m", "cloud_cover",
            "cloud_cover_low", "visibility", "boundary_layer_height", "precipitation"]
RUNS_START = date(2024, 3, 14)   # first archived ecmwf_ifs single run
RUN_MODEL = "ecmwf_ifs"
RUN_HOURS = 36


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": UA}, timeout=120, follow_redirects=True)


def _get(http: httpx.Client, url: str, params: dict, attempts: int = 4) -> dict:
    for attempt in range(attempts):
        try:
            r = http.get(url, params=params)
        except httpx.TransportError:  # timeouts and dropped connections happen on long backfills
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5 * (attempt + 1))
            continue
        data = r.json()
        if r.status_code != 200 or data.get("error"):
            raise RuntimeError(f"{url} {params.get('run', '')}: {data.get('reason', r.status_code)}")
        return data
    raise RuntimeError(f"{url}: gave up after {attempts} attempts")


def _hourly_frame(data: dict) -> pd.DataFrame:
    df = pd.DataFrame(data["hourly"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def fetch_label_atmosphere(out: Path, end: date | None = None) -> pd.DataFrame:
    """Hourly summit-column fields from the Historical Forecast API, LABEL_START..end, one request per year."""
    end = end or date.today() - timedelta(days=1)
    frames = []
    with _client() as http:
        for year in range(LABEL_START.year, end.year + 1):
            start = max(LABEL_START, date(year, 1, 1))
            stop = min(end, date(year, 12, 31))
            data = _get(http, HF_URL, {
                "latitude": SUMMIT.lat, "longitude": SUMMIT.lon, "hourly": ",".join(LABEL_VARS),
                "models": "best_match", "timezone": "UTC",
                "start_date": start.isoformat(), "end_date": stop.isoformat()})
            frames.append(_hourly_frame(data))
            print(f"label atmosphere {start}..{stop}: {len(frames[-1])} hours", flush=True)
            time.sleep(1)
    df = pd.concat(frames, ignore_index=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return df


def fetch_run(http: httpx.Client, run_day: date, run_hour: int = 0, point=PLAINS) -> dict:
    return _get(http, RUNS_URL, {
        "latitude": point.lat, "longitude": point.lon, "models": RUN_MODEL,
        "run": f"{run_day.isoformat()}T{run_hour:02d}:00", "hourly": ",".join(RUN_VARS),
        "forecast_hours": RUN_HOURS, "timezone": "UTC"})


def fetch_runs(cache: Path, start: date = RUNS_START, end: date | None = None, workers: int = 4) -> None:
    """Download and cache one 00 UTC run per day. Cached days are skipped, so reruns only fetch new days."""
    end = end or date.today()
    cache.mkdir(parents=True, exist_ok=True)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    todo = [d for d in days if not (cache / f"{d.isoformat()}.json").exists()]
    print(f"single runs: {len(days)} days, {len(todo)} to fetch", flush=True)

    def one(d: date) -> str:
        with _client() as http:
            try:
                data = fetch_run(http, d)
            except RuntimeError as err:
                return f"{d}: {err}"
        (cache / f"{d.isoformat()}.json").write_text(json.dumps(data))
        return ""

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, msg in enumerate(pool.map(one, todo), 1):
            if msg:
                print("  missing", msg, flush=True)
            if i % 100 == 0:
                print(f"  {i}/{len(todo)}", flush=True)


def load_runs(cache: Path) -> pd.DataFrame:
    """All cached runs as one long frame with columns run_day, time (UTC), lead_h and RUN_VARS."""
    rows = []
    for path in sorted(cache.glob("*.json")):
        df = _hourly_frame(json.loads(path.read_text()))
        run_day = date.fromisoformat(path.stem)
        df["run_day"] = pd.Timestamp(run_day)
        df["lead_h"] = ((df["time"] - pd.Timestamp(run_day, tz="UTC")) / pd.Timedelta(hours=1)).astype(int)
        rows.append(df)
    return pd.concat(rows, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Download Open-Meteo data for labels and forecast features")
    ap.add_argument("what", choices=["label", "runs", "both"])
    args = ap.parse_args()
    from cloudsea.settings import DATA_DIR
    if args.what in ("label", "both"):
        fetch_label_atmosphere(DATA_DIR / "interim" / "label_atmosphere.parquet")
    if args.what in ("runs", "both"):
        fetch_runs(DATA_DIR / "raw" / "openmeteo" / f"{RUN_MODEL}_00z")


if __name__ == "__main__":
    main()
