"""Morning grader, 08:15 IST: what did the airport see at dawn, and was last night's call right?

Stores the airport-based outcome (label B from Phase 1) with its evidence, and adds last night's features
plus this outcome as a new training row, so the model keeps learning from live days.

    uv run python -m cloudsea.jobs.grader              # grade today's dawn
    uv run python -m cloudsea.jobs.grader --day 2026-10-11 --dry-run
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta

import pandas as pd

from cloudsea import label, live, metar
from cloudsea.config import IST


def grade(day: date) -> dict:
    reports = live.recent_reports(days=2)
    dawn = metar.dawn_summary(reports)
    d = pd.Timestamp(day)
    if d not in dawn.index:
        return {"airport_outcome": None, "evidence": "No airport reports for the dawn window.", "dawn": {}}
    row = dawn.loc[[d]].copy()
    row["rh850"] = live.summit_rh850(day)
    y = label.label(row).iloc[0]
    r = row.iloc[0]
    outcome = None if pd.isna(y) else ("cloud_sea" if y == 1 else "no_sea")

    def fmt(v, unit):
        return "none" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.0f} {unit}"
    evidence = (f"VOBL 05:30-07:30: {int(r.n_dawn)} reports, low layer in {int(r.low_layer_reports)}, "
                f"lowest visibility {fmt(r.min_vis_m, 'm')}, lowest ceiling {fmt(r.min_ceiling_ft, 'ft')}, "
                f"rain in {int(r.precip_reports)}; 850 hPa humidity {fmt(r.rh850, '%')}")
    dawn_json = {k: (None if pd.isna(v) else (v.item() if hasattr(v, "item") else v))
                 for k, v in r.drop(labels=["metars"]).items()}
    dawn_json["metars"] = r.metars
    return {"airport_outcome": outcome, "y": None if pd.isna(y) else float(y), "evidence": evidence, "dawn": dawn_json}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", type=date.fromisoformat, default=None, help="dawn date to grade (IST); default today")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    day = args.day or datetime.now(IST).date()
    result = grade(day)
    print(json.dumps({"date": day.isoformat(), **result}, indent=2, default=str))
    if args.dry_run:
        return
    from cloudsea import db
    with db.connect() as conn:
        db.init_schema(conn)
        db.upsert_outcome(conn, day, result["airport_outcome"], result["evidence"], result["dawn"])
        call = db.get_call(conn, day)
        if call is not None:
            feats = {k: v for k, v in call["features"].items() if not k.startswith("_")}
            db.upsert_train_row(conn, day - timedelta(days=1), feats, result.get("y"))
        conn.commit()
    print(f"graded {day}: {result['airport_outcome']} (call: {call['verdict'] if call else 'none'})")


if __name__ == "__main__":
    main()
