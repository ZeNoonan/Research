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
FIT_WEIGHTS = [1.0, 0.5, 0.25, 0.125]  # most recent source round first
FIT_ROUNDS = len(FIT_WEIGHTS)

# Points of home advantage, applied inside the rating fit only (the ratings it
# produces are neutral-venue). PROVISIONAL: the NFL system uses a well
# established 3.0, but the URC has no equivalent settled number, and its
# handicaps are wider. Run ``calibrate.py`` once a season of handicaps is
# entered and set this from the fitted value rather than leaving the guess in.
HOME_ADVANTAGE = 5.0

# Extra points charged to a side crossing between Europe and South Africa.
# Off by default so the model is a straight port; ``calibrate.py`` estimates it.
LONG_HAUL_PENALTY = 0.0

SEASON_COLUMNS = ["round", "date", "home", "away", "neutral", "line",
                  "home_score", "away_score",
                  "home_turnovers_conceded", "away_turnovers_conceded"]


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
        return df.assign(season=year, played=False, playoff=False, long_haul=False)

    for col in ("home", "away"):
        df[col] = df[col].map(teams.canonical)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["round"] = pd.to_numeric(df["round"], errors="coerce").astype("Int64")
    df["line"] = pd.to_numeric(df["line"], errors="coerce")
    for col in ("home_score", "away_score",
                "home_turnovers_conceded", "away_turnovers_conceded"):
        df[col] = pd.array(pd.to_numeric(df[col], errors="coerce"), dtype="Int64")

    df["neutral"] = (df["neutral"].astype(str).str.strip().str.upper()
                     .isin({"Y", "YES", "TRUE", "1", "N/V"}))
    df["played"] = df["home_score"].notna() & df["away_score"].notna()
    df["playoff"] = df["round"].fillna(0).astype(int) > REGULAR_ROUNDS
    df["long_haul"] = [teams.is_long_haul(r.home, r.away) for r in df.itertuples()]
    df["season"] = year

    if df["round"].isna().any():
        missing = df[df["round"].isna()]
        raise ValueError(
            f"season_{year}.csv: {len(missing)} row(s) with no round number, "
            f"first is {missing.iloc[0]['home']} v {missing.iloc[0]['away']}")
    return df


# --- cross-season factors ----------------------------------------------------

def add_lgt(combined: pd.DataFrame) -> pd.DataFrame:
    """Last Game Turnover: each club's net turnovers conceded last time out.

    Carried across the season boundary, but only within a contiguous run of
    seasons, so the first round of a block starts at 0 (no previous match).

    ``lgt_unknown`` marks the different case of a previous match that exists on
    the schedule but has no turnover count - not yet played, or not yet typed
    in. The value exists and we simply do not have it, so the system declines to
    pick rather than treating the factor as neutral. Two of the five factors
    read this, so guessing it would mean betting on dead inputs.
    """
    g = combined.copy()
    # Net turnovers conceded, zero-sum between the two sides. float (not Int64)
    # so an unplayed match contributes NaN rather than a typed NA.
    g["home_net_to"] = (g["home_turnovers_conceded"]
                        - g["away_turnovers_conceded"]).astype(float)

    long = pd.concat([
        g[["order", "block", "home", "home_net_to"]]
         .rename(columns={"home": "team", "home_net_to": "net_to"}),
        g[["order", "block", "away", "home_net_to"]]
         .rename(columns={"away": "team", "home_net_to": "net_to"})
         .assign(net_to=lambda d: -d["net_to"]),
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
    return g.drop(columns=["home_net_to", "home_lgt_unknown", "away_lgt_unknown"])


def _source_rounds(season: int, rnd: int, season_rounds: dict[int, list[int]],
                   regular_rounds: dict[int, list[int]],
                   prior: dict[int, int]) -> list[tuple[int, int]]:
    """Up to four (season, round) sources for the power fit, most recent first."""
    picked = [(season, r) for r in season_rounds[season] if r < rnd][::-1][:FIT_ROUNDS]
    s = season
    while len(picked) < FIT_ROUNDS and s in prior:
        s = prior[s]
        for r in reversed(regular_rounds[s]):
            picked.append((s, r))
            if len(picked) == FIT_ROUNDS:
                break
    return picked


def add_powers(combined: pd.DataFrame) -> pd.DataFrame:
    """Weighted least-squares power ratings, refit before every round.

    The model is ``line = away_power - home_power - home_edge``, where the home
    edge is ``HOME_ADVANTAGE`` (zero at a neutral venue) plus
    ``LONG_HAUL_PENALTY`` when the away side crosses between hemispheres. The
    last four rounds of handicaps are weighted 1, 1/2, 1/4, 1/8.
    """
    g = combined.copy()
    clubs = sorted(set(g["home"]) | set(g["away"]))
    idx = {t: i for i, t in enumerate(clubs)}

    season_rounds = {s: sorted(d["round"].unique()) for s, d in g.groupby("season")}
    regular_rounds = {s: sorted(d.loc[~d["playoff"], "round"].unique())
                      for s, d in g.groupby("season")}
    prior = {s: s - 1 for s in season_rounds if (s - 1) in season_rounds}
    by_round = {(s, r): d for (s, r), d in g.groupby(["season", "round"])}

    def fit(season: int, rnd: int) -> dict[str, float] | None:
        rows, targets = [], []
        for weight, key in zip(FIT_WEIGHTS,
                               _source_rounds(season, rnd, season_rounds,
                                              regular_rounds, prior)):
            window = by_round[key]
            rw = np.sqrt(weight)
            for r in window[window["line"].notna()].itertuples():
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
        key = (r.season, int(r.round))
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
    return g


# --- assembling the report ---------------------------------------------------

def build_reports() -> dict[int, pd.DataFrame]:
    seasons = available_seasons()
    frames = [load_season(y) for y in seasons]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return {}

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["season", "round", "date"]).reset_index(drop=True)
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
            "home": season["home"], "away": season["away"], "line": season["line"],
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
