"""Draw the post's cover: the CloudSea name over an illustrated sunrise above a cloud sea at Nandi Hills.

Writes docs/brand/cover.svg and renders docs/brand/cover.png (2000x840, DEV's 1000x420 cover at 2x).
    uv run --with playwright==1.56.0 python scripts/make_cover.py      # CHROMIUM=path if needed
"""
from __future__ import annotations

import asyncio
import os
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "brand"
FONT_BOLD = ROOT / "cloudsea" / "assets" / "Inter-Bold.ttf"
FONT_REG = ROOT / "cloudsea" / "assets" / "Inter-Regular.ttf"
W, H = 1000, 420
SUN = (712, 286)
rng = random.Random(11)


def cloud_layer(baseline: float, rmin: float, rmax: float, step: float, jitter: float, fill: str,
                blur: float, opacity: float, x0: float = -60, x1: float = W + 60) -> str:
    """A bank of overlapping circles over a solid base: a soft, lumpy cloud top."""
    circles = []
    x = x0
    while x < x1:
        r = rng.uniform(rmin, rmax)
        cy = baseline + rng.uniform(-jitter, jitter) + r * 0.35
        circles.append(f'<circle cx="{x:.1f}" cy="{cy:.1f}" r="{r:.1f}"/>')
        x += step * rng.uniform(0.6, 1.1)
    base = f'<rect x="-60" y="{baseline + rmin * 0.6:.1f}" width="{W + 120}" height="{H}"/>'
    return (f'<g fill="{fill}" opacity="{opacity}" filter="url(#blur{int(blur * 10)})">'
            + "".join(circles) + base + "</g>")


def peak(cx: float, top: float, half: float, base: float, fill: str) -> str:
    """A rounded conical hill, like the granite domes around Nandi."""
    return (f'<path d="M{cx - half:.0f},{base} C{cx - half * 0.45:.0f},{base - (base - top) * 0.55} '
            f'{cx - half * 0.18:.0f},{top} {cx:.0f},{top} C{cx + half * 0.2:.0f},{top} '
            f'{cx + half * 0.5:.0f},{base - (base - top) * 0.6} {cx + half:.0f},{base} Z" fill="{fill}"/>')


def eucalyptus(x: float, ground: float, height: float, lean: float = 0) -> str:
    """A tall thin trunk with loose clumps of leaves, Nandi's typical tree, as a silhouette."""
    top = ground - height
    parts = [f'<path d="M{x - 1.6},{ground} Q{x + lean * 0.5},{(ground + top) / 2} {x + lean},{top + 10} '
             f'L{x + lean + 1.2},{top + 10} Q{x + lean * 0.5 + 2},{(ground + top) / 2} {x + 1.8},{ground} Z"/>']
    for _ in range(9):
        cx = x + lean + rng.uniform(-height * 0.22, height * 0.22)
        cy = top + rng.uniform(0, height * 0.42)
        parts.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rng.uniform(7, 15):.1f}" ry="{rng.uniform(5, 9):.1f}"/>')
    return "".join(parts)


def railing(x0: float, x1: float, y0: float, y1: float) -> str:
    """The iron fence at the viewpoint: two rails and spear-topped bars."""
    def y_at(x: float) -> float:
        return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    bars = []
    x = x0
    while x <= x1:
        y = y_at(x)
        bars.append(f'<rect x="{x - 0.9:.1f}" y="{y - 26:.1f}" width="1.8" height="26"/>'
                    f'<path d="M{x - 2.4:.1f},{y - 26:.1f} L{x:.1f},{y - 31:.1f} L{x + 2.4:.1f},{y - 26:.1f} Z"/>')
        x += 7.5
    rails = (f'<path d="M{x0},{y0 - 22} L{x1},{y1 - 22}" stroke="#120f26" stroke-width="2"/>'
             f'<path d="M{x0},{y0 - 6} L{x1},{y1 - 6}" stroke="#120f26" stroke-width="2"/>')
    return f'<g fill="#120f26">{"".join(bars)}{rails}</g>'


def person(x: float, ground: float, s: float = 1.0) -> str:
    return (f'<g fill="#120f26"><circle cx="{x}" cy="{ground - 31 * s:.1f}" r="{4.2 * s:.1f}"/>'
            f'<path d="M{x - 5 * s:.1f},{ground} L{x - 4.5 * s:.1f},{ground - 25 * s:.1f} '
            f'Q{x},{ground - 28 * s:.1f} {x + 4.5 * s:.1f},{ground - 25 * s:.1f} L{x + 5 * s:.1f},{ground} Z"/></g>')


def svg() -> str:
    stars = "".join(
        f'<circle cx="{rng.uniform(380, 990):.0f}" cy="{rng.uniform(8, 150):.0f}" r="{rng.uniform(0.5, 1.3):.1f}" '
        f'fill="#fff" opacity="{rng.uniform(0.25, 0.7):.2f}"/>' for _ in range(46))
    blurs = "".join(f'<filter id="blur{b}" x="-10%" y="-50%" width="120%" height="200%">'
                    f'<feGaussianBlur stdDeviation="{b / 10}"/></filter>' for b in (8, 15, 25, 40, 60))
    ground = (f'<path d="M0,268 C40,262 78,270 112,284 C150,300 190,316 232,330 C282,346 330,360 372,374 '
              f'C402,384 430,398 452,420 L0,420 Z" fill="#161331"/>')
    trees = (eucalyptus(26, 271, 66, -3) + eucalyptus(62, 274, 56, 4) + eucalyptus(112, 289, 46, -2)
             + eucalyptus(150, 300, 36, 3))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#0f1436"/><stop offset="0.38" stop-color="#2c2b63"/>
    <stop offset="0.58" stop-color="#6a4a86"/><stop offset="0.72" stop-color="#c46b78"/>
    <stop offset="0.82" stop-color="#ef9a62"/><stop offset="0.9" stop-color="#f8c77c"/>
  </linearGradient>
  <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="#ffe2a0" stop-opacity="0.95"/><stop offset="0.35" stop-color="#ffc77a" stop-opacity="0.45"/>
    <stop offset="1" stop-color="#ff9a6a" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="peak" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#3c2f63"/><stop offset="1" stop-color="#6b5287"/>
  </linearGradient>
  <linearGradient id="peakFar" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#7a5a8d"/><stop offset="1" stop-color="#b07a92"/>
  </linearGradient>
  <linearGradient id="seaLit" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#f1dbe6"/><stop offset="0.62" stop-color="#ffe9d0"/><stop offset="1" stop-color="#f6dde2"/>
  </linearGradient>
  <linearGradient id="seaFront" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#e3dcef"/>
  </linearGradient>
  {blurs}
  <style>
    @font-face {{ font-family: "Inter"; font-weight: 700; src: url("{FONT_BOLD.as_uri()}"); }}
    @font-face {{ font-family: "Inter"; font-weight: 400; src: url("{FONT_REG.as_uri()}"); }}
    .name {{ font-family: Inter, sans-serif; font-weight: 700; font-size: 98px; letter-spacing: -2.8px; }}
    .tag {{ font-family: Inter, sans-serif; font-weight: 400; font-size: 25px; letter-spacing: 0.2px; }}
    .small {{ font-family: Inter, sans-serif; font-weight: 700; font-size: 14.5px; letter-spacing: 2.4px; }}
  </style>
</defs>
<rect width="{W}" height="{H}" fill="url(#sky)"/>
{stars}
<circle cx="{SUN[0]}" cy="{SUN[1]}" r="230" fill="url(#glow)"/>
<circle cx="{SUN[0]}" cy="{SUN[1] + 4}" r="31" fill="#fff0c4"/>
{peak(905, 232, 110, 330, "url(#peakFar)")}
{peak(575, 262, 70, 330, "url(#peakFar)")}
{cloud_layer(292, 18, 40, 30, 4, "#e9c3cd", 2.5, 0.85)}
{peak(818, 222, 92, 340, "url(#peak)")}
{cloud_layer(312, 22, 48, 34, 5, "url(#seaLit)", 1.5, 0.96)}
{cloud_layer(338, 26, 58, 40, 6, "url(#seaFront)", 1.5, 1)}
{cloud_layer(356, 26, 54, 42, 6, "#d8cfe8", 2.5, 0.95, x0=260)}
{cloud_layer(368, 28, 60, 46, 6, "url(#seaFront)", 1.2, 1, x0=280)}
{cloud_layer(390, 30, 64, 50, 7, "#d6cde6", 2.5, 0.9, x0=330)}
{cloud_layer(402, 32, 70, 54, 7, "url(#seaFront)", 1.0, 1, x0=350)}
{ground}
<g fill="#161331">{trees}</g>
{railing(176, 360, 318, 377)}
{person(258, 344, 1.0)}{person(272, 349, 0.92)}
<circle cx="74" cy="72" r="16" fill="#ffd27f"/>
<g fill="#ffffff"><circle cx="66" cy="86" r="10"/><circle cx="80" cy="80" r="13"/><circle cx="94" cy="87" r="9"/>
<rect x="56" y="86" width="47" height="10" rx="5"/></g>
<text x="114" y="100" class="name" fill="#ffffff">CloudSea</text>
<text x="56" y="142" class="tag" fill="#e6e1ff">Tomorrow's sunrise call for Nandi Hills</text>
<text x="57" y="174" class="small" fill="#ffd27f">GO · MAYBE · SKIP · EVERY NIGHT AT 8:30 PM</text>
</svg>'''


async def render(svg_path: Path, png_path: Path) -> None:
    from playwright.async_api import async_playwright
    exe = os.environ.get("CHROMIUM")
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=exe) if exe else await p.chromium.launch()
        page = await browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        await page.goto(svg_path.as_uri())
        await page.wait_for_timeout(600)
        await page.screenshot(path=png_path)
        await browser.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    svg_path = OUT / "cover.svg"
    svg_path.write_text(svg())
    asyncio.run(render(svg_path, OUT / "cover.png"))
    print(OUT / "cover.png")


if __name__ == "__main__":
    main()
