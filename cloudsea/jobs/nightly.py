"""Nightly job, 20:30 IST: data -> features -> TabPFN -> Gemma writes the call -> Postgres.

    uv run python -m cloudsea.jobs.nightly            # today's call, written to the database
    uv run python -m cloudsea.jobs.nightly --dry-run  # print it instead (no database needed)
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta

import pandas as pd

from cloudsea import features, label, live, metar, model, plan, writer
from cloudsea.config import IST


def _clean(v):
    """JSON-safe: NaN/NA -> None, numpy scalars -> Python."""
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA:
        return None
    return v.item() if hasattr(v, "item") else v


def build_features(day: date) -> tuple[pd.Series, dict]:
    """Feature row for call day `day`, plus notes on what data was available."""
    reports = live.recent_reports(days=5)
    dawn = metar.dawn_summary(reports)
    dawn["A_low_layer"] = label.low_layer(dawn)
    obs = features.obs_features(reports, dawn)
    d = pd.Timestamp(day)
    row = obs.loc[d] if d in obs.index else pd.Series(index=features.OBS_FEATURES, dtype=float)
    notes = {"airport_reports": int(len(reports)),
             "last_report_ist": f"{reports['ist'].max():%Y-%m-%d %H:%M}" if len(reports) else None}
    try:
        nwp = features.nwp_features(live.todays_run(day)).loc[d]
        notes["ecmwf_run"] = f"{day.isoformat()}T00Z"
    except Exception as err:  # noqa: BLE001  - the model copes with missing NWP (TabPFN handles NaN)
        nwp = pd.Series(index=features.NWP_FEATURES, dtype=float)
        notes["ecmwf_run"] = f"missing: {err!r}"[:200]
    return pd.concat([row, nwp]), notes


def make_call(day: date, train: pd.DataFrame | None = None) -> dict:
    target = day + timedelta(days=1)
    x, notes = build_features(day)
    train = train if train is not None else model.training_rows()
    p, model_info = model.predict_live(train, x)
    th = model.live_thresholds()
    verdict = model.verdict(p, th)
    pct = round(100 * p)

    sun = plan.sun_times(target)
    leave = plan.leave_by(sun["sunrise"])
    cond = live.summit_conditions(target, sun["sunrise"])
    rain_24h = bool((x.get("rain_reports_24h") or 0) > 0)
    carry = plan.carry(cond["summit_temp_c"], cond["rain_chance_pct"])
    home = next(r for r in leave if r["area"] == plan.DEFAULT_AREA)

    facts = writer.Facts(
        day_label=f"{target:%a} {target.day} {target:%b}", verdict=verdict, probability_pct=pct,
        sunrise=f"{sun['sunrise']:%H:%M}", first_light=f"{sun['first_light']:%H:%M}",
        area_label=home["label"], drive_minutes=home["drive_minutes"], buffer_minutes=home["buffer_minutes"],
        leave_by=home["leave_by"], summit_temp_c=cond["summit_temp_c"], wind_kmh=cond["wind_kmh"],
        rain_chance_pct=cond["rain_chance_pct"], carry=carry)
    written = writer.write_call(facts)
    text_kn = writer.translate(written["text"], verdict, "kn")
    text_hi = writer.translate(written["text"], verdict, "hi")

    return {
        "date": target, "issued_at": datetime.now(IST), "verdict": verdict, "probability": round(float(p), 4),
        "sunrise": facts.sunrise, "first_light": facts.first_light,
        "text": written["text"], "text_source": written["source"], "text_kn": text_kn, "text_hi": text_hi,
        "carry": carry, "conditions": {**cond, "rain_last_24h": rain_24h},
        "leave_by": [{k: r[k] for k in ("area", "label", "drive_minutes", "buffer_minutes", "leave_by")}
                     for r in leave],
        "gate": plan.GATE,
        "model": {**model_info, "writer": "Gemma 4 E2B (gemma4:e2b-it-q4_K_M)", "writer_attempts": len(written["attempts"])},
        "features": {k: _clean(v) for k, v in x.items()} | {"_notes": notes},
        "thresholds": th.__dict__,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", type=date.fromisoformat, default=None, help="call day (IST); default today")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    day = args.day or datetime.now(IST).date()
    call = make_call(day)
    print(json.dumps({k: v for k, v in call.items() if k != "features"}, indent=2, default=str))
    if args.dry_run:
        return
    from cloudsea import db
    with db.connect() as conn:
        db.init_schema(conn)
        db.upsert_call(conn, call)
        conn.commit()
    print(f"saved call for {call['date']}")


if __name__ == "__main__":
    main()
