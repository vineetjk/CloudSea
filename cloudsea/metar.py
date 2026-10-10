"""Load IEM METAR CSVs and summarise each dawn (05:30-07:30 IST) and evening at VOBL."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from cloudsea.config import DAWN_END, DAWN_START, SUMMIT_ABOVE_VOBL_FT

MILE_M = 1609.344
KT_KMH = 1.852
PRECIP_CODES = ("RA", "DZ", "TS", "SH")
LAYERS = range(1, 5)
VIS_LOW_M = 1450  # "below 1500 m": reported 1400 m or less
VIS_FOG_M = 950   # "below 1000 m": reported 900 m or less (fog by definition)


COLS = ["valid", "tmpf", "dwpf", "relh", "drct", "sknt", "vsby", "wxcodes", "metar"] + \
       [f"skyc{i}" for i in LAYERS] + [f"skyl{i}" for i in LAYERS]


def load(raw_dir: Path) -> pd.DataFrame:
    """The whole archive: one row per report with UTC and IST times and metric units."""
    frames = [pd.read_csv(p, usecols=COLS, dtype={"wxcodes": str, "metar": str}, low_memory=False)
              for p in sorted(raw_dir.glob("*.csv"))]
    return parse(pd.concat(frames, ignore_index=True))


def from_csv_bytes(body: bytes) -> pd.DataFrame:
    """Reports fetched live by `iem.fetch_range`."""
    import io
    raw = pd.read_csv(io.BytesIO(body), usecols=COLS, dtype={"wxcodes": str, "metar": str}, na_values=[""])
    return parse(raw)


def parse(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["utc"] = pd.to_datetime(df["valid"], utc=True)
    df["ist"] = df["utc"].dt.tz_convert("Asia/Kolkata")
    df["date"] = df["ist"].dt.date
    df["temp_c"] = (df["tmpf"] - 32) / 1.8
    df["dew_c"] = (df["dwpf"] - 32) / 1.8
    df["spread_c"] = df["temp_c"] - df["dew_c"]
    df["wind_kmh"] = df["sknt"] * KT_KMH
    df["vis_m"] = df["vsby"] * MILE_M
    df["wxcodes"] = df["wxcodes"].fillna("")
    toks = df["wxcodes"].str.split()
    df["fog"] = toks.apply(lambda ts: any("FG" in t and not t.startswith("VC") for t in ts))
    df["mist"] = toks.apply(lambda ts: any(t.lstrip("+-").endswith("BR") for t in ts))
    df["precip"] = toks.apply(lambda ts: any(c in t for t in ts for c in PRECIP_CODES))
    ceil = np.full(len(df), np.nan)
    low_any = np.full(len(df), np.nan)
    deck_near_summit = np.zeros(len(df), dtype=bool)
    for i in LAYERS:
        cover, base = df[f"skyc{i}"].fillna(""), df[f"skyl{i}"]
        is_ceiling = cover.isin(["BKN", "OVC", "VV"]) & base.notna()
        is_layer = cover.isin(["SCT", "BKN", "OVC", "VV"]) & base.notna()
        ceil = np.where(is_ceiling, np.fmin(ceil, base), ceil)
        low_any = np.where(is_layer, np.fmin(low_any, base), low_any)
        # A broken/overcast deck from just below summit height up to 5000 ft: the summit is in it or under it.
        deck_near_summit |= (is_ceiling & base.between(1500, 5000)).to_numpy()
    df["ceiling_ft"] = ceil
    df["lowest_layer_ft"] = low_any
    df["deck_near_summit"] = deck_near_summit
    df["has_sky"] = df["skyc1"].notna()
    return df.sort_values("utc").reset_index(drop=True)


def dawn_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per local date: what the airport saw between 05:30 and 07:30 IST."""
    t = df["ist"].dt.time
    d = df[(t >= DAWN_START) & (t <= DAWN_END)].copy()
    # IEM stores visibility in statute miles, so a reported 1500 m comes back as 1497 m: compare with margins.
    d["low_layer"] = d["fog"] | (d["vis_m"] < VIS_LOW_M) | (d["ceiling_ft"] <= 1000)
    d["fog_or_vis1k"] = d["fog"] | (d["vis_m"] < VIS_FOG_M)
    d["layer_below_summit"] = d["lowest_layer_ft"] < SUMMIT_ABOVE_VOBL_FT
    g = d.groupby("date")
    out = pd.DataFrame({
        "n_dawn": g.size(),
        "n_with_sky": g["has_sky"].sum(),
        "fog_reports": g["fog"].sum(),
        "fog_or_vis1k_reports": g["fog_or_vis1k"].sum(),
        "low_layer_reports": g["low_layer"].sum(),
        "mist_reports": g["mist"].sum(),
        "below_summit_reports": g["layer_below_summit"].sum(),
        "deck_near_summit_reports": g["deck_near_summit"].sum(),
        "precip_reports": g["precip"].sum(),
        "min_vis_m": g["vis_m"].min(),
        "min_ceiling_ft": g["ceiling_ft"].min(),
        "min_spread_c": g["spread_c"].min(),
        "mean_wind_kmh": g["wind_kmh"].mean(),
        "metars": g["metar"].apply(lambda s: " | ".join(x.split(" ", 2)[2][:70] for x in s.astype(str))),
    })
    out.index = pd.to_datetime(out.index)
    return out
