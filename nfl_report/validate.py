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
    # Bet recorded but the team name was lost in the PDF; fall back to the sign.
    return "home" if row.system_num > 0 else "away"


def validate_year(year: int) -> None:
    df = pd.read_csv(DATA_DIR / f"report_{year}.csv")
    df = model.apply_system(df)
    df = model.season_to_date_covers(df)
    n = len(df)

    # 1. System # ------------------------------------------------------------
    num_match = (df["system_num_calc"] == df["system_num"]).sum()

    # 2. Bet side ------------------------------------------------------------
    pub_side = [_published_side(r) for r in df.itertuples()]
    side_match = sum(p == c for p, c in zip(pub_side, df["pick_calc"]))

    # 3. Result (only graded over games the report actually bet) -------------
    bet_mask = df["system_bet"].notna()
    res_pub = df.loc[bet_mask, "result"]
    res_calc = df.loc[bet_mask, "result_calc"]
    res_match = (res_pub.fillna("-") == res_calc.fillna("-")).sum()

    # 4. STDC reconstruction (only where both names survived the PDF) --------
    home_ok = df["home_stdc_calc"].notna()
    away_ok = df["away_stdc_calc"].notna()
    home_stdc_match = (df.loc[home_ok, "home_stdc_calc"] == df.loc[home_ok, "home_stdc"]).sum()
    away_stdc_match = (df.loc[away_ok, "away_stdc_calc"] == df.loc[away_ok, "away_stdc"]).sum()

    print(f"\n===== {year} ({n} games) =====")
    print(f"System #   : {num_match}/{n} ({num_match / n:.1%})")
    print(f"Bet side   : {side_match}/{n} ({side_match / n:.1%})")
    print(f"Result     : {res_match}/{bet_mask.sum()} graded bets")
    print(f"STDC home  : {home_stdc_match}/{home_ok.sum()} (names known)")
    print(f"STDC away  : {away_stdc_match}/{away_ok.sum()} (names known)")

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
