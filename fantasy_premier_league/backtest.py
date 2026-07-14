"""Score the star ratings against what actually happened next week.

For every gameweek G where at least one earlier gameweek is loaded, rate all
players on data through G-1, then look up their actual FPL points in G. If
the model means anything, average next-week points should rise with the star
rating — the same monotonicity treatment the NFL report and bracket projects
get. Also reports each factor standalone (average next-week points with the
star vs without), the analogue of ``nfl_report/factor_analysis.py``.

Needs two or more gameweek files; with only the gw38 sample it explains
itself and exits. Drop in gw1.csv .. gw38.csv and it runs the full season.

    python backtest.py [--data data/2025-26]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import model

HERE = Path(__file__).parent


def backtest(data_dir) -> pd.DataFrame | None:
    gws = model.load_season(data_dir)
    rounds = sorted(gws["round"].unique())
    if len(rounds) < 2:
        return None

    rows = []
    for g in rounds[1:]:
        rated = model.rate_players(model.player_table(gws, through_gw=g - 1))
        rated = rated[rated["eligible"]]
        actual = (gws[gws["round"] == g]
                  .groupby("element")["total_points"].sum().rename("next_points"))
        joined = rated.join(actual, on="element")
        # No row in G = didn't feature: 0 points, which is the point of the gate.
        joined["next_points"] = joined["next_points"].fillna(0)
        joined["gw"] = g
        rows.append(joined)
    return pd.concat(rows, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=HERE / "data" / "2025-26")
    args = ap.parse_args()

    result = backtest(args.data)
    if result is None:
        print("Backtest needs 2+ gameweek files (rate through GW G-1, score "
              "against GW G). Only one is present - add gw<N>.csv files to "
              f"{args.data} (fetch_data.py builds them once the season runs).")
        return

    n_gws = result["gw"].nunique()
    print(f"Backtest over {n_gws} gameweeks, "
          f"{len(result)} player-week ratings\n")

    by_stars = (result.groupby("stars")["next_points"]
                .agg(["mean", "count"]).round(2))
    print("Average next-gameweek points by star rating (want: rising)")
    print(by_stars.rename(columns={"mean": "next-GW pts", "count": "n"})
          .to_string(), "\n")

    print("Each factor standalone (eligible players, with star vs without)")
    for f in model.FACTORS:
        w = result.loc[result[f] == 1, "next_points"].mean()
        wo = result.loc[result[f] == 0, "next_points"].mean()
        print(f"  {f:<8} with {w:5.2f}   without {wo:5.2f}   edge {w - wo:+.2f}")

    picks = result[result["stars"] >= 4]
    rest = result[result["stars"] < 4]
    print(f"\n4-5 star picks: {picks['next_points'].mean():.2f} pts/week "
          f"(n={len(picks)}) vs the rest {rest['next_points'].mean():.2f} "
          f"(n={len(rest)})")


if __name__ == "__main__":
    main()
