"""GET /api/backtest: map docs/results/backtest.json (written by `cloudsea.model`) into the docs/API.md shape."""
from __future__ import annotations

import json
from pathlib import Path

from cloudsea.settings import ROOT

PATH = ROOT / "docs" / "results" / "backtest.json"
DEFAULT_MODEL = "tabpfn_full"

NAMES = {
    "tabpfn_full": "TabPFN (airport + ECMWF)",
    "tabpfn_obs": "TabPFN (airport only)",
    "gbt_full": "Gradient boosting (airport + ECMWF)",
    "gbt_obs": "Gradient boosting (airport only)",
    "climatology": "Climatology (monthly rate)",
    "persistence": "Persistence (like this morning)",
    "hand_rule": "Hand rule (evening dew-point spread, wind, rain)",
    "ecmwf_raw_low_cloud": "ECMWF low cloud, uncorrected",
}

_cache: dict[Path, tuple[float, dict]] = {}


def _bin_label(b: str) -> str:
    """'0.1-0.2' -> '10-20%'. Anything unexpected passes through."""
    try:
        lo, hi = (float(x) for x in b.split("-"))
    except ValueError:
        return b
    return f"{round(lo * 100)}-{round(hi * 100)}%"


def _metric(key: str, kind: str, m: dict) -> dict:
    out = {"model": NAMES.get(key, key), "id": key, "kind": kind, "n": m.get("n"),
           "brier": m.get("brier"), "roc_auc": m.get("roc_auc")}
    for k in ("go_precision", "go_nights"):
        if k in m:
            out[k] = m[k]
    return out


def shape(raw: dict) -> dict:
    head = dict(raw.get("headline") or {})
    model = head.get("model") or (DEFAULT_MODEL if DEFAULT_MODEL in raw.get("models", {})
                                  else next(iter(raw.get("models", {})), None))
    if head:
        # docs/API.md names. "Following CloudSea" means going on GO or MAYBE, matching how calls are scored.
        head.setdefault("weekends", head.get("weekend_mornings"))
        head.setdefault("cloudsea_trips", head.get("go_or_maybe_trips"))
        head.setdefault("cloudsea_seas", head.get("go_or_maybe_seas"))
    models = raw.get("models", {})
    order = sorted(models, key=lambda k: k != model)
    metrics = [_metric(k, "model", models[k].get("test", {})) for k in order]
    metrics += [_metric(k, "baseline", m) for k, m in raw.get("baselines", {}).items()]
    calibration = [{**c, "bin": _bin_label(c["bin"])} for c in models.get(model, {}).get("calibration", [])]
    return {
        "season": raw.get("test_season"),
        "model": NAMES.get(model, model) if model else None,
        "test_rows": raw.get("test_rows"),
        "test_base_rate": raw.get("test_base_rate"),
        "thresholds": models.get(model, {}).get("thresholds"),
        "headline": head or None,
        "metrics": metrics,
        "calibration": calibration,
    }


def load(path: Path = PATH) -> dict | None:
    """The shaped backtest, re-read when the file changes. None when the file doesn't exist yet."""
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return None
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    shaped = shape(json.loads(path.read_text()))
    _cache[path] = (mtime, shaped)
    return shaped
