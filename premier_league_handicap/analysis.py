"""Data loading and handicap computations for the Premier League handicap analysis.

The handicap is a fixed number of bonus points added to a team's season total.
It is spread evenly across the 38 games of a season (handicap / 38 per game),
so per-game adjusted points sum back to actual points + handicap.

Seasons may be partially played. Everything here is expressed "to date":

    handicap_to_date = handicap * played / 38
    adjusted_points  = actual_points + handicap_to_date

For a completed season played == 38, so this reduces to actual + handicap.
"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"

GAMES_PER_SEASON = 38
WIN_PTS, DRAW_PTS, LOSS_PTS = 3, 1, 0

SEASONS = {
    "2025_2026": {"label": "2025-2026", "short": "25/26"},
    "2026_2027": {"label": "2026-2027", "short": "26/27"},
}
CURRENT_SEASON = "2026_2027"

# Handicap-file team name -> results-file (football-data) team name.
# Only names that actually differ need an entry.
NAME_TO_RESULTS = {
    "Manchester City": "Man City",
    "Manchester Utd": "Man United",
    "Newcastle Utd": "Newcastle",
    "Nott'ham Forest": "Nott'm Forest",
    "Leeds United": "Leeds",
    "Sheffield Utd": "Sheffield United",
    "West Bromwich": "West Brom",
}

# Columns we accept for a minimal, hand-written results file, mapped onto the
# football-data.co.uk names used internally.
MINIMAL_COLUMNS = {
    "date": "Date",
    "home": "HomeTeam",
    "hometeam": "HomeTeam",
    "away": "AwayTeam",
    "awayteam": "AwayTeam",
    "homegoals": "FTHG",
    "hg": "FTHG",
    "fthg": "FTHG",
    "awaygoals": "FTAG",
    "ag": "FTAG",
    "ftag": "FTAG",
}


def season_dir(season: str) -> Path:
    if season not in SEASONS:
        raise ValueError(f"Unknown season {season!r}; expected one of {sorted(SEASONS)}")
    return DATA_DIR / season


def has_results(season: str) -> bool:
    return (season_dir(season) / "results.csv").exists()


def load_handicaps(season: str) -> pd.DataFrame:
    df = pd.read_csv(season_dir(season) / "season_handicap.csv")
    df["results_name"] = df["team"].map(lambda t: NAME_TO_RESULTS.get(t, t))
    if df["team"].duplicated().any():
        dupes = sorted(df.loc[df["team"].duplicated(), "team"])
        raise ValueError(f"Duplicate teams in {season} handicap file: {dupes}")
    return df


def load_results(season: str) -> pd.DataFrame:
    """Read a results file.

    Accepts the football-data.co.uk layout (HomeTeam/AwayTeam/FTHG/FTAG/...)
    or a minimal hand-written CSV with date, home, away and goal columns.
    """
    df = pd.read_csv(season_dir(season) / "results.csv", encoding="utf-8-sig")
    if not {"HomeTeam", "AwayTeam", "FTHG", "FTAG"}.issubset(df.columns):
        renames = {
            c: MINIMAL_COLUMNS[c.strip().lower().replace(" ", "").replace("_", "")]
            for c in df.columns
            if c.strip().lower().replace(" ", "").replace("_", "") in MINIMAL_COLUMNS
        }
        df = df.rename(columns=renames)
    missing = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"} - set(df.columns)
    if missing:
        raise ValueError(
            f"{season} results.csv is missing column(s) {sorted(missing)}. "
            "Expected football-data.co.uk columns (Date, HomeTeam, AwayTeam, "
            "FTHG, FTAG) or date/home/away/home_goals/away_goals."
        )

    df = df[["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]].copy()
    # Drop unplayed fixtures (blank scores) so a part-season file is usable.
    df = df.dropna(subset=["FTHG", "FTAG"])
    df["FTHG"] = df["FTHG"].astype(int)
    df["FTAG"] = df["FTAG"].astype(int)
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, format="mixed")
    return df.sort_values("Date").reset_index(drop=True)


def _points_for(scored: int, conceded: int) -> int:
    if scored > conceded:
        return WIN_PTS
    if scored == conceded:
        return DRAW_PTS
    return LOSS_PTS


def build_team_games(results: pd.DataFrame, handicaps: pd.DataFrame) -> pd.DataFrame:
    """One row per team per game, with base and handicap-adjusted points."""
    per_game = dict(
        zip(handicaps["results_name"], handicaps["handicap"] / GAMES_PER_SEASON)
    )
    display_name = dict(zip(handicaps["results_name"], handicaps["team"]))

    played_names = set(results["HomeTeam"]) | set(results["AwayTeam"])
    unknown = sorted(played_names - set(per_game))
    if unknown:
        raise ValueError(
            f"Teams in results.csv with no handicap entry: {unknown}. "
            f"Add them to the handicap file or to NAME_TO_RESULTS."
        )

    rows = []
    for _, m in results.iterrows():
        for team, opp, gf, ga, venue in (
            (m["HomeTeam"], m["AwayTeam"], m["FTHG"], m["FTAG"], "Home"),
            (m["AwayTeam"], m["HomeTeam"], m["FTAG"], m["FTHG"], "Away"),
        ):
            base = _points_for(gf, ga)
            outcome = "Win" if base == WIN_PTS else "Draw" if base == DRAW_PTS else "Loss"
            rows.append(
                {
                    "team": display_name.get(team, team),
                    "date": m["Date"],
                    "venue": venue,
                    "opponent": display_name.get(opp, opp),
                    "gf": int(gf),
                    "ga": int(ga),
                    "result": outcome,
                    "base_points": base,
                    "handicap_per_game": per_game.get(team, 0.0),
                    "adjusted_points": base + per_game.get(team, 0.0),
                }
            )

    games = pd.DataFrame(rows).sort_values(["team", "date"]).reset_index(drop=True)
    games["match_no"] = games.groupby("team").cumcount() + 1
    games["cum_base_points"] = games.groupby("team")["base_points"].cumsum()
    games["cum_adjusted_points"] = games.groupby("team")["adjusted_points"].cumsum()
    return games


def build_standings(games: pd.DataFrame, handicaps: pd.DataFrame) -> pd.DataFrame:
    """Standings to date, with actual points, handicap and adjusted points.

    ``handicap_to_date`` is the share of the handicap earned so far
    (handicap * played / 38); ``adjusted_points`` adds that to actual points.
    ``adjusted_full`` is the season-end total if every remaining game is played.
    """
    agg = (
        games.groupby("team")
        .agg(
            played=("match_no", "max"),
            wins=("result", lambda s: (s == "Win").sum()),
            draws=("result", lambda s: (s == "Draw").sum()),
            losses=("result", lambda s: (s == "Loss").sum()),
            goals_for=("gf", "sum"),
            goals_against=("ga", "sum"),
            actual_points=("base_points", "sum"),
        )
        .reset_index()
    )
    agg["goal_difference"] = agg["goals_for"] - agg["goals_against"]

    keep = ["team", "handicap"] + (["odds"] if "odds" in handicaps.columns else [])
    agg = agg.merge(handicaps[keep], on="team", how="left")

    agg["handicap_to_date"] = agg["handicap"] * agg["played"] / GAMES_PER_SEASON
    agg["adjusted_points"] = agg["actual_points"] + agg["handicap_to_date"]
    agg["adjusted_full"] = agg["actual_points"] + agg["handicap"]

    actual_order = agg.sort_values(
        ["actual_points", "goal_difference", "goals_for"], ascending=False
    )["team"].tolist()
    agg["actual_rank"] = agg["team"].map({t: i + 1 for i, t in enumerate(actual_order)})

    agg = agg.sort_values(
        ["adjusted_points", "goal_difference", "goals_for"], ascending=False
    ).reset_index(drop=True)
    agg.insert(0, "adjusted_rank", agg.index + 1)
    agg["rank_change"] = agg["actual_rank"] - agg["adjusted_rank"]
    return agg


def load_all(season: str = "2025_2026"):
    handicaps = load_handicaps(season)
    results = load_results(season)
    games = build_team_games(results, handicaps)
    standings = build_standings(games, handicaps)
    return handicaps, results, games, standings
