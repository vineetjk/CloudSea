"""Result charts for the write-up, from the saved backtest outputs (no model calls).

Colours: validated categorical slots 1-2 (blue = TabPFN, orange = gradient-boosted tree), neutral grey for
baselines; text in text colours, never series colours.
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from cloudsea.settings import ROOT  # noqa: E402

OUT = ROOT / "docs" / "results"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#b5b4ad"

NAMES = {
    "tabpfn_full": "TabPFN, airport + ECMWF (live)", "gbt_full": "Boosted tree, airport + ECMWF",
    "tabpfn_obs": "TabPFN, airport only", "gbt_obs": "Boosted tree, airport only",
    "climatology": "Monthly climatology", "persistence": "Persistence (like this morning)",
    "hand_rule": "Hand rule (spread, wind, clear)", "ecmwf_raw_low_cloud": "ECMWF raw low cloud",
}


def _style(ax, title: str, subtitle: str) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.figure.text(0.02, 0.97, title, fontsize=13, fontweight="bold", color=INK, va="top")
    ax.figure.text(0.02, 0.91, subtitle, fontsize=9.5, color=INK2, va="top")


def calibration(result: dict) -> None:
    rows = result["models"]["tabpfn_full"]["calibration"]
    fig, ax = plt.subplots(figsize=(6.4, 5.4), facecolor=SURFACE)
    fig.subplots_adjust(top=0.80, left=0.12, right=0.96, bottom=0.12)
    ax.plot([0, 1], [0, 1], color=INK2, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(0.80, 0.70, "perfectly calibrated", color=INK2, fontsize=8.5, ha="center", rotation=40)
    x = [r["predicted"] for r in rows]
    y = [r["observed"] for r in rows]
    n = [r["n"] for r in rows]
    ax.plot(x, y, color=BLUE, linewidth=2, zorder=2)
    ax.scatter(x, y, s=[30 + 4 * k for k in n], color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3)
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.03, 1.06)
    ax.set_xlabel("Forecast probability of a cloud sea", color=INK2, fontsize=9.5)
    ax.set_ylabel("Share of those nights that had one", color=INK2, fontsize=9.5)
    _style(ax, "Calibration on the 2025-26 fog season",
           f"TabPFN, airport + ECMWF. {result['test_rows']} nights never seen in training,\n"
           "grouped by forecast in 10% bins; dot size = number of nights in the bin.")
    fig.savefig(OUT / "calibration.png", dpi=160, facecolor=SURFACE)
    plt.close(fig)


def brier(result: dict) -> None:
    items = {**{k: v["test"]["brier"] for k, v in result["models"].items()},
             **{k: v["brier"] for k, v in result["baselines"].items() if v.get("n")}}
    order = sorted(items, key=items.get, reverse=True)
    fig, ax = plt.subplots(figsize=(7.2, 4.6), facecolor=SURFACE)
    fig.subplots_adjust(top=0.80, left=0.36, right=0.93, bottom=0.12)
    colors = [BLUE if k.startswith("tabpfn") else ORANGE if k.startswith("gbt") else GREY for k in order]
    bars = ax.barh([NAMES[k] for k in order], [items[k] for k in order], color=colors, height=0.62,
                   edgecolor=SURFACE, linewidth=2)
    for b, k in zip(bars, order, strict=True):
        ax.text(b.get_width() + 0.004, b.get_y() + b.get_height() / 2, f"{items[k]:.3f}", va="center",
                fontsize=8.5, color=INK, fontweight="bold" if k == "tabpfn_full" else "normal")
    ax.set_xlabel("Brier score (lower is better)", color=INK2, fontsize=9.5)
    ax.grid(axis="y", visible=False)
    _style(ax, "Forecast error by model, 2025-26 season",
           f"{result['test_rows']} nights; a cloud sea on {result['test_base_rate']:.0%} of them (airport-based label).")
    fig.savefig(OUT / "brier.png", dpi=160, facecolor=SURFACE)
    plt.close(fig)


def auc_by_season(result: dict) -> None:
    oof = pd.read_csv(OUT / "oof_by_season.csv")
    test = pd.DataFrame([{"model": m, "season": result["test_season"], "auc": result["models"][m]["test"]["roc_auc"]}
                         for m in ("tabpfn_full", "gbt_full", "tabpfn_obs", "gbt_obs")])
    df = pd.concat([oof[["model", "season", "auc"]], test])
    seasons = sorted(df["season"].unique())
    fig, ax = plt.subplots(figsize=(6.8, 4.4), facecolor=SURFACE)
    fig.subplots_adjust(top=0.76, left=0.10, right=0.80, bottom=0.12)
    ax.axhline(0.5, color=INK2, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(0, 0.51, "coin flip", color=INK2, fontsize=8.5)
    for model, color, label in [("tabpfn_full", BLUE, "TabPFN"), ("gbt_full", ORANGE, "Boosted tree")]:
        s = df[df["model"] == model].set_index("season").reindex(seasons)["auc"]
        ax.plot(range(len(seasons)), s, color=color, linewidth=2, marker="o", markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2, label=label)
        ax.text(len(seasons) - 1 + 0.12, s.iloc[-1] + (0.012 if model == "tabpfn_full" else -0.03), label,
                color=INK, fontsize=9, va="center")
    ax.set_xticks(range(len(seasons)), [s + (" (test)" if s == result["test_season"] else "") for s in seasons])
    ax.set_ylim(0.45, 0.95)
    ax.set_ylabel("ROC-AUC", color=INK2, fontsize=9.5)
    ax.legend(loc="upper left", frameon=False, fontsize=8.5, labelcolor=INK)
    _style(ax, "Skill varies by season",
           "Each season predicted by a model trained only on earlier seasons.\nECMWF features exist from March 2024, so the first two seasons ran without them.")
    fig.savefig(OUT / "auc_by_season.png", dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    result = json.loads((OUT / "backtest.json").read_text())
    calibration(result)
    brier(result)
    auc_by_season(result)
    print("wrote", ", ".join(p.name for p in sorted(OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
