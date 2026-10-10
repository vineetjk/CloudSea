"""Share cards (Open Graph 1200x630, story 1080x1920) and the small share page with Open Graph tags.

Cards are drawn with Pillow in a dawn palette. The cloud layer below the horizon gets denser with the
forecast probability, so a SKIP card doesn't show a sea that isn't forecast.

Font: Inter (SIL Open Font License 1.1, cloudsea/assets/Inter-OFL.txt), subset to Latin to keep it small.
"""
from __future__ import annotations

import html
import io
import random
import re
import threading
from collections import OrderedDict
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS = Path(__file__).resolve().parent / "assets"
BOLD = ASSETS / "Inter-Bold.ttf"
REGULAR = ASSETS / "Inter-Regular.ttf"

OG_SIZE = (1200, 630)
STORY_SIZE = (1080, 1920)
FOOTER = "CloudSea · forecast, not a guarantee"
DEFAULT_DESCRIPTION = "Tomorrow's sunrise call for Nandi Hills"

# Night indigo at the top, through violet and rose, to a warm horizon.
SKY = [(0.00, (14, 16, 46)), (0.40, (42, 38, 96)), (0.66, (104, 66, 128)), (0.84, (214, 120, 112)),
       (1.00, (252, 196, 128))]
LAND = (30, 30, 62)
RIDGE = (12, 12, 30)
CLOUD = (244, 238, 246)
SUN = (255, 220, 160)
WHITE = (255, 255, 255)
SOFT = (222, 218, 244)
MUTED = (190, 184, 226)
VERDICT_COLOR = {"GO": (255, 214, 140), "MAYBE": (255, 200, 170), "SKIP": (232, 230, 250)}


# --- small formatting helpers (also used by the API) ---------------------------------------------------

def as_date(v: date | datetime | str) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def pct(p: float) -> int:
    return int(round(float(p) * 100))


def day_short(d: date) -> str:
    return f"{d:%a} {d.day} {d:%b}"          # Sun 11 Oct


def day_long(d: date) -> str:
    return f"{d:%A} {d.day} {d:%b}"          # Sunday 11 Oct


def og_title(call: dict) -> str:
    return f"{call['verdict']} · {pct(call['probability'])}% cloud sea · {day_short(as_date(call['date']))}"


def og_description(call: dict | None) -> str:
    text = (call or {}).get("text") or ""
    m = re.match(r"\s*(.+?[.!?])(?=\s|$)", text, re.S)
    first = (m.group(1) if m else text).strip()
    return first or DEFAULT_DESCRIPTION


# --- drawing -------------------------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def _fit(draw: ImageDraw.ImageDraw, text: str, path: Path, size: int, max_w: int) -> ImageFont.FreeTypeFont:
    """The largest font up to `size` at which `text` fits in `max_w` pixels."""
    while size > 12:
        font = _font(path, size)
        if draw.textlength(text, font=font) <= max_w:
            return font
        size -= 2
    return _font(path, size)


def _lerp(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b, strict=True))


def _sky(w: int, h: int) -> Image.Image:
    col = Image.new("RGB", (1, h))
    px = col.load()
    for y in range(h):
        t = y / max(1, h - 1)
        for (t0, c0), (t1, c1) in zip(SKY[:-1], SKY[1:], strict=True):
            if t <= t1:
                px[0, y] = _lerp(c0, c1, (t - t0) / (t1 - t0))
                break
    return col.resize((w, h), Image.Resampling.NEAREST)


def _scene(size: tuple[int, int], horizon: int, p: float) -> Image.Image:
    """Sky gradient, a rising sun, land below the horizon, a cloud layer whose density follows p, a ridge."""
    w, h = size
    img = _sky(w, horizon)
    canvas = Image.new("RGB", (w, h), LAND)
    canvas.paste(img, (0, 0))
    canvas = canvas.convert("RGBA")
    rng = random.Random(7)
    scale = 4                                   # draw soft layers small, blur, scale up: fast and smooth
    sw, sh, sy = w // scale, h // scale, horizon // scale

    d = ImageDraw.Draw(canvas)
    sun_r = int(min(w, h) * 0.06)
    cx = int(w * 0.72)
    d.ellipse((cx - sun_r, horizon - sun_r, cx + sun_r, horizon + sun_r), fill=(*SUN, 255))
    d.rectangle((0, horizon, w, h), fill=(*LAND, 255))

    # Clouds: a haze over the whole band plus soft blobs; both get denser with p.
    clouds = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    c = ImageDraw.Draw(clouds)
    alpha = int(40 + 200 * max(0.0, min(1.0, float(p))))
    band = sh - sy
    c.rectangle((0, sy, sw, sh), fill=(*CLOUD, alpha // 2))
    for _ in range(40):
        x = rng.uniform(-0.1, 1.1) * sw
        y = sy + rng.uniform(0.0, 0.7) * band
        rx, ry = rng.uniform(0.08, 0.22) * sw, rng.uniform(0.05, 0.14) * band
        c.ellipse((x - rx, y - ry, x + rx, y + ry), fill=(*CLOUD, alpha))
    clouds = clouds.filter(ImageFilter.GaussianBlur(max(2, band * 0.06)))
    clouds.paste((0, 0, 0, 0), (0, 0, sw, sy))          # nothing above the horizon
    canvas.alpha_composite(clouds.resize((w, h), Image.Resampling.BILINEAR))

    # Warm glow around the sun, over sky and cloud tops alike, which also softens the horizon line.
    glow = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    sx, r = int(sw * 0.72), int(min(sw, sh) * 0.22)
    g.ellipse((sx - r * 2, sy - r, sx + r * 2, sy + r), fill=(*SUN, 60))
    g.ellipse((sx - r, sy - r // 2, sx + r, sy + r // 2), fill=(*SUN, 120))
    g.rectangle((0, sy - 1, sw, sy + 1), fill=(*SKY[-1][1], 110))
    glow = glow.filter(ImageFilter.GaussianBlur(r * 0.6)).resize((w, h), Image.Resampling.BILINEAR)
    canvas.alpha_composite(glow)

    d = ImageDraw.Draw(canvas)
    ridge_top = h - int((h - horizon) * 0.45)
    pts = [(0, h), (0, ridge_top), (int(w * 0.18), ridge_top - int(h * 0.012)), (int(w * 0.38), ridge_top + int(h * 0.01)),
           (int(w * 0.55), ridge_top + int(h * 0.04)), (int(w * 0.68), h - int((h - horizon) * 0.18)), (w, h - int((h - horizon) * 0.1)),
           (w, h)]
    d.polygon(pts, fill=(*RIDGE, 255))
    return canvas.convert("RGB")


def _png(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def _lines(call: dict) -> tuple[str, str, str, str]:
    d = as_date(call["date"])
    return (day_long(d), str(call["verdict"]), f"{pct(call['probability'])}% chance of a cloud sea",
            f"Nandi Hills · sunrise {call['sunrise']}")


def render_og(call: dict) -> bytes:
    w, h = OG_SIZE
    img = _scene(OG_SIZE, horizon=int(h * 0.80), p=call["probability"])
    d = ImageDraw.Draw(img)
    when, verdict, chance, place = _lines(call)
    m = 72
    d.text((m, 104), when, font=_font(REGULAR, 40), fill=SOFT, anchor="ls")
    d.text((m, 284), verdict, font=_fit(d, verdict, BOLD, 184, w - 2 * m),
           fill=VERDICT_COLOR.get(verdict, WHITE), anchor="ls")
    d.text((m, 360), chance, font=_font(BOLD, 52), fill=WHITE, anchor="ls")
    d.text((m, 418), place, font=_font(REGULAR, 34), fill=SOFT, anchor="ls")
    d.text((m, h - 34), FOOTER, font=_font(REGULAR, 24), fill=MUTED, anchor="ls")
    return _png(img)


def render_story(call: dict) -> bytes:
    w, h = STORY_SIZE
    img = _scene(STORY_SIZE, horizon=int(h * 0.74), p=call["probability"])
    d = ImageDraw.Draw(img)
    when, verdict, chance, place = _lines(call)
    m = 90
    d.text((m, 360), when, font=_fit(d, when, REGULAR, 60, w - 2 * m), fill=SOFT, anchor="ls")
    d.text((m, 640), verdict, font=_fit(d, verdict, BOLD, 300, w - 2 * m),
           fill=VERDICT_COLOR.get(verdict, WHITE), anchor="ls")
    d.text((m, 760), chance, font=_fit(d, chance, BOLD, 70, w - 2 * m), fill=WHITE, anchor="ls")
    d.text((m, 850), place, font=_fit(d, place, REGULAR, 48, w - 2 * m), fill=SOFT, anchor="ls")
    d.text((m, h - 70), FOOTER, font=_fit(d, FOOTER, REGULAR, 36, w - 2 * m), fill=MUTED, anchor="ls")
    return _png(img)


_cache: OrderedDict[tuple, bytes] = OrderedDict()
_cache_lock = threading.Lock()
CACHE_MAX = 48


def card_png(kind: str, call: dict) -> bytes:
    """`kind` is "og" or "story". Cached in memory per (kind, date, issued_at)."""
    key = (kind, str(call["date"]), str(call.get("issued_at")))
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    png = (render_og if kind == "og" else render_story)(call)
    with _cache_lock:
        _cache[key] = png
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)
    return png


# --- share page ----------------------------------------------------------------------------------------

def share_html(call: dict | None, day: date, *, base_url: str, web_base_url: str) -> str:
    """Open Graph page for crawlers; people are sent on to the web app."""
    base = base_url.rstrip("/")
    app_url = f"{web_base_url.rstrip('/')}/#/?d={day.isoformat()}"
    if call:
        title = og_title(call)
        version = ""
        if isinstance(call.get("issued_at"), datetime):
            version = f"?v={int(call['issued_at'].timestamp())}"
        image = f"{base}/og/{day.isoformat()}.png{version}"
        alt = f"{call['verdict']}: {pct(call['probability'])}% chance of a cloud sea at Nandi Hills, {day_long(day)}"
    else:
        title, image, alt = f"CloudSea · Nandi Hills sunrise · {day_short(day)}", None, ""
    desc = og_description(call)
    e = lambda s: html.escape(s, quote=True)  # noqa: E731
    image_tags = (f'<meta property="og:image" content="{e(image)}">\n'
                  '<meta property="og:image:width" content="1200">\n'
                  '<meta property="og:image:height" content="630">\n'
                  f'<meta property="og:image:alt" content="{e(alt)}">\n'
                  f'<meta name="twitter:image" content="{e(image)}">\n') if image else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} · CloudSea</title>
<meta name="description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="CloudSea">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(f'{base}/s/{day.isoformat()}')}">
{image_tags}<meta name="twitter:card" content="{'summary_large_image' if image else 'summary'}">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta http-equiv="refresh" content="0; url={e(app_url)}">
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0e1030;color:#e8e6f8;
font:16px/1.5 system-ui,sans-serif}}a{{color:#ffd68c}}</style>
</head>
<body>
<p>{e(title)}. <a href="{e(app_url)}">Open CloudSea</a> for the full call.</p>
</body>
</html>
"""
