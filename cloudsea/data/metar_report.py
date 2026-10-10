"""Phase 0 report: coverage of the VOBL METAR archive and dawn fog / low-cloud frequency by month.

Dawn window is 05:30-07:30 IST. The Nandi summit (1478 m) is about 563 m (1847 ft)
above VOBL (915 m), so a cloud layer reported below ~1800 ft at the airport sits
below summit height. Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path

IST = timedelta(hours=5, minutes=30)
DAWN_START, DAWN_END = time(5, 30), time(7, 30)
MILE_M = 1609.344
SUMMIT_ABOVE_VOBL_FT = 1800  # (1478 m - 915 m) = 563 m = 1847 ft, rounded down
MIN_DAWN_REPORTS = 3
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@dataclass
class Dawn:
    reports: int = 0
    fog: bool = False          # FG, BCFG, MIFG, PRFG (not VCFG: fog in the vicinity only)
    mist: bool = False         # BR
    min_vis_m: float | None = None
    low_ceiling_ft: float | None = None   # lowest BKN/OVC/VV base
    low_layer_ft: float | None = None     # lowest SCT/BKN/OVC/VV base
    raw: list[str] = field(default_factory=list)


def _num(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:
        return None


def _min(a: float | None, b: float | None) -> float | None:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def load(raw_dir: Path) -> tuple[dict, dict]:
    """Return per-year coverage stats and per-local-date dawn summaries."""
    years: dict[int, Counter] = defaultdict(Counter)
    days_seen: dict[int, set] = defaultdict(set)
    dawn: dict = defaultdict(Dawn)
    for path in sorted(raw_dir.glob("*.csv")):
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                utc = datetime.strptime(row["valid"], "%Y-%m-%d %H:%M")
                local = utc + IST
                y = local.year
                years[y]["reports"] += 1
                days_seen[y].add(local.date())
                has_sky = bool(row["skyc1"].strip())
                years[y]["with_sky"] += has_sky
                years[y]["with_wx"] += bool(row["wxcodes"].strip())
                if not (DAWN_START <= local.time() <= DAWN_END):
                    continue
                d = dawn[local.date()]
                d.reports += 1
                d.raw.append(row["metar"])
                tokens = row["wxcodes"].split()
                d.fog |= any("FG" in t and not t.startswith("VC") for t in tokens)
                d.mist |= any(t.lstrip("+-").endswith("BR") for t in tokens)
                vis = _num(row["vsby"])
                if vis is not None:
                    d.min_vis_m = _min(d.min_vis_m, vis * MILE_M)
                for i in range(1, 5):
                    cover, base = row[f"skyc{i}"].strip(), _num(row[f"skyl{i}"])
                    if base is None:
                        continue
                    if cover in ("BKN", "OVC", "VV"):
                        d.low_ceiling_ft = _min(d.low_ceiling_ft, base)
                    if cover in ("SCT", "BKN", "OVC", "VV"):
                        d.low_layer_ft = _min(d.low_layer_ft, base)
    for y, s in days_seen.items():
        years[y]["days"] = len(s)
    return years, dawn


def report(years: dict, dawn: dict, first_sky_year: int) -> str:
    out = ["## VOBL METAR coverage by year (local IST dates)", "",
           ("| Year | Reports | Days with data | % reports with sky groups | % with wx codes "
            "| Days with >=3 dawn reports | Median dawn reports/day |"),
           "|---|---|---|---|---|---|---|"]
    by_year_dawn: dict[int, list[int]] = defaultdict(list)
    for day, d in dawn.items():
        by_year_dawn[day.year].append(d.reports)
    for y in sorted(years):
        c = years[y]
        counts = by_year_dawn.get(y, [])
        ok = sum(n >= MIN_DAWN_REPORTS for n in counts)
        med = statistics.median(counts) if counts else 0
        out.append(f"| {y} | {c['reports']} | {c['days']} | {100 * c['with_sky'] / c['reports']:.0f}% "
                   f"| {100 * c['with_wx'] / c['reports']:.0f}% | {ok} | {med:g} |")

    usable = {day: d for day, d in dawn.items()
              if d.reports >= MIN_DAWN_REPORTS and day.year >= first_sky_year}
    by_month: dict[int, list[Dawn]] = defaultdict(list)
    for day, d in usable.items():
        by_month[day.month].append(d)

    def pct(ds: list[Dawn], pred) -> str:
        return f"{100 * sum(map(pred, ds)) / len(ds):.0f}%" if ds else "-"

    below = SUMMIT_ABOVE_VOBL_FT
    out += ["", f"## Dawn (05:30-07:30 IST) frequency by month, {first_sky_year} onward",
            f"Days with at least {MIN_DAWN_REPORTS} dawn reports. A day counts if any dawn report shows the condition.",
            "", ("| Month | Days | Fog (FG) | Mist (BR) | Vis < 1000 m | Vis < 3000 m "
                 f"| BKN/OVC/VV < 1000 ft | SCT+ layer < {below} ft (below summit) |"),
            "|---|---|---|---|---|---|---|---|"]
    for m in range(1, 13):
        ds = by_month.get(m, [])
        out.append(
            f"| {MONTHS[m - 1]} | {len(ds)} | {pct(ds, lambda d: d.fog)} | {pct(ds, lambda d: d.mist)} "
            f"| {pct(ds, lambda d: d.min_vis_m is not None and d.min_vis_m < 1000)} "
            f"| {pct(ds, lambda d: d.min_vis_m is not None and d.min_vis_m < 3000)} "
            f"| {pct(ds, lambda d: d.low_ceiling_ft is not None and d.low_ceiling_ft < 1000)} "
            f"| {pct(ds, lambda d: d.low_layer_ft is not None and d.low_layer_ft < below)} |")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", type=Path, default=Path("data/raw/iem"))
    ap.add_argument("--out", type=Path, default=Path("docs/phase0/metar_summary.md"))
    ap.add_argument("--first-sky-year", type=int, default=2011)
    args = ap.parse_args()
    years, dawn = load(args.raw)
    md = report(years, dawn, args.first_sky_year)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md)
    print(md)


if __name__ == "__main__":
    main()
