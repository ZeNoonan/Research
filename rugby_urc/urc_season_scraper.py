"""Scrape a whole finished URC season from the match centre, for backtesting.

A companion to ``urc_scraper.py``, which is left exactly as it is. That one
fetches a round at a time while a season is being played; this one fetches
every played match of a past season in one go - about 151 for a URC season,
144 regular-season and 7 playoff - so the system can be run over it.

It **reuses** ``urc_scraper``'s feed calls and stat-finding rather than copying
them. That code is proven on real data (every team's points reconciled with its
tries, conversions and kicks on the first live run), and one copy means a fix
to it is a fix to both. So the two files must sit in the same folder.

What this adds is only what a whole-season pull needs:

* **Every played match**, regular season and playoffs, in one click.
* **Playoff rounds numbered 19, 20, 21**, as the report numbers them, by the
  calendar week each stage is played in. The feed's own round number is kept
  in ``feed_round``.
* **Retries.** A single failed request out of ~151 is retried once; anything
  still failing is listed, and pressing Fetch again retries only those - the
  rest are cached.
* **Results that survive a click.** A two-minute pull is kept in the session,
  so downloading the CSV does not throw it away.

Run:  streamlit run urc_season_scraper.py
"""

from __future__ import annotations

import json
import time

import pandas as pd
import requests

import urc_scraper as base

DEFAULT_SEASON = "202501"   # 2025-26, as the match-centre URLs spell it
REGULAR_ROUNDS = 18         # URC regular season; playoffs are numbered after it
RETRY_WAIT = 2.0            # seconds before the one retry of a failed request
EXTRA_COLUMNS = ["stage", "feed_round"]


def report_rounds(fixtures: pd.DataFrame) -> pd.Series:
    """The round each match gets in the report: 1-18, then 19, 20, 21 ...

    Regular-season matches keep the feed's round. Playoff matches are numbered
    by the calendar week their stage is played in - quarter-finals spread over
    a Friday and Saturday share a week - because the feed's own numbering of
    knockout rounds is not documented, and week order is what the report uses
    for 2025-26 already.
    """
    stage_week = pd.to_datetime(fixtures["date"]).dt.isocalendar()
    week_key = stage_week["year"].astype(int) * 100 + stage_week["week"].astype(int)
    knockout = fixtures["round_type"] == "knockout"
    order = {w: REGULAR_ROUNDS + 1 + i
             for i, w in enumerate(sorted(week_key[knockout].unique()))}
    rounds = pd.to_numeric(fixtures["round"], errors="coerce")
    return rounds.where(~knockout, week_key.map(order)).astype("Int64")


def fetch_with_retry(fetch, match_id: str, season: str) -> dict:
    """One match's response, retried once after a pause."""
    try:
        return fetch(match_id, season)
    except requests.RequestException:
        time.sleep(RETRY_WAIT)
        return fetch(match_id, season)


def season_row(body: dict, fixture: pd.Series) -> dict:
    """``urc_scraper.match_row`` plus the report's round and the playoff stage."""
    row = base.match_row(body, str(fixture["match_id"]))
    row["Round"] = int(fixture["report_round"])
    row["stage"] = "playoff" if fixture["round_type"] == "knockout" else "regular"
    row["feed_round"] = fixture["round"]
    # The fixture list is the authority on who was home and when; the match
    # response should agree, and falls back to it if a field is missing.
    for col, key in (("Date", "date"), ("Home Team", "home"), ("Away Team", "away")):
        row[col] = row.get(col) or fixture[key]
    return row


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="URC season scraper", layout="wide")
    st.title("🏉 URC season scraper")
    st.caption("A whole past season from the match centre, for backtesting. "
               "Uses urc_scraper.py for the reading, and leaves it untouched.")

    @st.cache_data(ttl=12 * 3600, show_spinner=False)   # a finished season is final
    def cached_fixtures(season: str) -> pd.DataFrame:
        return base.fetch_fixtures(season)

    @st.cache_data(ttl=12 * 3600, show_spinner=False)
    def cached_match(match_id: str, season: str) -> dict:
        return fetch_with_retry(base.fetch_match, match_id, season)

    season = st.text_input("Season (as in the match-centre URL)", DEFAULT_SEASON)
    try:
        fixtures = cached_fixtures(season)
    except requests.RequestException as exc:
        st.error(f"Could not load the {season} fixture list: {exc}")
        st.stop()
    if fixtures.empty:
        st.warning(f"The feed returned no matches for season {season}.")
        st.stop()

    fixtures["report_round"] = report_rounds(fixtures)
    played = fixtures[fixtures["status"].map(base.is_played)].copy()
    regular = int((played["round_type"] == "league").sum())
    playoff = len(played) - regular

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Played", len(played))
    c2.metric("Regular season", regular)
    c3.metric("Playoffs", playoff)
    c4.metric("Not played", len(fixtures) - len(played))
    if playoff > 15 or (len(played) and regular == 0):
        st.warning("That split looks wrong for a URC season (144 regular, 7 playoff). "
                   "The feed may not be marking stages the way this expects - worth "
                   "checking the round table below before relying on the playoffs.")

    by_round = (played.groupby("report_round")
                .agg(stage=("round_type", "first"), first=("date", "min"),
                     last=("date", "max"), matches=("match_id", "size"))
                .reset_index().rename(columns={"report_round": "round"}))
    with st.expander("Rounds found"):
        base.wide(st, by_round, hide_index=True)

    key = f"season_{season}"
    minutes = len(played) * (base.PAUSE + 0.35) / 60
    if st.button(f"Fetch all {len(played)} played matches "
                 f"(about {max(1, round(minutes))} min)",
                 type="primary", disabled=played.empty):
        rows, raw, failed = [], {}, []
        progress = st.progress(0.0)
        for i, (_, fixture) in enumerate(played.iterrows(), start=1):
            label = f"{fixture['home']} v {fixture['away']} ({fixture['date']})"
            progress.progress(i / len(played), text=f"{i} of {len(played)}: {label}")
            try:
                body = cached_match(str(fixture["match_id"]), season)
                raw[str(fixture["match_id"])] = body
                rows.append(season_row(body, fixture))
            except requests.RequestException as exc:
                failed.append(f"{label}: {exc}")
            time.sleep(base.PAUSE)
        progress.empty()
        st.session_state[key] = {"rows": rows, "raw": raw, "failed": failed}

    if key not in st.session_state:
        st.stop()
    got = st.session_state[key]
    if not got["rows"]:
        st.error("No matches could be fetched.")
        for f in got["failed"]:
            st.write(f"- {f}")
        st.stop()

    columns = base.table_columns(got["rows"])
    columns = columns[:len(base.COLUMNS)] + EXTRA_COLUMNS + [
        c for c in columns[len(base.COLUMNS):] if c not in EXTRA_COLUMNS]
    table = (pd.DataFrame(got["rows"], columns=columns)
             .sort_values(["Date", "Round", "Home Team"]).reset_index(drop=True))
    whole = table.apply(lambda r: base.complete(r.to_dict()), axis=1)

    if got["failed"]:
        st.warning(f"{len(got['failed'])} match(es) could not be fetched. Press Fetch "
                   f"again to retry just these - the others are cached.")
        for f in got["failed"]:
            st.write(f"- {f}")
    if whole.all():
        st.success(f"Turnovers found for all {len(table)} matches fetched.")
    else:
        st.warning(f"Turnovers incomplete for {int((~whole).sum())} of {len(table)} "
                   f"matches - listed in the round table below.")

    summary = (table.assign(turnovers=whole)
               .groupby("Round")
               .agg(stage=("stage", "first"), matches=("match_id", "size"),
                    with_turnovers=("turnovers", "sum"))
               .reset_index())
    st.subheader("By round")
    base.wide(st, summary, hide_index=True)
    st.subheader("For the report")
    base.wide(st, table[base.COLUMNS + EXTRA_COLUMNS], hide_index=True)

    base.OUT.mkdir(parents=True, exist_ok=True)
    out = base.OUT / f"urc_{season}_season.csv"
    table.to_csv(out, index=False)
    st.download_button("Download CSV", table.to_csv(index=False), file_name=out.name,
                       mime="text/csv")
    st.caption(f"Also saved to {out}. Every stat on the page is in it, one row per "
               f"match. Send it over for the backtest.")
    with st.expander("Raw JSON for the whole season, for when a stat is missing"):
        st.download_button(f"urc_{season}_raw.json", json.dumps(got["raw"]),
                           file_name=f"urc_{season}_raw.json", mime="application/json")


if __name__ == "__main__":
    main()
