"""Upload checks and the metadata-stripping re-encode. No database needed."""
from __future__ import annotations

import io
from datetime import datetime

import pytest
from PIL import Image, ImageDraw

from cloudsea import photos
from cloudsea.config import IST

GPS_IFD, EXIF_IFD = 0x8825, 0x8769


def jpeg_with_metadata(size=(2400, 1600), orientation: int = 6) -> bytes:
    im = Image.new("RGB", size, (90, 110, 170))
    ImageDraw.Draw(im).rectangle((0, 0, size[0] // 4, size[1] // 8), fill=(250, 240, 200))   # marks top-left
    exif = Image.Exif()
    exif[0x010F] = "TestCam"                    # Make
    exif[0x0112] = orientation                  # 6 = rotate 90° clockwise to display
    exif[0x0132] = "2026:10:11 06:12:00"        # DateTime
    exif.get_ifd(EXIF_IFD)[0x9003] = "2026:10:11 06:12:00"     # DateTimeOriginal
    gps = exif.get_ifd(GPS_IFD)
    gps.update({1: "N", 2: (13.0, 22.0, 12.7), 3: "E", 4: (77.0, 41.0, 0.6)})
    out = io.BytesIO()
    im.save(out, "JPEG", exif=exif, icc_profile=b"fake icc profile", comment=b"secret note", quality=90)
    return out.getvalue()


def test_fixture_really_has_gps_and_capture_time():
    src = Image.open(io.BytesIO(jpeg_with_metadata()))
    exif = src.getexif()
    assert exif.get_ifd(GPS_IFD)[1] == "N"
    assert exif.get_ifd(EXIF_IFD)[0x9003] == "2026:10:11 06:12:00"


def test_reencode_strips_all_metadata_and_downscales():
    src = jpeg_with_metadata()
    assert len(src) <= photos.MAX_BYTES and b"Exif\x00\x00" in src
    out = photos.reencode(src)
    im = Image.open(io.BytesIO(out))
    assert im.format == "JPEG" and im.mode == "RGB"
    assert len(im.getexif()) == 0
    assert b"Exif\x00\x00" not in out
    assert b"secret note" not in out and b"fake icc profile" not in out
    assert "icc_profile" not in im.info and "comment" not in im.info
    assert max(im.size) <= 1280


def test_reencode_applies_orientation_before_dropping_it():
    out = Image.open(io.BytesIO(photos.reencode(jpeg_with_metadata(size=(2400, 1600), orientation=6))))
    w, h = out.size
    assert h > w                                 # landscape pixels, rotated to portrait for display
    assert out.getpixel((w - 5, 5))[0] > 200     # the bright top-left mark is now top-right


def test_small_png_with_alpha_becomes_rgb_jpeg():
    im = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    out = Image.open(io.BytesIO(photos.reencode(buf.getvalue())))
    assert out.format == "JPEG" and out.mode == "RGB" and out.size == (300, 200)


def test_reencode_rejects_non_images_and_big_files():
    with pytest.raises(photos.PhotoError) as e:
        photos.reencode(b"not an image at all")
    assert e.value.status == 400
    with pytest.raises(photos.PhotoError) as e:
        photos.reencode(b"\xff" * (photos.MAX_BYTES + 1))
    assert e.value.status == 413
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    with pytest.raises(photos.PhotoError):
        photos.reencode(gif.getvalue())


# --- the dawn window ------------------------------------------------------------------------------------

NOW = datetime(2026, 10, 11, 20, 0, tzinfo=IST)


def check(ts: str, now: datetime = NOW):
    return photos.check_taken_at(photos.parse_taken_at(ts), now)


@pytest.mark.parametrize("ts", ["2026-10-11T05:00:00+05:30", "2026-10-11T08:30:00+05:30",
                                "2026-10-11T06:12:00+05:30"])
def test_inside_dawn_window(ts):
    assert check(ts).isoformat() == "2026-10-11"


@pytest.mark.parametrize("ts", ["2026-10-11T04:59:59+05:30", "2026-10-11T08:30:01+05:30",
                                "2026-10-11T12:00:00+05:30", "2026-10-11T02:00:00+05:30"])
def test_outside_dawn_window(ts):
    with pytest.raises(photos.PhotoError, match="05:00 and 08:30"):
        check(ts)


def test_other_offsets_are_converted_to_ist():
    assert check("2026-10-11T00:42:00Z").isoformat() == "2026-10-11"             # 06:12 IST
    assert check("2026-10-11T00:42:00+00:00").isoformat() == "2026-10-11"
    assert check("2026-10-10T20:42:00-04:00").isoformat() == "2026-10-11"        # 06:12 IST next day
    with pytest.raises(photos.PhotoError):
        check("2026-10-11T06:12:00+00:00")                                      # 11:42 IST
    # The same wall-clock time labelled UTC is a different instant, outside the window.
    with pytest.raises(photos.PhotoError):
        check("2026-10-11T06:12:00Z")


def test_edges_in_ist_when_given_in_utc():
    assert check("2026-10-10T23:30:00Z").isoformat() == "2026-10-11"             # 05:00 IST
    assert check("2026-10-11T03:00:00Z").isoformat() == "2026-10-11"             # 08:30 IST
    with pytest.raises(photos.PhotoError):
        check("2026-10-10T23:29:59Z")


def test_timestamp_without_offset_is_refused():
    with pytest.raises(photos.PhotoError, match="timezone"):
        photos.parse_taken_at("2026-10-11T06:12:00")
    with pytest.raises(photos.PhotoError):
        photos.parse_taken_at("yesterday at dawn")
    with pytest.raises(photos.PhotoError):
        photos.parse_taken_at(None)


def test_future_is_refused_with_five_minutes_of_clock_slack():
    now = datetime(2026, 10, 11, 5, 50, tzinfo=IST)
    with pytest.raises(photos.PhotoError, match="future"):
        check("2026-10-11T06:00:00+05:30", now)
    now = datetime(2026, 10, 11, 5, 56, tzinfo=IST)
    assert check("2026-10-11T06:00:00+05:30", now).isoformat() == "2026-10-11"


def test_older_than_36_hours_is_refused():
    now = datetime(2026, 10, 12, 19, 0, tzinfo=IST)
    assert check("2026-10-11T08:00:00+05:30", now).isoformat() == "2026-10-11"   # 35 h
    with pytest.raises(photos.PhotoError, match="36 hours"):
        check("2026-10-11T06:00:00+05:30", now)                                 # 37 h


# --- distance and form parsing ------------------------------------------------------------------------

def test_gps_distance_rule():
    photos.check_distance(True, 0.4)
    photos.check_distance(True, 3.0)
    photos.check_distance(True, None)          # GPS flag without a distance: nothing to check
    photos.check_distance(False, 40.0)         # no GPS: the distance isn't trusted or used
    with pytest.raises(photos.PhotoError, match="km from the summit"):
        photos.check_distance(True, 3.2)
    with pytest.raises(photos.PhotoError):
        photos.check_distance(True, float("nan"))
    with pytest.raises(photos.PhotoError):
        photos.parse_distance("far")
    assert photos.parse_distance("") is None and photos.parse_distance("1.5") == 1.5


def test_parse_bool():
    assert photos.parse_bool("true") is True and photos.parse_bool("False") is False
    assert photos.parse_bool(None) is False and photos.parse_bool("", default=True) is True
    with pytest.raises(photos.PhotoError):
        photos.parse_bool("maybe")
