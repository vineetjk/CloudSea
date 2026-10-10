"""Sunrise, leave-by times and what to carry: the practical half of the call.

Drive times are free-flow estimates from OSRM (open-source routing on OpenStreetMap data, computed
2026-10-10 from each area's centre to the summit). Roads are close to empty before 4 AM, so free-flow is a
fair estimate, but it is not live traffic. Electronics City is still to be confirmed by a real drive.
Every leave-by time adds a safety buffer and aims to arrive well before sunrise; nothing here should ever
encourage driving fast.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from astral import Observer
from astral.sun import sun

from cloudsea.config import IST, SUMMIT, SUMMIT_ABOVE_PLAINS_M

BUFFER_MIN = 20                 # added to every drive
ARRIVE_BEFORE_SUNRISE_MIN = 30  # parking, the walk up and finding a spot
GATE = {"opens": "06:00", "verified": False,
        "note": "Gate time not yet verified. Check before you go."}

# (key, label, OSRM free-flow minutes, km). Source: router.project-osrm.org, 2026-10-10.
AREAS = [
    ("electronics-city", "Electronics City", 94, 79.3),
    ("hsr-layout", "HSR Layout", 83, 76.5),
    ("koramangala", "Koramangala", 77, 71.3),
    ("jayanagar", "Jayanagar", 80, 67.5),
    ("indiranagar", "Indiranagar", 72, 66.4),
    ("whitefield", "Whitefield", 68, 62.4),
    ("majestic", "Majestic", 72, 60.6),
    ("hebbal", "Hebbal", 65, 54.4),
    ("yelahanka", "Yelahanka", 55, 48.7),
]
DEFAULT_AREA = "electronics-city"


def sun_times(day: date) -> dict:
    """Sunrise and first light (civil dawn) seen from the summit, which sits ~560 m above the plains."""
    obs = Observer(latitude=SUMMIT.lat, longitude=SUMMIT.lon, elevation=SUMMIT_ABOVE_PLAINS_M)
    s = sun(obs, date=day, tzinfo=IST)
    return {"sunrise": s["sunrise"], "first_light": s["dawn"]}


def _round_down(t: datetime, minutes: int = 5) -> datetime:
    return t - timedelta(minutes=t.minute % minutes, seconds=t.second, microseconds=t.microsecond)


def leave_by(sunrise: datetime) -> list[dict]:
    out = []
    for key, label, osrm_min, km in AREAS:
        drive = 5 * math.ceil(osrm_min / 5)
        t = _round_down(sunrise - timedelta(minutes=ARRIVE_BEFORE_SUNRISE_MIN + drive + BUFFER_MIN))
        out.append({"area": key, "label": label, "drive_minutes": drive, "buffer_minutes": BUFFER_MIN,
                    "leave_by": f"{t:%H:%M}", "km": km})
    return out


def carry(summit_temp_c: float | None, rain_chance_pct: float | None) -> list[str]:
    items = []
    if summit_temp_c is not None:
        t = round(summit_temp_c)
        items.append(f"Warm layer (summit about {t}°C)" if t < 18 else f"Light jacket (summit about {t}°C)")
    if rain_chance_pct is not None and rain_chance_pct >= 30:
        items.append("Rain jacket")
    items += ["Water", "Torch for the walk from parking"]
    return items
