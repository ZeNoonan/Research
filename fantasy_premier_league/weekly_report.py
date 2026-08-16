"""Print the weekly FPL pick list and write it to a CSV.

Rates every eligible player on the seven factors (see ``model.py``) using
all gameweek files in the season directory, prints the 6- and 7-star picks
by position, and writes the full rated table to ``reports/``.

    python weekly_report.py                          # data/2025-26, all GWs
    python weekly_report.py --data data/2026-27      # the new season
    python weekly_report.py --through-gw 30          # rate as of GW30
    python weekly_report.py --min-stars 3 --top 10   # deeper watchlist
"""

from __future__ import annotations

import argparse
from pathlib import Path

import model

HERE = Path(__file__).parent
POSITION_NAMES = {"GK": "Goalkeepers", "DEF": "Defenders",
                  "MID": "Midfielders", "FWD": "Forwards"}

REPORT_COLUMNS = ["name", "position", "team", "price", "stars",
                  "factors_assessed", "factor_letters", "xpts90",
                  "form_points", "minutes_avg", "minutes_share", "justice_margin",
                  "selected",
                  "minutes", "appearances", "gws_since_app", "points",
                  "eligible"]


def fmt_selected(n: float) -> str:
    return f"{n / 1e6:.1f}m" if n >= 1e6 else f"{n / 1e3:.0f}k"


def print_report(rated, min_stars: int, top: int | None) -> None:
    through = int(rated["through_gw"].iloc[0])
    used = int(rated["gws_used"].iloc[0])
    n_eligible = int(rated["eligible"].sum())
    print(f"FPL seven-factor picks - through GW{through} "
          f"({used} gameweek{'s' if used != 1 else ''} of evidence, "
          f"{n_eligible} eligible players)")
    if used < model.MINUTES_WINDOW:
        print(f"NOTE: fewer than {model.MINUTES_WINDOW} gameweeks loaded; "
              "form/justice windows are thin, treat ratings as provisional.")
    print("Factors: Q quality  V value  F form  M minutes  N nailed  "
          f"J justice  C crowd (one star each; {min_stars}+ stars shown)\n")

    picks = model.recommendations(rated, min_stars=min_stars)
    for pos in model.POSITIONS:
        block = picks[picks["position"] == pos]
        if top:
            block = block.head(top)
        print(f"--- {POSITION_NAMES[pos]} ---")
        if block.empty:
            print("  (none at this star level)")
        for r in block.itertuples():
            of = "" if r.factors_assessed == len(model.FACTORS) \
                else f"/{r.factors_assessed}"
            stale = f"  [last played GW{r.last_app_round:.0f}]" \
                if r.gws_since_app >= 2 else ""
            print(f"  {r.stars}*{of:<3}{r.name:<28} {r.team:<15} "
                  f"£{r.price:>4.1f}m  {r.factor_letters:<7} "
                  f"xPts/90 {r.xpts90:4.1f}  "
                  f"owned {fmt_selected(r.selected):>6}{stale}")
        print()

    captains = picks[picks["position"].isin(("MID", "FWD"))].nlargest(3, "xpts90")
    if not captains.empty:
        names = ", ".join(f"{r.name} ({r.team})" for r in captains.itertuples())
        print(f"Captain shortlist: {names}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=HERE / "data" / "2025-26",
                    help="season directory of gw<N>.csv files")
    ap.add_argument("--through-gw", type=int, default=None,
                    help="rate using only gameweeks up to this round")
    # 6 of 7, not 5 of 7: Minutes went from one star to two, so the old
    # 5-of-6 default would now show a materially wider list. 6+ keeps the
    # same selectivity (n=1726 player-weeks over 2025/26, against 2176 at
    # the old 5+ of 6).
    ap.add_argument("--min-stars", type=int, default=6)
    ap.add_argument("--top", type=int, default=None,
                    help="cap the printed list per position")
    ap.add_argument("--out", default=None,
                    help="output CSV (default reports/rated_gw<N>.csv)")
    args = ap.parse_args()

    rated = model.rate_season(args.data, args.through_gw)
    print_report(rated, args.min_stars, args.top)

    through = int(rated["through_gw"].iloc[0])
    out = Path(args.out) if args.out else HERE / "reports" / f"rated_gw{through}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = REPORT_COLUMNS + list(model.FACTORS)
    (rated.sort_values(["stars", "xpts90"], ascending=False)
          .to_csv(out, index=False, columns=cols, float_format="%.3f"))
    print(f"\nFull rated table (all {len(rated)} players): {out}")


if __name__ == "__main__":
    main()
