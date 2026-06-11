"""Streamlit viewer for the replicated NFL reports.

Shows each season's games with the replicated factor columns (LGT, STDC, Power),
the System #, the model's pick and the graded result, plus a summary of the
betting record and how closely we match Aaron Brown's published reports.

Run: ``streamlit run app.py``
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

import model

DATA_DIR = Path(__file__).parent / "data"

DISPLAY_COLUMNS = {
    "date": "Date",
    "home": "Home",
    "away": "Away",
    "line": "Line",
    "home_score": "H",
    "away_score": "A",
    "home_lgt": "H LGT",
    "home_stdc": "H STDC",
    "home_power": "H Power",
    "away_lgt": "A LGT",
    "away_stdc": "A STDC",
    "away_power": "A Power",
    "system_num": "System #",
    "system_bet": "Bet",
    "result": "Result",
}


@st.cache_data
def load(year: int) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / f"report_{year}.csv")
    return model.apply_system(df)


def betting_summary(df: pd.DataFrame) -> dict:
    graded = df[df["result"].notna()]
    wins = (graded["result"] == "W").sum()
    losses = (graded["result"] == "L").sum()
    bets = int(df["system_bet"].notna().sum())
    win_rate = wins / (wins + losses) if (wins + losses) else 0.0
    # One unit per bet, full 10% juice: a loss costs 1.1 units.
    profit = wins * 1.0 - losses * 1.1
    return {
        "bets": bets,
        "wins": int(wins),
        "losses": int(losses),
        "win_rate": win_rate,
        "profit": profit,
    }


def main() -> None:
    st.set_page_config(page_title="NFL Report replication", layout="wide")
    st.title("🏈 NFL Report — replicated")
    st.caption(
        "Aaron Brown's five-factor against-the-spread system, reproduced from "
        "the published 2015 / 2016 reports. See README for the model."
    )

    year = st.radio("Season", (2016, 2015), horizontal=True)
    df = load(year)
    s = betting_summary(df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bets", s["bets"])
    c2.metric("Record", f"{s['wins']}–{s['losses']}")
    c3.metric("Win rate", f"{s['win_rate']:.1%}")
    c4.metric("Profit (units, full juice)", f"{s['profit']:+.1f}")

    # Replication check against the published columns.
    num_ok = int((df["system_num_calc"] == df["system_num"]).sum())
    st.write(
        f"**Replication:** recomputed System # matches the published value on "
        f"{num_ok}/{len(df)} games."
    )

    only_bets = st.checkbox("Show only games the system bet", value=False)
    view = df[df["system_bet"].notna()] if only_bets else df
    table = view[list(DISPLAY_COLUMNS)].rename(columns=DISPLAY_COLUMNS)
    st.dataframe(table, use_container_width=True, hide_index=True, height=600)


if __name__ == "__main__":
    main()
