"""Validate the model against the published reports.

Loads the parsed report CSVs and, using only raw inputs, recomputes the derived
columns, then measures how often we match Aaron Brown's published values:

* **System #** – recomputed from the LGT / STDC / Power columns and the line.
* **Bet side** – recomputed from the System #.
* **Result**   – recomputed from the scores, line and System #.
* **STDC**     – independently reconstructed from prior scores and lines (i.e.
  not taken from the report at all), to confirm it is just net spread covers.

Run: ``python validate.py``
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import model

DATA_DIR = Path(__file__).parent / "data"


def _published_side(row) -> str | None:
    if not isinstance(row.system_bet, str):
        return None
    if isinstance(row.home, str) and row.system_bet == row.home:
        return "home"
    if isinstance(row.away, str) and row.system_bet == row.away:
        return "away"
    # Safety net (not normally hit now names are recovered): infer from the sign.
    return "home" if row.system_num > 0 else "away"


def validate_year(year: int) -> None:
    df = pd.read_csv(DATA_DIR / f"report_{year}.csv")
    df = model.apply_system(df)
    df = model.season_to_date_covers(df)
    n = len(df)

    # 1. System # ------------------------------------------------------------
    num_match = (df["system_num_calc"] == df["system_num"]).sum()

    # 2. Bet side (over the games the report actually bet) -------------------
    bet_mask = df["system_bet"].notna()
    pub_side = pd.Series([_published_side(r) for r in df.itertuples()], index=df.index)
    side_match = (pub_side[bet_mask] == df.loc[bet_mask, "pick_calc"]).sum()

    # 3. Result (only graded over games the report actually bet) -------------
    res_pub = df.loc[bet_mask, "result"]
    res_calc = df.loc[bet_mask, "result_calc"]
    res_match = (res_pub.fillna("-") == res_calc.fillna("-")).sum()

    # 4. STDC reconstructed from prior scores and lines. The denominator is the
    # games we can track: a team's first game of the season has no prior covers,
    # so it is left out (its true STDC is 0 by definition).
    home_ok = df["home_stdc_calc"].notna()
    away_ok = df["away_stdc_calc"].notna()
    home_stdc_match = (df.loc[home_ok, "home_stdc_calc"] == df.loc[home_ok, "home_stdc"]).sum()
    away_stdc_match = (df.loc[away_ok, "away_stdc_calc"] == df.loc[away_ok, "away_stdc"]).sum()

    print(f"\n===== {year} ({n} games) =====")
    print(f"System #   : {num_match}/{n} ({num_match / n:.1%})")
    print(f"Bet side   : {side_match}/{bet_mask.sum()} bets")
    print(f"Result     : {res_match}/{bet_mask.sum()} graded bets")
    print(f"STDC home  : {home_stdc_match}/{home_ok.sum()} trackable")
    print(f"STDC away  : {away_stdc_match}/{away_ok.sum()} trackable")

    mism = df[df["system_num_calc"] != df["system_num"]]
    if len(mism):
        print(f"-- {len(mism)} System # mismatches (first 10) --")
        cols = ["date", "home", "away", "line", "home_lgt", "home_stdc",
                "home_power", "away_lgt", "away_stdc", "away_power",
                "system_num", "system_num_calc"]
        print(mism[cols].head(10).to_string(index=False))


def main() -> None:
    for year in (2015, 2016):
        validate_year(year)


if __name__ == "__main__":
    main()
