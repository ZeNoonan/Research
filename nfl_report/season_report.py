"""Build season reports from raw data: results+turnovers and betting odds.

Instead of parsing Aaron Brown's published sheets, this produces the same report
table from raw inputs for every season that has data in ``data/``, using the
validated factor engine in ``model.py``:

* ``data/results_<year>.csv``  – pro-football-reference games table (winner /
  loser orientation, points, TOW/TOL turnovers).
* ``data/odds_<year>.csv``     – aussportsbetting odds export. The spread is
  ``Home Line Close`` (positive = home underdog, matching the report's Line),
  falling back to ``Home Line Open`` where the close is missing. Games with no
  line at all keep their factor columns but recommend no bet.

``<year>`` is the season's start year (Sept), matching the published reports
(``report_2016`` is the Sept 2016 – Feb 2017 season).

Prior-season carryover
----------------------
When the previous season's files are present, the two season-spanning factors
are seeded from them, exactly as the published reports do:

* **LGT** (last-game turnovers) carries over the season boundary — a team's
  week-1 value is its net turnovers in its last game of the prior season,
  playoffs included.
* **Power ratings** for the new season's first weeks are fit on the prior
  season's last regular weeks until the new season has four of its own.

Power ratings are fit per week as the demonstration describes — a weighted
least-squares fit of the last four weeks' lines (weights 1, 1/2, 1/4, 1/8) with
a 3-point home-field advantage inside the fit (0 for neutral venues) — and the
factor compares the line to the raw rating difference, the construction that
reproduces the published 2016 implied lines at 0.999 correlation (see README).

The earliest season with no predecessor (and any season whose predecessor is
missing) has a blank week 1 (LGT = 0, power neutral), as before.

Run: ``python season_report.py``  ->  ``data/report_<year>.csv`` for each season.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

import model

DATA_DIR = Path(__file__).parent / "data"

PLAYOFF_ORDER = ["WildCard", "Division", "ConfChamp", "SuperBowl"]
FIT_WEIGHTS = [1.0, 0.5, 0.25, 0.125]  # most recent source week first
HOME_FIELD = 3.0  # points, inside the rating fit only

# Franchises whose nickname is not just the last word of the full name, or that
# changed name across these seasons. Washington went Redskins -> Football Team
# -> Commanders; we use the current nickname throughout so the franchise tracks
# cleanly across the boundary. (Oakland/Las Vegas Raiders already share
# "Raiders".)
NAME_FIXES = {
    "Washington Redskins": "Commanders",
    "Washington Football Team": "Commanders",
}


def nickname(full_name: str) -> str:
    """Full team name -> canonical nickname (stable across relocations/renames)."""
    return NAME_FIXES.get(full_name, full_name.split()[-1])


def available_years() -> list[int]:
    years = sorted(
        int(m.group(1))
        for f in DATA_DIR.glob("results_*.csv")
        if (m := re.match(r"results_(\d{4})\.csv", f.name))
        and (DATA_DIR / f"odds_{m.group(1)}.csv").exists()
    )
    return years


# --- loading a single season -------------------------------------------------

def assign_weeks(week_col: pd.Series) -> pd.Series:
    """Numeric regular weeks unchanged; playoff rounds become max_regular + 1..4."""
    reg = pd.to_numeric(week_col, errors="coerce")
    max_reg = int(reg.max())
    wk = reg.copy()
    for offset, label in enumerate(PLAYOFF_ORDER, start=1):
        wk = wk.mask(week_col == label, max_reg + offset)
    return wk.astype(int)


def load_results(year: int) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / f"results_{year}.csv")
    df = df.dropna(subset=["Pts"])  # header/divider rows (e.g. 'Playoffs')
    df["Date"] = pd.to_datetime(df["Date"])
    df["Week"] = assign_weeks(df["Week"])

    away_won = df["venue_marker"] == "@"       # '@' = winner was the away team
    df["home"] = np.where(away_won, df["Loser/tie"], df["Winner/tie"])
    df["away"] = np.where(away_won, df["Winner/tie"], df["Loser/tie"])
    df["home_score"] = np.where(away_won, df["Pts.1"], df["Pts"]).astype(int)
    df["away_score"] = np.where(away_won, df["Pts"], df["Pts.1"]).astype(int)
    df["home_giveaways"] = np.where(away_won, df["TOL"], df["TOW"]).astype(int)
    df["away_giveaways"] = np.where(away_won, df["TOW"], df["TOL"]).astype(int)
    df["neutral"] = df["venue_marker"] == "N"  # neutral venue (e.g. Super Bowl)
    for col in ("home", "away"):
        df[col] = df[col].map(nickname)

    df["season"] = year
    cols = ["season", "Week", "Date", "home", "away", "home_score", "away_score",
            "home_giveaways", "away_giveaways", "neutral"]
    return df[cols].rename(columns={"Week": "week"})


def load_odds(year: int) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / f"odds_{year}.csv", parse_dates=["Date"])
    df["line"] = df["Home Line Close"].fillna(df["Home Line Open"])
    df["line_is_open"] = df["Home Line Close"].isna() & df["Home Line Open"].notna()
    df["neutral_odds"] = df["Neutral Venue?"] == "Y"
    for col in ("Home Team", "Away Team"):
        df[col] = df[col].map(nickname)
    return df[["Date", "Home Team", "Away Team", "Home Score", "Away Score",
               "line", "line_is_open", "neutral_odds"]]


def merge_season(year: int, warn: list | None = None) -> pd.DataFrame:
    """Attach the betting line to each game of one season.

    The two files disagree on some game dates by a day (the odds export uses a
    different timezone for late and international games) and can orient
    neutral-venue games differently, so each game is matched on the team pair
    within +/-1 day, preferring same orientation and the nearest date. On a
    swapped match the game is re-oriented to the odds file's designated home
    team (the convention the published reports use).

    Scores come from the results file (pro-football-reference); the odds file is
    used only for the line. A handful of odds rows carry wrong scores, so a
    score disagreement is recorded in ``warn`` rather than raised — the team
    pair plus date already pins the join down (no team plays twice in two days).
    """
    results, odds = load_results(year), load_odds(year)
    rows = []
    for r in results.itertuples():
        same = odds[(odds["Home Team"] == r.home) & (odds["Away Team"] == r.away)]
        swapped = odds[(odds["Home Team"] == r.away) & (odds["Away Team"] == r.home)]
        cand = pd.concat([same.assign(swap=False), swapped.assign(swap=True)])
        cand = cand[(cand["Date"] - r.Date).abs() <= pd.Timedelta(days=1)]
        if cand.empty:
            raise ValueError(f"{year}: no odds row for {r.Date.date()} {r.home} v {r.away}")
        best = cand.assign(dd=(cand["Date"] - r.Date).abs()).sort_values(["dd", "swap"]).iloc[0]

        row = {k: getattr(r, k) for k in
               ("season", "week", "Date", "home", "away", "home_score", "away_score",
                "home_giveaways", "away_giveaways", "neutral")}
        if best["swap"]:
            row["home"], row["away"] = r.away, r.home
            row["home_score"], row["away_score"] = r.away_score, r.home_score
            row["home_giveaways"], row["away_giveaways"] = r.away_giveaways, r.home_giveaways
        row["line"] = best["line"]
        row["neutral"] = bool(r.neutral or best["neutral_odds"])
        if warn is not None and not pd.isna(best["Home Score"]) and (
                row["home_score"] != best["Home Score"] or row["away_score"] != best["Away Score"]):
            warn.append(f"{year} {r.Date.date()} {row['home']} v {row['away']}: "
                        f"results {row['home_score']}-{row['away_score']} vs "
                        f"odds {int(best['Home Score'])}-{int(best['Away Score'])}")
        rows.append(row)
    return pd.DataFrame(rows).rename(columns={"Date": "date"})


# --- cross-season factors on the combined log --------------------------------

def add_lgt(combined: pd.DataFrame) -> pd.DataFrame:
    """Last Game Turnover: each team's net giveaways in its previous game.

    The previous game is taken across the season boundary (a team's week-1 value
    is its last game of the prior season), but only within a contiguous run of
    seasons: the carry does not jump a missing year, so the first week of a block
    of seasons has LGT 0.
    """
    g = combined.copy()
    g["home_net_to"] = g["home_giveaways"] - g["away_giveaways"]
    long = pd.concat([
        g[["order", "block", "home", "home_net_to"]]
         .rename(columns={"home": "team", "home_net_to": "net_to"}),
        g[["order", "block", "away", "home_net_to"]]
         .rename(columns={"away": "team", "home_net_to": "net_to"})
         .assign(net_to=lambda d: -d["net_to"]),
    ]).sort_values(["team", "order"])
    long["lgt"] = long.groupby(["team", "block"])["net_to"].shift()

    for side in ("home", "away"):
        key = long.rename(columns={"team": side, "lgt": f"{side}_lgt"})
        g = g.merge(key[["order", side, f"{side}_lgt"]], on=["order", side], how="left")
    g[["home_lgt", "away_lgt"]] = g[["home_lgt", "away_lgt"]].fillna(0.0)
    return g.drop(columns=["home_net_to"])


def _source_weeks(season: int, week: int, season_weeks: dict[int, list[int]],
                  regular_weeks: dict[int, list[int]], prior: dict[int, int]) -> list[tuple[int, int]]:
    """Up to four (season, week) source weeks for the power fit, most recent first.

    Same-season weeks before ``week`` are used first (preserving the validated
    within-season behaviour); if fewer than four, the prior season's most recent
    *regular* weeks fill the rest (the season-boundary seed).
    """
    picked = [(season, w) for w in season_weeks[season] if w < week][::-1][:4]
    s = season
    while len(picked) < 4 and s in prior:
        s = prior[s]
        for w in reversed(regular_weeks[s]):
            picked.append((s, w))
            if len(picked) == 4:
                break
    return picked


def add_powers(combined: pd.DataFrame) -> pd.DataFrame:
    g = combined.copy()
    teams = sorted(set(g["home"]) | set(g["away"]))
    tix = {t: i for i, t in enumerate(teams)}

    season_weeks = {s: sorted(d["week"].unique()) for s, d in g.groupby("season")}
    regular_weeks = {
        s: sorted(w for w in season_weeks[s] if w <= d["week"].max() - len(PLAYOFF_ORDER))
        for s, d in g.groupby("season")
    }
    seasons = sorted(season_weeks)
    prior = {s: s - 1 for s in seasons if (s - 1) in season_weeks}  # consecutive years only
    by_week = {(s, w): d for (s, w), d in g.groupby(["season", "week"])}

    def fit(season: int, week: int) -> dict[str, float] | None:
        sources = _source_weeks(season, week, season_weeks, regular_weeks, prior)
        if not sources:
            return None
        rows, targets = [], []
        for weight, (s, w) in zip(FIT_WEIGHTS, sources):
            window = by_week[(s, w)]
            window = window[window["line"].notna()]
            rw = np.sqrt(weight)
            for r in window.itertuples():
                row = np.zeros(len(teams))
                row[tix[r.away]] += rw
                row[tix[r.home]] -= rw
                rows.append(row)
                targets.append(rw * (r.line + (0.0 if r.neutral else HOME_FIELD)))
        if not rows:
            return None
        p, *_ = np.linalg.lstsq(np.array(rows), np.array(targets), rcond=None)
        return {t: p[i] for t, i in tix.items()}

    cache: dict[tuple[int, int], dict | None] = {}
    home_power, away_power = [], []
    for r in g.itertuples():
        key = (r.season, r.week)
        if key not in cache:
            cache[key] = fit(*key)
        ratings = cache[key]
        if ratings is None:
            home_power.append(np.nan)
            away_power.append(np.nan)
        else:  # one decimal, as the published reports display (and effectively use)
            home_power.append(round(ratings[r.home], 1))
            away_power.append(round(ratings[r.away], 1))
    g["home_power"] = home_power
    g["away_power"] = away_power
    return g


# --- assembling the report ---------------------------------------------------

def build_reports(warn: list | None = None) -> dict[int, pd.DataFrame]:
    years = available_years()
    combined = pd.concat([merge_season(y, warn) for y in years], ignore_index=True)
    combined = combined.sort_values(["season", "week", "date"]).reset_index(drop=True)
    combined["order"] = np.arange(len(combined))  # global chronological index

    # Block id = contiguous run of seasons; LGT carries within a block only.
    block_of, b = {}, 0
    for i, s in enumerate(years):
        if i and s != years[i - 1] + 1:
            b += 1
        block_of[s] = b
    combined["block"] = combined["season"].map(block_of)

    combined = add_lgt(combined)
    combined = add_powers(combined)

    reports: dict[int, pd.DataFrame] = {}
    for year in years:
        season = combined[combined["season"] == year].copy()
        # STDC resets each season: compute on this season's games only.
        stdc = model.season_to_date_covers(season)
        season["home_stdc"] = stdc["home_stdc_calc"].fillna(0.0).values
        season["away_stdc"] = stdc["away_stdc_calc"].fillna(0.0).values

        season["system_num"] = [
            model.system_number(r.home_lgt, r.home_stdc, r.home_power,
                                r.away_lgt, r.away_stdc, r.away_power, r.line)
            for r in season.itertuples()
        ]
        picks = season["system_num"].map(model.pick)
        picks[season["line"].isna()] = None  # nothing to bet against without a spread
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
            "date": pd.to_datetime(season["date"]).dt.strftime("%y-%m-%d"),
            "week": season["week"],
            "home": season["home"], "away": season["away"], "line": season["line"],
            "home_score": season["home_score"], "away_score": season["away_score"],
            "home_lgt": season["home_lgt"], "home_stdc": season["home_stdc"],
            "home_power": season["home_power"], "away_lgt": season["away_lgt"],
            "away_stdc": season["away_stdc"], "away_power": season["away_power"],
            "system_num": season["system_num"], "system_bet": season["system_bet"],
            "result": season["result"],
        }).reset_index(drop=True)
    return reports


def main() -> None:
    warn: list[str] = []
    for year, report in build_reports(warn).items():
        out = DATA_DIR / f"report_{year}.csv"
        report.to_csv(out, index=False)
        bets = report["system_bet"].notna()
        w = (report["result"] == "W").sum()
        l = (report["result"] == "L").sum()
        no_line = int(report["line"].isna().sum())
        wr = f"{w / (w + l):.1%}" if (w + l) else "n/a"
        print(f"{year}: {len(report):3d} games | {bets.sum():2d} bets | "
              f"{w:2d}-{l:2d} ({wr}) | {w - 1.1 * l:+5.1f}u"
              + (f" | {no_line} games w/o line" if no_line else ""))
    if warn:
        print(f"\n{len(warn)} odds rows with scores differing from results "
              f"(line still used; scores taken from results):")
        for msg in warn:
            print(f"  {msg}")


if __name__ == "__main__":
    main()
