"""Build the weekly report from the season files.

Reads every ``data/season_<year>.csv`` - one row per match, carrying the
fixture, the handicap and (once played) the score and turnover counts - and
writes ``data/report_<year>.csv`` with the five factor columns, the System #,
the pick and the graded result.

This differs from ``nfl_report`` in one structural way. There, odds and results
arrive as two machine-generated exports and are joined on team pair and date.
Here both are typed in by hand from two web pages, so they live in **one file
per season**: a join between two hand-keyed tables would turn every typo into a
silently dropped match, and there is nothing to gain from it.

Factors that cross the season boundary
--------------------------------------
* **LGT** - a club's round-1 turnover margin is its margin in its last match of
  the previous season, playoffs included.
* **Power** - the new season's first rounds are fit on the previous season's
  last *regular* rounds until four of its own exist.

Both need the prior season present as ``data/season_<year-1>.csv``, which is
why only the tail of 2025-26 is kept: four rounds of handicaps to seed the
ratings, and the last round's turnovers to seed LGT.

Run: ``python season_report.py`` -> ``data/report_<year>.csv``
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

import model
import teams

DATA_DIR = Path(__file__).parent / "data"

REGULAR_ROUNDS = 18            # rounds above this are playoffs
FIT_WEIGHTS = [1.0, 0.5, 0.25, 0.125]  # most recent source week first
FIT_WEEKS = len(FIT_WEIGHTS)

# Points of home advantage, applied inside the rating fit only (the ratings it
# produces are neutral-venue). PROVISIONAL: the NFL system uses a well
# established 3.0, but the URC has no equivalent settled number, and its
# handicaps are wider. Run ``calibrate.py`` once a season of handicaps is
# entered and set this from the fitted value rather than leaving the guess in.
HOME_ADVANTAGE = 5.0

# Extra points charged to a side crossing between Europe and South Africa.
# Off by default so the model is a straight port; ``calibrate.py`` estimates it.
LONG_HAUL_PENALTY = 0.0

SEASON_COLUMNS = ["round", "date", "home", "away", "neutral",
                  "opening_line", "closing_line", "line_source",
                  "home_score", "away_score",
                  "home_turnovers_conceded", "away_turnovers_conceded",
                  "home_turnovers_won", "away_turnovers_won"]

# Values for ``line_source``. Blank means a handicap quoted as a handicap; the
# NFL project's hardest judgement call was about exactly this kind of
# provenance (opening vs closing lines), so it is recorded rather than implied.
LINE_QUOTED = ""
LINE_INFERRED = "inferred-1x2"


def model_line(opening: pd.Series, closing: pd.Series) -> pd.Series:
    """The handicap the model runs on: the close, or the open until there is one.

    ``nfl_report`` is defined on the closing line, falling back to the opening
    line only where the close is missing, and this is the same rule. The close
    carries what the open predates - in the URC chiefly the team sheets, which
    moved round 1 of 2026-27 by up to 13 points. The opening line is otherwise
    kept only as a record of how the market moved.
    """
    return closing.fillna(opening)


def available_seasons() -> list[int]:
    return sorted(
        int(m.group(1))
        for f in DATA_DIR.glob("season_*.csv")
        if (m := re.match(r"season_(\d{4})\.csv", f.name))
    )


def season_label(year: int) -> str:
    return f"{year}-{(year + 1) % 100:02d}"


# --- loading -----------------------------------------------------------------

def load_season(year: int) -> pd.DataFrame:
    """One row per match, with blanks preserved as missing values."""
    df = pd.read_csv(DATA_DIR / f"season_{year}.csv")
    for col in SEASON_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    df = df.dropna(subset=["home", "away"]).copy()
    if df.empty:
        return df.assign(line=np.nan, season=year, played=False, playoff=False,
                         long_haul=False)

    for col in ("home", "away"):
        df[col] = df[col].map(teams.canonical)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["round"] = pd.to_numeric(df["round"], errors="coerce").astype("Int64")
    for col in ("opening_line", "closing_line"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["line"] = model_line(df["opening_line"], df["closing_line"])
    for col in ("home_score", "away_score",
                "home_turnovers_conceded", "away_turnovers_conceded",
                "home_turnovers_won", "away_turnovers_won"):
        df[col] = pd.array(pd.to_numeric(df[col], errors="coerce"), dtype="Int64")

    df["neutral"] = (df["neutral"].astype(str).str.strip().str.upper()
                     .isin({"Y", "YES", "TRUE", "1", "N/V"}))
    df["played"] = df["home_score"].notna() & df["away_score"].notna()
    df["playoff"] = df["round"].fillna(0).astype(int) > REGULAR_ROUNDS
    df["long_haul"] = [teams.is_long_haul(r.home, r.away) for r in df.itertuples()]
    df["season"] = year

    for col, what in (("round", "round number"), ("date", "date")):
        blank = df[col].isna()
        if blank.any():
            first = df[blank].iloc[0]
            raise ValueError(
                f"season_{year}.csv: {int(blank.sum())} row(s) with no {what}, "
                f"first is {first['home']} v {first['away']}. Every match needs "
                f"a date: the previous-match and season-to-date factors are "
                f"ordered by it, not by round number.")
    return df


# --- cross-season factors ----------------------------------------------------

def add_lgt(combined: pd.DataFrame) -> pd.DataFrame:
    """Last Game Turnover: each club's own net turnover margin last time out.

    A club's margin is **its own turnovers conceded minus its own turnovers
    won** - how much ball it leaked, net of how much it won back.

    That is the NFL system's definition (``giveaways - takeaways``) read
    literally. The NFL implementation computes it as a *differential* between
    the two sides instead, which is equivalent there because a giveaway by one
    team is by definition a takeaway by the other. **Rugby breaks that
    identity**: a knock-on into touch is a turnover conceded that nobody won,
    and across the 15 URC matches first loaded here ``home_conceded`` never
    once equalled ``away_won``, differing by as much as 8. The differential is
    therefore not a shortcut to the same number in rugby, it is a different
    quantity - and the two disagree on the *sign*, which is all this factor
    reads, in 8 of 30 club-matches. So the definition carries over, not the
    shortcut, and both columns are required.

    Carried across the season boundary, but only within a contiguous run of
    seasons, so the first round of a block starts at 0 (no previous match).

    ``lgt_unknown`` marks the different case of a previous match that exists on
    the schedule but has no turnover count - not yet played, or not yet typed
    in. The value exists and we simply do not have it, so the system declines to
    pick rather than treating the factor as neutral. Two of the five factors
    read this, so guessing it would mean betting on dead inputs.
    """
    g = combined.copy()
    # float (not Int64) so a match with no counts contributes NaN, which flows
    # through to lgt_unknown rather than to a typed NA.
    for side in ("home", "away"):
        g[f"{side}_net_to"] = (g[f"{side}_turnovers_conceded"]
                               - g[f"{side}_turnovers_won"]).astype(float)

    long = pd.concat([
        g[["order", "block", "home", "home_net_to"]]
         .rename(columns={"home": "team", "home_net_to": "net_to"}),
        g[["order", "block", "away", "away_net_to"]]
         .rename(columns={"away": "team", "away_net_to": "net_to"}),
    ]).sort_values(["team", "order"])

    by_team = long.groupby(["team", "block"])
    long["lgt"] = by_team["net_to"].shift()
    long["lgt_unknown"] = (by_team.cumcount() > 0) & long["lgt"].isna()

    for side in ("home", "away"):
        key = long.rename(columns={"team": side, "lgt": f"{side}_lgt",
                                   "lgt_unknown": f"{side}_lgt_unknown"})
        g = g.merge(key[["order", side, f"{side}_lgt", f"{side}_lgt_unknown"]],
                    on=["order", side], how="left")

    # ``+ 0.0`` folds the -0.0 that negating a zero margin produces.
    g[["home_lgt", "away_lgt"]] = g[["home_lgt", "away_lgt"]].fillna(0.0) + 0.0
    g["lgt_unknown"] = (g["home_lgt_unknown"].fillna(False)
                        | g["away_lgt_unknown"].fillna(False))
    return g.drop(columns=["home_net_to", "away_net_to",
                           "home_lgt_unknown", "away_lgt_unknown"])


def _week_key(day: pd.Timestamp) -> int:
    """The match-week a fixture belongs to, as a sortable ``yyyyww`` integer."""
    iso = day.isocalendar()
    return int(iso[0]) * 100 + int(iso[1])


def add_powers(combined: pd.DataFrame) -> pd.DataFrame:
    """Weighted least-squares power ratings, refit before every match-week.

    The model is ``line = away_power - home_power - home_edge``, where the home
    edge is ``HOME_ADVANTAGE`` (zero at a neutral venue) plus
    ``LONG_HAUL_PENALTY`` when the away side crosses between hemispheres. The
    last four match-weeks of handicaps are weighted 1, 1/2, 1/4, 1/8.

    The window is four **match-weeks**, not four round numbers, because in the
    URC a round is a scheduling label rather than a date. 2026-27's round 8
    puts six matches on 26-27 December and the two South African derbies on
    20-21 February, after rounds 9, 10 and 11 have been played. Keyed on the
    round number those two February matches would be rated on October form, and
    rounds 9-11 would be rated on a match that had not happened. Calendar weeks
    split a split round correctly, and they make the season boundary fall out
    for free: the previous season's last weeks are simply the previous weeks.

    Only weeks holding priced **regular-season** matches are used as sources. A
    playoff week has four, two or one match between mismatched sides - too thin
    to pin sixteen ratings, and the same reason the NFL version seeds a new
    season from the previous one's regular weeks.
    """
    g = combined.copy()
    clubs = sorted(set(g["home"]) | set(g["away"]))
    idx = {t: i for i, t in enumerate(clubs)}
    g["week_key"] = [_week_key(d) for d in g["date"]]

    usable = g["line"].notna() & ~g["playoff"]
    weeks_in_block = {blk: sorted(set(d["week_key"]))
                      for blk, d in g[usable].groupby("block")}
    by_week = {key: d for key, d in g[usable].groupby(["block", "week_key"])}

    def fit(block: int, week_key: int) -> dict[str, float] | None:
        prior = [w for w in weeks_in_block.get(block, []) if w < week_key]
        rows, targets = [], []
        for weight, wk in zip(FIT_WEIGHTS, prior[-FIT_WEEKS:][::-1]):
            rw = np.sqrt(weight)
            for r in by_week[(block, wk)].itertuples():
                row = np.zeros(len(clubs))
                row[idx[r.away]] += rw
                row[idx[r.home]] -= rw
                rows.append(row)
                edge = 0.0 if r.neutral else HOME_ADVANTAGE
                if r.long_haul and not r.neutral:
                    edge += LONG_HAUL_PENALTY
                targets.append(rw * (r.line + edge))
        if not rows:
            return None
        p, *_ = np.linalg.lstsq(np.array(rows), np.array(targets), rcond=None)
        return {t: p[i] for t, i in idx.items()}

    cache: dict[tuple[int, int], dict | None] = {}
    home_power, away_power = [], []
    for r in g.itertuples():
        key = (r.block, r.week_key)
        if key not in cache:
            cache[key] = fit(*key)
        ratings = cache[key]
        if ratings is None:
            home_power.append(np.nan)
            away_power.append(np.nan)
        else:  # one decimal, as the published NFL reports display and use
            home_power.append(round(ratings[r.home], 1))
            away_power.append(round(ratings[r.away], 1))
    g["home_power"] = home_power
    g["away_power"] = away_power
    return g.drop(columns=["week_key"])


# --- assembling the report ---------------------------------------------------

def build_reports() -> dict[int, pd.DataFrame]:
    seasons = available_seasons()
    frames = [load_season(y) for y in seasons]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return {}

    combined = pd.concat(frames, ignore_index=True)
    # Chronological, NOT by round: a club's previous match and its running
    # cover record are both "what had happened by then", and the URC's round
    # numbers are not in date order (see add_powers).
    combined = combined.sort_values(["season", "date", "round"]).reset_index(drop=True)
    combined["order"] = np.arange(len(combined))

    # Block id = contiguous run of seasons; LGT carries within a block only.
    present = sorted(combined["season"].unique())
    block_of, b = {}, 0
    for i, s in enumerate(present):
        if i and s != present[i - 1] + 1:
            b += 1
        block_of[s] = b
    combined["block"] = combined["season"].map(block_of)

    combined = add_powers(add_lgt(combined))

    reports: dict[int, pd.DataFrame] = {}
    for year in present:
        season = combined[combined["season"] == year].copy()
        # A season in progress carries its whole remaining schedule, which the
        # factors need but the report should not list: keep the matches that are
        # actionable - already played, or priced so the system can pick them.
        season = season[season["played"] | season["line"].notna()].copy()
        if season.empty:
            continue

        stdc = model.season_to_date_covers(season)   # STDC resets each season
        season["home_stdc"] = stdc["home_stdc_calc"].fillna(0.0).values
        season["away_stdc"] = stdc["away_stdc_calc"].fillna(0.0).values

        season["system_num"] = [
            model.system_number(r.home_lgt, r.home_stdc, r.home_power,
                                r.away_lgt, r.away_stdc, r.away_power, r.line)
            for r in season.itertuples()
        ]
        picks = season["system_num"].map(model.pick)
        picks[season["line"].isna()] = None          # nothing to bet against
        picks[season["home_power"].isna()] = None    # no ratings yet
        picks[season["lgt_unknown"]] = None          # turnovers missing: decline
        season["system_bet"] = [
            r.home if p == "home" else r.away if p == "away" else None
            for r, p in zip(season.itertuples(), picks)
        ]
        season["result"] = [
            model.grade(r.system_num, r.home_score, r.away_score, r.line)
            if isinstance(r.system_bet, str) else None
            for r in season.itertuples()
        ]

        reports[year] = pd.DataFrame({
            "date": season["date"].dt.strftime("%Y-%m-%d"),
            "round": season["round"].astype(int),
            "home": season["home"], "away": season["away"],
            "opening_line": season["opening_line"], "line": season["line"],
            "home_score": season["home_score"], "away_score": season["away_score"],
            "home_lgt": season["home_lgt"], "home_stdc": season["home_stdc"],
            "home_power": season["home_power"], "away_lgt": season["away_lgt"],
            "away_stdc": season["away_stdc"], "away_power": season["away_power"],
            "system_num": season["system_num"], "system_bet": season["system_bet"],
            "result": season["result"], "lgt_unknown": season["lgt_unknown"],
        }).reset_index(drop=True)
    return reports


def main() -> None:
    reports = build_reports()
    if not reports:
        print("no season data yet - add data/season_<year>.csv and re-run")
        return
    for year, report in reports.items():
        bets = int(report["system_bet"].notna().sum())
        w = int((report["result"] == "W").sum())
        l = int((report["result"] == "L").sum())
        wr = f"{w / (w + l):.1%}" if (w + l) else "n/a"
        held = int(report["lgt_unknown"].sum())
        out = DATA_DIR / f"report_{year}.csv"
        report.drop(columns=["lgt_unknown"]).to_csv(out, index=False)
        print(f"{season_label(year)}: {len(report):3d} matches | {bets:2d} bets | "
              f"{w:2d}-{l:2d} ({wr}) | {w - 1.1 * l:+5.1f}u"
              + (f" | {held} held back for missing turnovers" if held else ""))


if __name__ == "__main__":
    main()
