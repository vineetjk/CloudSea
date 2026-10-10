"""Phase 2: the forecast model, its baselines, and the backtest.

Train on earlier seasons, test on the latest full fog season (Oct 2025 - Feb 2026), never touching the test
season while choosing anything. GO/MAYBE/SKIP thresholds come from out-of-fold predictions on the training
seasons (each season predicted by a model trained only on the seasons before it).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score

from cloudsea import features, label, metar
from cloudsea.config import SEASON_MONTHS
from cloudsea.data.openmeteo import RUN_MODEL, load_runs
from cloudsea.settings import DATA_DIR, ROOT

LABEL_FROM = pd.Timestamp("2021-04-01")     # label B needs 850 hPa humidity, available from 2021-03-23
TEST_SEASON = "2025-26"
GO_PRECISION_TARGET = 0.60                   # of the nights we say GO, at least this share should deliver
SKIP_MISS_TARGET = 0.10                      # of the nights we say SKIP, at most this share should be seas
RESULTS = ROOT / "docs" / "results"


def season_of(day: pd.Timestamp) -> str:
    y = day.year if day.month >= 7 else day.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def load_table() -> pd.DataFrame:
    """All call days with features and the next dawn's label, plus season bookkeeping."""
    reports = metar.load(DATA_DIR / "raw" / "iem")
    dawn = pd.read_parquet(DATA_DIR / "interim" / "dawn.parquet")
    runs_dir = DATA_DIR / "raw" / "openmeteo" / f"{RUN_MODEL}_00z"
    runs = load_runs(runs_dir) if any(runs_dir.glob("*.json")) else None
    t = features.build_table(reports, dawn, runs, label.LABEL)
    t = t[(t["target_date"] >= LABEL_FROM) & t["y"].notna()].copy()
    t["season"] = t["target_date"].map(season_of)
    t["in_season"] = t["target_date"].dt.month.isin(SEASON_MONTHS)
    t["weekend"] = t["target_date"].dt.dayofweek >= 5
    return t


# --- models -------------------------------------------------------------------------------------------

def tabpfn_fit_predict(X_train: pd.DataFrame, y_train: pd.Series, X_test: pd.DataFrame) -> np.ndarray:
    from tabpfn_client import TabPFNClassifier
    clf = TabPFNClassifier()
    clf.fit(X_train, y_train.astype(int))
    return clf.predict_proba(X_test)[:, 1]


def gbt_fit_predict(X_train: pd.DataFrame, y_train: pd.Series, X_test: pd.DataFrame) -> np.ndarray:
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                         l2_regularization=1.0, random_state=0)
    clf.fit(X_train, y_train.astype(int))
    return clf.predict_proba(X_test)[:, 1]


MODELS = {
    "tabpfn_obs": (tabpfn_fit_predict, features.OBS_FEATURES),
    "tabpfn_full": (tabpfn_fit_predict, features.OBS_FEATURES + features.NWP_FEATURES),
    "gbt_obs": (gbt_fit_predict, features.OBS_FEATURES),
    "gbt_full": (gbt_fit_predict, features.OBS_FEATURES + features.NWP_FEATURES),
}


def baselines(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, np.ndarray]:
    month = test["target_date"].dt.month
    clim = train.groupby(train["target_date"].dt.month)["y"].mean()
    out = {"climatology": month.map(clim).fillna(train["y"].mean()).to_numpy()}

    # Persistence: tomorrow like this morning (airport part), as a frequency learned on the training rows.
    pers = train.groupby(train["today_sea_airport"].fillna(-1))["y"].mean()
    out["persistence"] = test["today_sea_airport"].fillna(-1).map(pers).fillna(train["y"].mean()).to_numpy()

    def rule(df: pd.DataFrame) -> pd.Series:
        return ((df["eve_spread_c"] <= 2.0) & (df["eve_wind_kmh"] <= 8)
                & ~(df["eve_ceiling_kft"] < 5) & (df["rain_reports_24h"] == 0))
    hit_rate = train.groupby(rule(train))["y"].mean()
    out["hand_rule"] = rule(test).map(hit_rate).fillna(train["y"].mean()).to_numpy()

    # ECMWF's own dawn forecast, unmodified: low cloud fraction as a probability.
    out["ecmwf_raw_low_cloud"] = (test["nwp_dawn_low_cloud_max"] / 100).to_numpy()
    return out


# --- metrics and thresholds ---------------------------------------------------------------------------

def metrics(y: np.ndarray, p: np.ndarray, t_go: float | None = None) -> dict:
    ok = ~np.isnan(p)
    y, p = y[ok], p[ok]
    if len(y) == 0:
        return {"n": 0}
    m = {"n": int(len(y)), "brier": round(float(brier_score_loss(y, p)), 4),
         "roc_auc": round(float(roc_auc_score(y, p)), 3) if len(set(y)) > 1 else None}
    if t_go is not None:
        go = p >= t_go
        m["go_nights"] = int(go.sum())
        m["go_precision"] = round(float(y[go].mean()), 3) if go.any() else None
    return m


def calibration(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        sel = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if sel.sum():
            out.append({"bin": f"{lo:.1f}-{hi:.1f}", "predicted": round(float(p[sel].mean()), 3),
                        "observed": round(float(y[sel].mean()), 3), "n": int(sel.sum())})
    return out


@dataclass
class Thresholds:
    skip_below: float
    go_at: float


def choose_thresholds(y: np.ndarray, p: np.ndarray) -> Thresholds:
    """GO: the lowest cut where precision reaches the target. SKIP: the highest cut where the share of seas
    among SKIP nights stays under the target. Both from out-of-fold predictions only."""
    grid = np.round(np.arange(0.05, 0.96, 0.01), 2)
    go = next((t for t in grid if (p >= t).sum() >= 10 and y[p >= t].mean() >= GO_PRECISION_TARGET), 0.95)
    skip = max((t for t in grid if (p < t).sum() >= 10 and y[p < t].mean() <= SKIP_MISS_TARGET), default=0.05)
    skip = min(skip, go)
    return Thresholds(skip_below=float(skip), go_at=float(go))


def verdict(p: float, th: Thresholds) -> str:
    return "GO" if p >= th.go_at else ("SKIP" if p < th.skip_below else "MAYBE")


# --- backtest -----------------------------------------------------------------------------------------

def out_of_fold(table: pd.DataFrame, model: str, seasons: list[str]) -> pd.Series:
    """Predict each in-season row of `seasons` with a model trained only on rows before that season."""
    fit_predict, cols = MODELS[model]
    preds = []
    for s in seasons:
        test = table[(table["season"] == s) & table["in_season"]]
        train = table[table["target_date"] < test["target_date"].min()]
        if len(test) == 0 or train["y"].nunique() < 2:
            continue
        preds.append(pd.Series(fit_predict(train[cols], train["y"], test[cols]), index=test.index))
    return pd.concat(preds) if preds else pd.Series(dtype=float)


def backtest(models: list[str]) -> dict:
    table = load_table()
    seasons = sorted(table["season"].unique())
    cv_seasons = [s for s in seasons if s < TEST_SEASON and s >= "2022-23"]
    test = table[(table["season"] == TEST_SEASON) & table["in_season"]]
    train = table[table["target_date"] < test["target_date"].min()]
    y_test = test["y"].to_numpy()
    print(f"train rows {len(train)} ({train['target_date'].min():%Y-%m-%d}..{train['target_date'].max():%Y-%m-%d}), "
          f"test rows {len(test)} ({TEST_SEASON}), test base rate {y_test.mean():.2f}", flush=True)

    result = {"label": label.LABEL, "test_season": TEST_SEASON, "train_rows": len(train), "test_rows": len(test),
              "test_base_rate": round(float(y_test.mean()), 3), "models": {}, "baselines": {}}
    preds: dict[str, np.ndarray] = {}
    for name in models:
        oof = out_of_fold(table, name, cv_seasons)
        th = choose_thresholds(table.loc[oof.index, "y"].to_numpy(), oof.to_numpy())
        fit_predict, cols = MODELS[name]
        p = fit_predict(train[cols], train["y"], test[cols])
        preds[name] = p
        result["models"][name] = {
            "thresholds": th.__dict__, "oof": metrics(table.loc[oof.index, "y"].to_numpy(), oof.to_numpy(), th.go_at),
            "test": metrics(y_test, p, th.go_at), "calibration": calibration(y_test, p)}
        print(name, result["models"][name]["test"], th, flush=True)
    for name, p in baselines(train, test).items():
        result["baselines"][name] = metrics(y_test, p)
        preds[name] = p
    pd.DataFrame(preds, index=test.index).assign(y=y_test, weekend=test["weekend"].to_numpy(),
                                                 target_date=test["target_date"].to_numpy()) \
        .to_parquet(DATA_DIR / "interim" / "backtest_predictions.parquet")
    return result


def headline(result: dict, model: str) -> dict:
    """'Last season, going every weekend = N trips and X cloud seas; following CloudSea = M trips and Y seas.'"""
    pr = pd.read_parquet(DATA_DIR / "interim" / "backtest_predictions.parquet")
    wk = pr[pr["weekend"]]
    th = Thresholds(**result["models"][model]["thresholds"])
    go = wk[model] >= th.go_at
    go_or_maybe = wk[model] >= th.skip_below
    return {"model": model, "weekend_mornings": int(len(wk)), "every_weekend_seas": int(wk["y"].sum()),
            "go_trips": int(go.sum()), "go_seas": int(wk.loc[go, "y"].sum()),
            "go_or_maybe_trips": int(go_or_maybe.sum()), "go_or_maybe_seas": int(wk.loc[go_or_maybe, "y"].sum()),
            "seas_missed_by_skip": int(wk.loc[~go_or_maybe, "y"].sum())}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", nargs="+", default=list(MODELS))
    ap.add_argument("--headline-model", default="tabpfn_full")
    args = ap.parse_args()
    result = backtest(args.models)
    if args.headline_model in result["models"]:
        result["headline"] = headline(result, args.headline_model)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "backtest.json").write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps({k: v for k, v in result.items() if k != "models"}, indent=2, default=str))


if __name__ == "__main__":
    main()
