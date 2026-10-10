"""Summit photo uploads: the server-side checks and a re-encode that keeps pixels and nothing else.

The browser already resizes and checks the photo (docs/API.md). The server checks again because a client can
send anything, and re-encodes so that no EXIF, GPS, ICC profile or comment survives, whatever arrived.
"""
from __future__ import annotations

import io
from datetime import date, datetime, time, timedelta

from PIL import Image, ImageOps, UnidentifiedImageError

from cloudsea.config import IST

MAX_BYTES = 250 * 1024
MAX_EDGE = 1280
MAX_PIXELS = 40_000_000           # refuse decompression bombs before decoding
FORMATS = {"JPEG", "PNG", "WEBP"}
DAWN_FROM, DAWN_TO = time(5, 0), time(8, 30)   # IST, inclusive
MAX_AGE = timedelta(hours=36)
FUTURE_TOLERANCE = timedelta(minutes=5)        # phone clocks drift
MAX_DISTANCE_KM = 3.0                          # from the summit, when the photo has GPS
JPEG_QUALITY = 85


class PhotoError(ValueError):
    """A rejected upload. `status` is the HTTP status; the message is shown to the person."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    v = value.strip().lower()
    if v in ("true", "1", "yes", "on"):
        return True
    if v in ("false", "0", "no", "off"):
        return False
    raise PhotoError(f"Expected true or false, got {value!r}.")


def parse_taken_at(value: str | None) -> datetime:
    """An ISO timestamp with a UTC offset (or Z). A time without an offset is ambiguous, so it is refused."""
    if not value:
        raise PhotoError("The photo has no capture time. Use the original photo from your camera.")
    try:
        ts = datetime.fromisoformat(value.strip())
    except ValueError:
        raise PhotoError("The capture time isn't a valid timestamp.") from None
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise PhotoError("The capture time needs a timezone offset, like +05:30.")
    return ts


def check_taken_at(taken_at: datetime, now: datetime | None = None) -> date:
    """Check the dawn window (05:00-08:30 IST), age (36 h) and clock skew; return the IST date of the photo."""
    now = now or datetime.now(IST)
    local = taken_at.astimezone(IST)
    if taken_at > now + FUTURE_TOLERANCE:
        raise PhotoError("The photo's capture time is in the future. Check your camera's clock.")
    if now - taken_at > MAX_AGE:
        raise PhotoError("This photo is more than 36 hours old. We only take photos from the latest sunrise.")
    if not (DAWN_FROM <= local.time() <= DAWN_TO):
        raise PhotoError(f"This photo was taken at {local:%H:%M} IST. "
                         "We only take photos from between 05:00 and 08:30 IST.")
    return local.date()


def check_distance(gps_present: bool, distance_km: float | None) -> None:
    """Photos with GPS must be within 3 km of the summit. Photos without GPS are taken on trust."""
    if not gps_present or distance_km is None:
        return
    if distance_km != distance_km or distance_km < 0:      # NaN or negative
        raise PhotoError("The distance from the summit isn't valid.")
    if distance_km > MAX_DISTANCE_KM:
        raise PhotoError(f"This photo was taken {distance_km:.1f} km from the summit. "
                         "We only take photos from the top of Nandi Hills.")


def parse_distance(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        raise PhotoError("The distance from the summit isn't a number.") from None


def reencode(data: bytes) -> bytes:
    """Decode, apply the EXIF orientation, drop all metadata, convert to RGB, fit within 1280 px, JPEG q85."""
    if len(data) > MAX_BYTES:
        raise PhotoError("This photo is larger than 250 KB. Try again from the app, which shrinks it first.", 413)
    try:
        im = Image.open(io.BytesIO(data))
        if im.format not in FORMATS:
            raise PhotoError("Please upload a JPEG, PNG or WebP photo.")
        w, h = im.size
        if w * h > MAX_PIXELS:
            raise PhotoError("This image is too large to process.")
        im.load()
        im = ImageOps.exif_transpose(im)
    except PhotoError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, SyntaxError):
        raise PhotoError("That file doesn't look like a photo we can read.") from None

    if im.mode not in ("RGB", "L"):
        if "A" in im.getbands() or im.mode == "P":
            rgba = im.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.getchannel("A"))
            im = bg
        else:
            im = im.convert("RGB")
    im = im.convert("RGB")
    if max(im.size) > MAX_EDGE:
        im.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)

    # A fresh image carries only pixels: no info dict, so no exif, icc_profile or comment can reach the encoder.
    clean = Image.frombytes("RGB", im.size, im.tobytes())
    out = io.BytesIO()
    clean.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()
