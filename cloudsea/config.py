"""Fixed facts about the place. Sources are in BUILD_LOG.md (2026-10-10 Phase 0 entries)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class Point:
    name: str
    lat: float
    lon: float
    elev_m: float


SUMMIT = Point("Nandi Hills summit", 13.3702, 77.6835, 1478)    # Wikipedia; PeakVisor 1479 m
VOBL = Point("Kempegowda Intl Airport (VOBL)", 13.1979, 77.7063, 915)  # AIP India: 3003 ft
PLAINS = Point("Plains south of Nandi", 13.25, 77.68, 900)       # fog predictors: grid cell below the hill

SUMMIT_ABOVE_VOBL_FT = 1847          # (1478 - 915) m
SUMMIT_ABOVE_PLAINS_M = 560          # observer height for sunrise over the plains horizon
DAWN_START, DAWN_END = time(5, 30), time(7, 30)   # IST window used for labels and grading
CALL_TIME = time(20, 30)             # the nightly call goes live at 8:30 PM IST

# Season used for evaluation: the fog months. Cloud seas outside these months are mostly monsoon stratus.
SEASON_MONTHS = (10, 11, 12, 1, 2)
