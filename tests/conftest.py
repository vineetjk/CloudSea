from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from cloudsea.config import IST


def make_call(day: date, verdict: str = "SKIP", p: float = 0.08) -> dict:
    """A call row as the nightly job would write it."""
    return {
        "date": day,
        "issued_at": datetime.combine(day - timedelta(days=1), time(20, 30, 12), IST),
        "verdict": verdict,
        "probability": p,
        "sunrise": "06:09",
        "first_light": "05:46",
        "text": f"{verdict} for Sunday. {round(p * 100)}% chance of a cloud sea at Nandi. Sunrise 06:09. "
                "A forecast, not a guarantee.",
        "text_source": "gemma",
        "text_kn": None,
        "text_hi": None,
        "carry": ["Light jacket (summit about 17°C)", "Water"],
        "conditions": {"summit_temp_c": 17, "wind_kmh": 9, "rain_last_24h": False},
        "leave_by": [{"area": "electronics-city", "label": "Electronics City", "drive_minutes": 100,
                      "buffer_minutes": 20, "leave_by": "03:39"}],
        "gate": {"opens": "06:00", "verified": False, "note": "Gate time not yet verified. Check before you go."},
        "model": {"forecaster": "TabPFN v3.5 (Prior Labs)", "writer": "Gemma 4 E2B", "trained_through": "2025-09-30"},
        "features": {"eve_spread_c": 1.5, "eve_ceiling_kft": float("nan")},
        "thresholds": {"skip_below": 0.15, "go_at": 0.55},
    }


@pytest.fixture
def sample_call() -> dict:
    return make_call(date(2026, 10, 11))


@pytest.fixture
def new_call():
    """The `make_call(day, verdict, p)` factory, for tests that need several calls."""
    return make_call
