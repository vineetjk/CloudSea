"""Download a fixed set of Creative Commons Nandi Hills photos from Wikimedia Commons for the Gemma vision benchmark.

Photos are 1024 px thumbnails, close to what the upload flow will send after client-side resizing.
Writes ATTRIBUTION.md next to the photos (CC BY-SA requires credit + licence link).
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import httpx

API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia rejects (403) clients without contact details, especially from datacenter IPs.
UA = "CloudSea/0.1 (https://github.com/vineetjk/CloudSea) python-httpx"

TITLES = [
    "File:Above the clouds at Nandi hills.jpg",
    "File:Early sunrise above clouds Nandi hills Bangalore.jpg",
    "File:Sun rising over a blanket of clouds, Nandi Hills, Karnataka.jpg",
    "File:Hill Above the clouds at nandi hills.jpg",
    "File:A Hill From Over The Clouds, Nandi Hills.jpg",
    "File:Fog on Nandi Hills.jpg",
    "File:Nandi Hills foggy view.jpg",
    "File:Nandi Hills.j Bangalore.jpg",
    "File:Nandi betta(hills).jpg",
    "File:Nandi Hills Bangalore 2017.jpg",
    "File:Sunrise @ Nandi Hils (4317595471).jpg",
    "File:Nandi Hills Sunrise.jpg",
    "File:Sunrise at Nandi Hills.jpg",
    "File:Sky view from top of nandi hills.jpg",
]


def slug(title: str) -> str:
    stem = title.removeprefix("File:").rsplit(".", 1)[0]
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")[:60] + ".jpg"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("data/raw/test_photos"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    with httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True) as http:
        meta = http.get(API, params={
            "action": "query", "titles": "|".join(TITLES), "prop": "imageinfo",
            "iiprop": "url|extmetadata", "iiurlwidth": 1024, "format": "json",
            "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist",
        }).raise_for_status().json()
        credits = []
        for page in meta["query"]["pages"].values():
            info = page["imageinfo"][0]
            m = info["extmetadata"]
            name = slug(page["title"])
            path = args.out / name
            if not path.exists():
                path.write_bytes(http.get(info["thumburl"]).raise_for_status().content)
                time.sleep(0.5)
            artist = re.sub("<[^>]+>", "", m.get("Artist", {}).get("value", "unknown")).strip()
            credits.append({
                "file": name, "title": page["title"], "source": info["descriptionurl"],
                "artist": artist, "license": m["LicenseShortName"]["value"],
                "license_url": m.get("LicenseUrl", {}).get("value", ""),
            })
            print(f"{name}  ({credits[-1]['license']}, {artist})")

    credits.sort(key=lambda c: c["file"])
    (args.out / "credits.json").write_text(json.dumps(credits, indent=2))
    lines = ["# Test photo credits", "", "Thumbnails from Wikimedia Commons, used unmodified for benchmarking.", ""]
    lines += [f"- `{c['file']}`: [{c['title'][5:]}]({c['source']}) by {c['artist']}, "
              f"[{c['license']}]({c['license_url']})" for c in credits]
    (args.out / "ATTRIBUTION.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
