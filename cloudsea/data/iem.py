"""Download VOBL METARs from the Iowa Environmental Mesonet, one station-year per request.

IEM throttles to about one request per second per IP and asks for sequential,
polite use, so we fetch one year at a time and pause between requests.
Docs: https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?help

Units in the CSV: vsby in statute miles, skyl1..4 in feet above ground, times in UTC.
Stdlib only, so it runs before the project environment exists.
"""
from __future__ import annotations

import argparse
import http.client
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
FIRST_YEAR = 2008  # IEM's VOBL archive begins 2008-07-21; real sky groups appear from 2011
USER_AGENT = "CloudSea/0.1 (Nandi Hills cloud-sea forecast; hackathon research)"


def year_url(station: str, network: str, year: int) -> str:
    params = [
        ("station", station),
        ("network", network),
        ("data", "all"),
        ("sts", f"{year}-01-01T00:00Z"),
        ("ets", f"{year + 1}-01-01T00:00Z"),
        ("tz", "Etc/UTC"),
        ("format", "onlycomma"),
        ("latlon", "yes"),
        ("elev", "yes"),
        ("missing", "empty"),
        ("trace", "T"),
        ("direct", "no"),
        ("report_type", "3"),  # routine METAR
        ("report_type", "4"),  # SPECI
    ]
    return URL + "?" + urllib.parse.urlencode(params)


def fetch(url: str, attempts: int = 5) -> bytes:
    for attempt in range(attempts):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        wait = 10 * (attempt + 1)
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if err.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
            wait = int(err.headers.get("Retry-After") or wait)
            reason = f"HTTP {err.code}"
        except (http.client.IncompleteRead, urllib.error.URLError, TimeoutError, ConnectionError) as err:
            # IEM occasionally drops long chunked responses mid-stream.
            if attempt == attempts - 1:
                raise
            reason = type(err).__name__
        print(f"  {reason}, retrying in {wait}s", file=sys.stderr, flush=True)
        time.sleep(wait)
    raise RuntimeError("unreachable")


def download(out_dir: Path, station: str, network: str, first: int, last: int,
             force: bool = False, pause: float = 2.0) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    this_year = date.today().year
    for year in range(first, last + 1):
        path = out_dir / f"{station}_{year}.csv"
        # The current year is always refreshed; past years are immutable once downloaded.
        if path.exists() and not force and year != this_year:
            continue
        body = fetch(year_url(station, network, year))
        tmp = path.with_suffix(".csv.part")
        tmp.write_bytes(body)
        tmp.replace(path)
        rows = max(body.count(b"\n") - 1, 0)
        print(f"{station} {year}: {rows} reports", flush=True)
        time.sleep(pause)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("data/raw/iem"))
    ap.add_argument("--station", default="VOBL")
    ap.add_argument("--network", default="IN__ASOS")
    ap.add_argument("--first", type=int, default=FIRST_YEAR)
    ap.add_argument("--last", type=int, default=date.today().year)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    download(args.out, args.station, args.network, args.first, args.last, args.force)


if __name__ == "__main__":
    main()
