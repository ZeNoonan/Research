"""Data loading and handicap computations for the 2025-2026 Premier League analysis.

The handicap is a fixed number of bonus points added to a team's season total.
For the game-by-game view it is spread evenly across the 38 games
(handicap / 38 per game), so the per-game adjusted points sum back to
actual points + handicap.
"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
HANDICAP_FILE = DATA_DIR / "season_handicap_2025_2026.csv"
RESULTS_FILE = DATA_DIR / "premier_league_results_2025_2026.csv"

GAMES_PER_SEASON = 38
WIN_PTS, DRAW_PTS, LOSS_PTS = 3, 1, 0

# Handicap-file team name -> results-file (football-data) team name.
NAME_TO_RESULTS = {
    "Manchester City": "Man City",
    "Manchester Utd": "Man United",
    "Newcastle Utd": "Newcastle",
    "Nott'ham Forest": "Nott'm Forest",
    "Leeds United": "Leeds",
}


def load_handicaps() -> pd.DataFrame:
    df = pd.read_csv(HANDICAP_FILE)
    df["results_name"] = df["team"].map(lambda t: NAME_TO_RESULTS.get(t, t))
    return df


def load_results() -> pd.DataFrame:
    df = pd.read_csv(RESULTS_FILE, encoding="utf-8-sig")
    cols = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
    df = df[cols].copy()
    df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y")
    return df.sort_values("Date").reset_index(drop=True)


def _points_for(scored: int, conceded: int) -> int:
    if scored > conceded:
        return WIN_PTS
    if scored == conceded:
        return DRAW_PTS
    return LOSS_PTS


def build_team_games(results: pd.DataFrame, handicaps: pd.DataFrame) -> pd.DataFrame:
    """One row per team per game (760 rows), with base and handicap-adjusted points."""
    per_game = dict(
        zip(handicaps["results_name"], handicaps["handicap"] / GAMES_PER_SEASON)
    )
    display_name = dict(zip(handicaps["results_name"], handicaps["team"]))

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
    """Season table with actual points, handicap and adjusted points."""
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
    agg = agg.merge(handicaps[["team", "handicap"]], on="team", how="left")
    agg["adjusted_points"] = agg["actual_points"] + agg["handicap"]

    actual_order = agg.sort_values(
        ["actual_points", "goal_difference", "goals_for"], ascending=False
    )["team"].tolist()
    actual_rank = {team: i + 1 for i, team in enumerate(actual_order)}
    agg["actual_rank"] = agg["team"].map(actual_rank)

    agg = agg.sort_values(
        ["adjusted_points", "goal_difference", "goals_for"], ascending=False
    ).reset_index(drop=True)
    agg.insert(0, "adjusted_rank", agg.index + 1)
    agg["rank_change"] = agg["actual_rank"] - agg["adjusted_rank"]
    return agg


def load_all():
    handicaps = load_handicaps()
    results = load_results()
    games = build_team_games(results, handicaps)
    standings = build_standings(games, handicaps)
    return handicaps, results, games, standings
