"""Screenshots of the live app for the README and the post: `make screenshots`.

Uses headless Chromium through Playwright. Set CHROMIUM to a browser binary if Playwright's own isn't installed.
Writes docs/screenshots/*.png, including a side-by-side strip of three screens and the server's share cards.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx
from PIL import Image, ImageDraw
from playwright.async_api import async_playwright

WEB = os.environ.get("WEB_URL", "https://cloudsea-web.onrender.com")
API = os.environ.get("API_URL", "https://cloudsea-api.onrender.com")
OUT = Path("docs/screenshots")
PHONE = {"width": 390, "height": 844}
PAGE_BG = (244, 241, 234)


async def capture() -> None:
    exe = os.environ.get("CHROMIUM")
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=exe) if exe else await p.chromium.launch()
        for scheme in ("light", "dark"):
            ctx = await browser.new_context(viewport=PHONE, device_scale_factor=2, color_scheme=scheme)
            page = await ctx.new_page()
            await page.goto(f"{WEB}/#/", wait_until="networkidle")
            await page.wait_for_timeout(1000)
            await page.screenshot(path=OUT / f"home-{scheme}.png")
            if scheme == "dark":
                await ctx.close()
                continue
            # The call card in each language Gemma wrote it in.
            card = page.locator('section[aria-labelledby="text-h"]')
            await card.screenshot(path=OUT / "call-en.png")
            for lang, label in (("kn", "ಕನ್ನಡ"), ("hi", "हिन्दी")):
                button = page.get_by_role("button", name=label)
                if await button.count():
                    await button.click()
                    await page.wait_for_timeout(300)
                    await card.screenshot(path=OUT / f"call-{lang}.png")
            await page.locator('section[aria-labelledby="share-h"]').screenshot(path=OUT / "share-block.png")
            for name in ("upload", "scoreboard"):
                await page.goto(f"{WEB}/#/{name}", wait_until="networkidle")
                await page.wait_for_timeout(1000)
                await page.screenshot(path=OUT / f"{name}-light.png")
            await page.goto(f"{WEB}/#/how", wait_until="networkidle")
            await page.wait_for_timeout(1500)
            await page.locator('section[aria-labelledby="backtest-h"]').screenshot(path=OUT / "how-backtest.png")
            await page.screenshot(path=OUT / "how-light.png", full_page=True)
            await ctx.close()
        await browser.close()


def rounded(im: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *im.size), radius=radius, fill=255)
    out = Image.new("RGBA", im.size)
    out.paste(im, (0, 0), mask)
    return out


def strip(names: list[str], height: int = 1100, gap: int = 40) -> None:
    """Three phone screens side by side, for a post that shouldn't scroll forever."""
    shots = []
    for n in names:
        im = Image.open(OUT / n).convert("RGB")
        im = im.resize((round(im.width * height / im.height), height), Image.LANCZOS)
        shots.append(rounded(im, 36))
    width = sum(s.width for s in shots) + gap * (len(shots) + 1)
    canvas = Image.new("RGBA", (width, height + 2 * gap), PAGE_BG + (255,))
    x = gap
    for s in shots:
        shadow = Image.new("RGBA", s.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((0, 0, *s.size), radius=36, fill=(30, 30, 60, 40))
        canvas.alpha_composite(shadow, (x + 4, gap + 6))
        canvas.alpha_composite(s, (x, gap))
        x += s.width + gap
    canvas.convert("RGB").save(OUT / "app-strip.png", optimize=True)


def share_cards() -> None:
    today = httpx.get(f"{API}/api/today", timeout=30).json()
    if not today.get("call"):
        return
    day = today["call"]["date"]
    for kind in ("og", "story"):
        r = httpx.get(f"{API}/{kind}/{day}.png", timeout=60)
        if r.status_code == 200:
            (OUT / f"{kind}-{day}.png").write_bytes(r.content)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    asyncio.run(capture())
    strip(["home-light.png", "upload-light.png", "scoreboard-light.png"])
    share_cards()
    print("\n".join(sorted(p.name for p in OUT.glob("*.png"))), file=sys.stderr)


if __name__ == "__main__":
    main()
