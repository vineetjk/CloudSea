"""What counts as "a cloud sea at Nandi at sunrise", built from things we can check after the fact.

Inputs per date:
* the airport's dawn reports (05:30-07:30 IST, usually 5 of them), summarised by `metar.dawn_summary`
* humidity at summit height (850 hPa) and in the fog layer (900 hPa) at 06:30 IST, from Open-Meteo's
  Historical Forecast API (model-derived, not observed)

The airport (915 m) is 15 km south-east of the summit (1478 m) and 563 m lower. It can see a fog or stratus
layer at or near the ground, and a cloud deck near summit height. It cannot see how thick the layer is.
The 850 hPa humidity stands in for "is the summit above the cloud or inside it".

Three candidate definitions, from broad to strict. The chosen one is `LABEL`, one line to change.
"""
from __future__ import annotations

import pandas as pd

MIN_DAWN_REPORTS = 3
MIN_HITS = 2  # a condition must appear in at least this many dawn reports, not one blip


def _usable(d: pd.DataFrame) -> pd.Series:
    return (d["n_dawn"] >= MIN_DAWN_REPORTS) & (d["n_with_sky"] >= MIN_DAWN_REPORTS)


def low_layer(d: pd.DataFrame) -> pd.Series:
    """A: the airport sits under a low layer at dawn (fog, visibility < 1500 m, or a ceiling at or below
    1000 ft), in at least two reports, without rain."""
    hit = (d["low_layer_reports"] >= MIN_HITS) & (d["precip_reports"] == 0)
    return hit.where(_usable(d))


def low_layer_summit_clear(d: pd.DataFrame, rh850_max: float = 90.0) -> pd.Series:
    """B: A, and the air at summit height is not saturated (850 hPa RH below 90% at 06:30 IST), so the summit
    is more likely above the layer than inside it."""
    hit = low_layer(d).astype("boolean") & (d["rh850"] < rh850_max)
    return hit.where(_usable(d) & d["rh850"].notna())


def strict(d: pd.DataFrame, rh850_max: float = 85.0) -> pd.Series:
    """C: fog or visibility under 1000 m in at least two dawn reports, no broken/overcast deck between 1500
    and 5000 ft (which would put the summit in cloud or the sun behind it), no rain, and 850 hPa RH < 85%."""
    hit = ((d["fog_or_vis1k_reports"] >= MIN_HITS) & (d["deck_near_summit_reports"] == 0)
           & (d["precip_reports"] == 0) & (d["rh850"] < rh850_max))
    return hit.where(_usable(d) & d["rh850"].notna())


DEFINITIONS = {"A_low_layer": low_layer, "B_low_layer_summit_clear": low_layer_summit_clear, "C_strict": strict}
LABEL = "B_low_layer_summit_clear"


def attach_atmosphere(dawn: pd.DataFrame, atmos: pd.DataFrame) -> pd.DataFrame:
    """Add 06:30 IST (01 UTC) summit-column humidity to the dawn summary."""
    a = atmos[atmos["time"].dt.hour == 1].copy()
    a["date"] = pd.to_datetime(a["time"].dt.tz_convert("Asia/Kolkata").dt.date)
    a = a.set_index("date")[["relative_humidity_850hPa", "relative_humidity_900hPa", "cloud_cover_low"]]
    a.columns = ["rh850", "rh900", "model_low_cloud"]
    return dawn.join(a, how="left")


def label(dawn_with_atmos: pd.DataFrame, name: str = LABEL) -> pd.Series:
    """1.0 = cloud sea likely, 0.0 = not, NaN = can't tell (too few reports or no atmosphere data)."""
    return DEFINITIONS[name](dawn_with_atmos).astype("Float64")
