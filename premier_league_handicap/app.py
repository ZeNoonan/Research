"""Streamlit app: Premier League 2025-2026 handicap-adjusted analysis."""

import altair as alt
import pandas as pd
import streamlit as st

from analysis import GAMES_PER_SEASON, load_all

st.set_page_config(
    page_title="Premier League 2025-2026 Handicap Analysis",
    page_icon="⚽",
    layout="wide",
)

handicaps, results, games, standings = load_all()

st.title("Premier League 2025-2026 — Handicap Analysis")
st.caption(
    "Each team's handicap is added to their actual points to give an adjusted total. "
    f"For the game-by-game view the handicap is spread evenly across all "
    f"{GAMES_PER_SEASON} games (handicap ÷ {GAMES_PER_SEASON} per game)."
)

tab_table, tab_games = st.tabs(["Adjusted league table", "Game-by-game"])

# --- Adjusted league table ------------------------------------------------
with tab_table:
    st.subheader("Adjusted standings (sorted by adjusted points)")

    table = standings[
        [
            "adjusted_rank",
            "team",
            "played",
            "wins",
            "draws",
            "losses",
            "goals_for",
            "goals_against",
            "goal_difference",
            "actual_points",
            "handicap",
            "adjusted_points",
            "actual_rank",
            "rank_change",
        ]
    ].rename(
        columns={
            "adjusted_rank": "Pos",
            "team": "Team",
            "played": "P",
            "wins": "W",
            "draws": "D",
            "losses": "L",
            "goals_for": "GF",
            "goals_against": "GA",
            "goal_difference": "GD",
            "actual_points": "Actual Pts",
            "handicap": "Handicap",
            "adjusted_points": "Adjusted Pts",
            "actual_rank": "Actual Pos",
            "rank_change": "Pos Δ",
        }
    )

    st.dataframe(
        table,
        hide_index=True,
        use_container_width=True,
        height=740,
        column_config={
            "Adjusted Pts": st.column_config.NumberColumn(format="%d"),
            "Actual Pts": st.column_config.NumberColumn(format="%d"),
            "Handicap": st.column_config.NumberColumn(format="%d"),
            "Pos Δ": st.column_config.NumberColumn(
                help="Positions gained (+) or lost (-) vs the actual table"
            ),
        },
    )

    st.markdown("##### Actual vs adjusted points")
    chart_df = standings.melt(
        id_vars="team",
        value_vars=["actual_points", "handicap"],
        var_name="component",
        value_name="points",
    )
    chart_df["component"] = chart_df["component"].map(
        {"actual_points": "Actual points", "handicap": "Handicap"}
    )
    order = standings.sort_values("adjusted_points", ascending=False)["team"].tolist()
    bar = (
        alt.Chart(chart_df)
        .mark_bar()
        .encode(
            x=alt.X("points:Q", title="Points"),
            y=alt.Y("team:N", sort=order, title=None),
            color=alt.Color(
                "component:N",
                title=None,
                scale=alt.Scale(
                    domain=["Actual points", "Handicap"],
                    range=["#37003c", "#00ff85"],
                ),
            ),
            tooltip=["team", "component", "points"],
        )
        .properties(height=520)
    )
    st.altair_chart(bar, use_container_width=True)

# --- Game-by-game ----------------------------------------------------------
with tab_games:
    st.subheader("Game-by-game adjusted points")

    teams = standings["team"].tolist()
    col_sel, col_info = st.columns([2, 3])
    with col_sel:
        team = st.selectbox("Team", teams)

    team_games = games[games["team"] == team].copy()
    row = standings[standings["team"] == team].iloc[0]
    per_game = row["handicap"] / GAMES_PER_SEASON

    with col_info:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Actual points", int(row["actual_points"]))
        c2.metric("Handicap", int(row["handicap"]))
        c3.metric("Handicap / game", f"{per_game:.4f}")
        c4.metric("Adjusted points", int(row["adjusted_points"]))

    display = team_games[
        [
            "match_no",
            "date",
            "venue",
            "opponent",
            "gf",
            "ga",
            "result",
            "base_points",
            "handicap_per_game",
            "adjusted_points",
            "cum_base_points",
            "cum_adjusted_points",
        ]
    ].rename(
        columns={
            "match_no": "Game",
            "date": "Date",
            "venue": "Venue",
            "opponent": "Opponent",
            "gf": "GF",
            "ga": "GA",
            "result": "Result",
            "base_points": "Base Pts",
            "handicap_per_game": "+ Handicap",
            "adjusted_points": "Adj Pts",
            "cum_base_points": "Cum Actual",
            "cum_adjusted_points": "Cum Adjusted",
        }
    )
    display["Date"] = display["Date"].dt.strftime("%d %b %Y")

    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        height=560,
        column_config={
            "+ Handicap": st.column_config.NumberColumn(format="%.4f"),
            "Adj Pts": st.column_config.NumberColumn(format="%.4f"),
            "Cum Adjusted": st.column_config.NumberColumn(format="%.2f"),
        },
    )
    st.caption(
        f"Example: a win gives {3} base points + {per_game:.4f} handicap "
        f"= {3 + per_game:.4f} adjusted points for that game."
    )

    st.markdown("##### Cumulative points across the season")
    line_df = team_games[["match_no", "cum_base_points", "cum_adjusted_points"]].melt(
        id_vars="match_no", var_name="series", value_name="points"
    )
    line_df["series"] = line_df["series"].map(
        {"cum_base_points": "Actual", "cum_adjusted_points": "Adjusted"}
    )
    line = (
        alt.Chart(line_df)
        .mark_line(point=True)
        .encode(
            x=alt.X("match_no:Q", title="Game number"),
            y=alt.Y("points:Q", title="Cumulative points"),
            color=alt.Color(
                "series:N",
                title=None,
                scale=alt.Scale(
                    domain=["Actual", "Adjusted"], range=["#37003c", "#00ff85"]
                ),
            ),
            tooltip=["match_no", "series", alt.Tooltip("points:Q", format=".2f")],
        )
        .properties(height=380)
    )
    st.altair_chart(line, use_container_width=True)
