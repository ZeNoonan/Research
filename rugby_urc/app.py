"""Streamlit viewer for the URC report.

A browsable version of what ``build_site.py`` renders statically: the season's
matches with their factor columns, the System #, the pick and the graded
result, plus the betting record and the factor diagnostics.

Run: ``streamlit run app.py``
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

import factor_analysis
import model
import season_report

DATA_DIR = Path(__file__).parent / "data"
JUICE = 1.1

DISPLAY_COLUMNS = {
    "date": "Date", "round": "Rd", "home": "Home", "away": "Away",
    "opening_line": "Open", "line": "Line",
    "home_score": "H", "away_score": "A",
    "home_lgt": "H LGT", "home_stdc": "H STDC", "home_power": "H Power",
    "away_lgt": "A LGT", "away_stdc": "A STDC", "away_power": "A Power",
    "system_num": "System #", "system_bet": "Bet", "result": "Result",
}


@st.cache_data
def load(year: int) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"report_{year}.csv")


def available() -> list[int]:
    return factor_analysis.available_years()


def betting_summary(df: pd.DataFrame) -> dict:
    graded = df[df["result"].notna()]
    wins = int((graded["result"] == "W").sum())
    losses = int((graded["result"] == "L").sum())
    return {
        "bets": int(df["system_bet"].notna().sum()),
        "wins": wins, "losses": losses,
        "win_rate": wins / (wins + losses) if (wins + losses) else None,
        "profit": wins - JUICE * losses,
    }


def main() -> None:
    st.set_page_config(page_title="URC Report", layout="wide")
    st.title("🏉 URC Report")
    st.caption(
        "The five-factor against-the-spread system, ported from `nfl_report` to "
        "the United Rugby Championship. Handicaps are from the home side's point "
        "of view: negative means home favoured. Nothing here is validated on "
        "rugby yet."
    )

    years = available()
    if not years:
        st.warning(
            "No report yet. Enter handicaps in `entry/urc_<year>_entry.xlsx`, run "
            "`python entry_sheet.py import --season <year>`, then "
            "`python season_report.py`."
        )
        st.stop()

    year = st.radio("Season", sorted(years, reverse=True), horizontal=True,
                    format_func=season_report.season_label)
    df = load(year)
    s = betting_summary(df)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Matches", len(df))
    c2.metric("Bets", s["bets"])
    c3.metric("Record", f"{s['wins']}–{s['losses']}")
    c4.metric("Win rate", "—" if s["win_rate"] is None else f"{s['win_rate']:.1%}")
    c5.metric("Profit (units, full juice)", f"{s['profit']:+.1f}")

    held = int(df["system_bet"].isna().sum() - df["line"].isna().sum())
    if held > 0:
        st.info(
            f"{held} priced match(es) made no pick. The system declines when a "
            f"side's previous match has no turnover count yet — two of the five "
            f"factors read it, so a guess would be a bet on dead inputs."
        )

    only_bets = st.checkbox("Show only matches the system bet", value=False)
    view = df[df["system_bet"].notna()] if only_bets else df
    st.dataframe(view[list(DISPLAY_COLUMNS)].rename(columns=DISPLAY_COLUMNS),
                 width="stretch", hide_index=True, height=560)

    st.subheader("Factor diagnostics")
    marginal, standalone = factor_analysis.build_tables()
    if marginal.empty:
        st.write("Nothing to diagnose yet.")
    else:
        labels = factor_analysis.FACTOR_LABELS
        cols = {y: season_report.season_label(y) for y in marginal.columns}
        left, right = st.columns(2)
        left.caption("Marginal contribution — net wins charged to each factor")
        left.dataframe(marginal.rename(index=labels, columns=cols), width="stretch")
        right.caption(f"Standalone success — each factor as its own rule "
                      f"(blank until {factor_analysis.MIN_VOTES} settled votes)")
        right.dataframe(
            standalone.rename(index=labels, columns=cols)
            .style.format(lambda v: "—" if pd.isna(v) else f"{v:.1%}"),
            width="stretch")

    with st.expander("How the system works"):
        st.markdown(model.__doc__)


if __name__ == "__main__":
    main()
