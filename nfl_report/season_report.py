"""Build a season report from raw data: results+turnovers and betting odds.

This is the Phase-2/3 pipeline from the README roadmap: instead of parsing
Aaron Brown's published sheets, it produces the same report table from raw
inputs, using the validated factor engine in ``model.py``:

* ``data/results_<year>.csv``  – pro-football-reference games table (winner /
  loser orientation, points, TOW/TOL turnovers).
* ``data/odds_<year>.csv``     – aussportsbetting odds export. The spread is
  ``Home Line Close`` (positive = home underdog, matching the report's Line),
  falling back to ``Home Line Open`` where the close is missing. Games with no
  line at all keep their factor columns but can recommend no bet.

Power ratings are fit per week exactly as the demonstration describes — a
weighted least-squares fit of the last four weeks' lines (weights 1, 1/2, 1/4,
1/8) with a 3-point home-field advantage inside the fit (0 for neutral-venue
games) — and the factor compares the line to the raw rating difference, which
is the construction that reproduces the published 2016 implied lines at 0.999
correlation (see README).

Until the prior season's file is added, week 1 has no last-game turnovers
(LGT = 0) and no power ratings (factor neutral); weeks 2-4 fit on shortened
windows. The published reports carry both across from the prior season.

Run: ``python season_report.py``  -> ``data/report_2025.csv``
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import model

DATA_DIR = Path(__file__).parent / "data"

PLAYOFF_WEEKS = {"WildCard": 19, "Division": 20, "ConfChamp": 21, "SuperBowl": 22}
FIT_WEIGHTS = [1.0, 0.5, 0.25, 0.125]  # most recent week first
HOME_FIELD = 3.0  # points, inside the rating fit only


def nickname(full_name: str) -> str:
    """'New England Patriots' -> 'Patriots' (works for all 32 current teams)."""
    return full_name.split()[-1]


def load_results(year: int) -> pd.DataFrame:
    """PFR games table -> one row per game in home/away orientation."""
    df = pd.read_csv(DATA_DIR / f"results_{year}.csv")
    df = df.dropna(subset=["Pts"])  # header/divider rows (e.g. 'Playoffs')
    df["Date"] = pd.to_datetime(df["Date"])
    df["Week"] = df["Week"].replace(PLAYOFF_WEEKS).astype(int)

    # '@' = winner was the away team; 'N' = neutral venue (orientation is fixed
    # against the odds file in build_report); blank = winner at home.
    away_won = df["venue_marker"] == "@"
    df["home"] = np.where(away_won, df["Loser/tie"], df["Winner/tie"])
    df["away"] = np.where(away_won, df["Winner/tie"], df["Loser/tie"])
    df["home_score"] = np.where(away_won, df["Pts.1"], df["Pts"]).astype(int)
    df["away_score"] = np.where(away_won, df["Pts"], df["Pts.1"]).astype(int)
    df["home_giveaways"] = np.where(away_won, df["TOL"], df["TOW"]).astype(int)
    df["away_giveaways"] = np.where(away_won, df["TOW"], df["TOL"]).astype(int)
    df["neutral"] = df["venue_marker"] == "N"

    cols = ["Week", "Date", "home", "away", "home_score", "away_score",
            "home_giveaways", "away_giveaways", "neutral"]
    return df[cols].sort_values(["Week", "Date"]).reset_index(drop=True)


def load_odds(year: int) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / f"odds_{year}.csv", parse_dates=["Date"])
    df["line"] = df["Home Line Close"].fillna(df["Home Line Open"])
    df["line_is_open"] = df["Home Line Close"].isna() & df["Home Line Open"].notna()
    df["neutral_odds"] = df["Neutral Venue?"] == "Y"
    return df[["Date", "Home Team", "Away Team", "Home Score", "Away Score",
               "line", "line_is_open", "neutral_odds"]]


def merge_odds(results: pd.DataFrame, odds: pd.DataFrame) -> pd.DataFrame:
    """Attach the line to each game.

    The two files disagree on some game dates by a day (the odds export uses a
    different timezone for late and international games), and neutral-venue
    games (e.g. the Super Bowl) can be oriented differently. So each game is
    matched on the team pair within +/-1 day, preferring same orientation and
    the nearest date; on a swapped match the game is re-oriented to the odds
    file's designated home team (the convention the published reports use).
    """
    rows = []
    for r in results.itertuples():
        same = odds[(odds["Home Team"] == r.home) & (odds["Away Team"] == r.away)]
        swapped = odds[(odds["Home Team"] == r.away) & (odds["Away Team"] == r.home)]
        cand = pd.concat([same.assign(swap=False), swapped.assign(swap=True)])
        cand = cand[(cand["Date"] - r.Date).abs() <= pd.Timedelta(days=1)]
        if cand.empty:
            raise ValueError(f"no odds row for {r.Date.date()} {r.home} v {r.away}")
        best = cand.assign(dd=(cand["Date"] - r.Date).abs()) \
                   .sort_values(["dd", "swap"]).iloc[0]

        row = r._asdict()
        del row["Index"]
        if best["swap"]:
            row["home"], row["away"] = r.away, r.home
            row["home_score"], row["away_score"] = r.away_score, r.home_score
            row["home_giveaways"], row["away_giveaways"] = (
                r.away_giveaways, r.home_giveaways)
        row["line"] = best["line"]
        row["line_is_open"] = best["line_is_open"]
        row["neutral"] = bool(r.neutral or best["neutral_odds"])

        # Cross-check: both files carry scores; a mismatch means a bad join.
        if not (pd.isna(best["Home Score"])
                or (row["home_score"] == best["Home Score"]
                    and row["away_score"] == best["Away Score"])):
            raise ValueError(f"score mismatch for {r.Date.date()} {r.home} v {r.away}")
        rows.append(row)

    return pd.DataFrame(rows)


def add_lgt(games: pd.DataFrame) -> pd.DataFrame:
    """Last Game Turnover: each team's net giveaways in its previous game.

    First game of the season has no prior game here; the published reports
    carry the value over from the prior season's last game (0 until that
    file is added).
    """
    games = games.copy()
    games["home_net_to"] = games["home_giveaways"] - games["away_giveaways"]

    long = pd.concat([
        games[["Week", "Date", "home", "home_net_to"]]
        .rename(columns={"home": "team", "home_net_to": "net_to"}),
        games[["Week", "Date", "away", "home_net_to"]]
        .rename(columns={"away": "team", "home_net_to": "net_to"})
        .assign(net_to=lambda d: -d["net_to"]),
    ]).sort_values(["team", "Week", "Date"])
    long["lgt"] = long.groupby("team")["net_to"].shift()

    for side in ("home", "away"):
        key = long.rename(columns={"team": side, "lgt": f"{side}_lgt"})
        games = games.merge(
            key[["Week", "Date", side, f"{side}_lgt"]], on=["Week", "Date", side])
    games[["home_lgt", "away_lgt"]] = games[["home_lgt", "away_lgt"]].fillna(0.0)
    return games.drop(columns=["home_net_to"])


def fit_week_powers(games: pd.DataFrame, week: int) -> dict[str, float] | None:
    """Neutral-field ratings entering ``week``: weighted LSQ on up to the last
    four played weeks' lines, line + HFA ~ rating(away) - rating(home)."""
    prior_weeks = sorted(w for w in games["Week"].unique() if w < week)[-4:]
    if not prior_weeks:
        return None
    weight = {w: FIT_WEIGHTS[i] for i, w in enumerate(sorted(prior_weeks, reverse=True))}
    window = games[games["Week"].isin(prior_weeks) & games["line"].notna()]

    teams = sorted(set(games["home"]) | set(games["away"]))
    tix = {t: i for i, t in enumerate(teams)}
    rows, targets = [], []
    for r in window.itertuples():
        w = np.sqrt(weight[r.Week])
        row = np.zeros(len(teams))
        row[tix[r.away]] += w
        row[tix[r.home]] -= w
        rows.append(row)
        targets.append(w * (r.line + (0.0 if r.neutral else HOME_FIELD)))
    p, *_ = np.linalg.lstsq(np.array(rows), np.array(targets), rcond=None)
    return {t: p[i] for t, i in tix.items()}


def add_powers(games: pd.DataFrame) -> pd.DataFrame:
    games = games.copy()
    home_power, away_power = [], []
    ratings_by_week = {
        wk: fit_week_powers(games, wk) for wk in games["Week"].unique()
    }
    for r in games.itertuples():
        ratings = ratings_by_week[r.Week]
        if ratings is None:
            home_power.append(np.nan)
            away_power.append(np.nan)
        else:
            # one decimal, as the published reports display (and effectively use)
            home_power.append(round(ratings[r.home], 1))
            away_power.append(round(ratings[r.away], 1))
    games["home_power"] = home_power
    games["away_power"] = away_power
    return games


def build_report(year: int) -> pd.DataFrame:
    games = merge_odds(load_results(year), load_odds(year))
    games = add_lgt(games)
    games = add_powers(games)

    # STDC from prior covers in the file (model handles pushes / missing lines)
    tmp = games.rename(columns={})  # model expects home/away/.../line columns
    tmp = model.season_to_date_covers(tmp)
    games["home_stdc"] = tmp["home_stdc_calc"].fillna(0.0)
    games["away_stdc"] = tmp["away_stdc_calc"].fillna(0.0)

    games["system_num"] = [
        model.system_number(r.home_lgt, r.home_stdc, r.home_power,
                            r.away_lgt, r.away_stdc, r.away_power, r.line)
        for r in games.itertuples()
    ]
    picks = games["system_num"].map(model.pick)
    no_line = games["line"].isna()
    picks[no_line] = None  # nothing to bet against without a spread
    games["system_bet"] = [
        nickname(r.home) if p == "home" else nickname(r.away) if p == "away" else None
        for r, p in zip(games.itertuples(), picks)
    ]
    games["result"] = [
        model.grade(r.system_num, r.home_score, r.away_score, r.line)
        if isinstance(r.system_bet, str) else None
        for r in games.itertuples()
    ]

    out = pd.DataFrame({
        "date": games["Date"].dt.strftime("%y-%m-%d"),
        "home": games["home"].map(nickname),
        "away": games["away"].map(nickname),
        "line": games["line"],
        "home_score": games["home_score"],
        "away_score": games["away_score"],
        "home_lgt": games["home_lgt"],
        "home_stdc": games["home_stdc"],
        "home_power": games["home_power"],
        "away_lgt": games["away_lgt"],
        "away_stdc": games["away_stdc"],
        "away_power": games["away_power"],
        "system_num": games["system_num"],
        "system_bet": games["system_bet"],
        "result": games["result"],
    })
    return out


def main() -> None:
    year = 2025
    report = build_report(year)
    out = DATA_DIR / f"report_{year}.csv"
    report.to_csv(out, index=False)

    bets = report["system_bet"].notna()
    w = (report["result"] == "W").sum()
    l = (report["result"] == "L").sum()
    no_line = report["line"].isna().sum()
    print(f"{year}: {len(report)} games -> {out.name}")
    print(f"  bets: {bets.sum()}  W-L: {w}-{l}  pushes: {bets.sum() - w - l}")
    print(f"  win rate: {w / (w + l):.1%}  profit at full juice: {w - 1.1 * l:+.1f}u")
    print(f"  games with no line in the odds file (not bettable): {no_line}")
    if no_line:
        missing = report[report["line"].isna()][["date", "home", "away"]]
        print(missing.to_string(index=False))


if __name__ == "__main__":
    main()
