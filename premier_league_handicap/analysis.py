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

# Results files come from different sources (football-data.co.uk, FBref, hand
# typed) which each spell clubs differently, so both the handicap file and the
# results are resolved to a canonical club key before being joined. Add a
# spelling here rather than renaming anything in the source data.
CLUB_ALIASES = {
    "arsenal": ["arsenal"],
    "aston villa": ["aston villa", "villa"],
    "bournemouth": ["bournemouth", "afc bournemouth"],
    "brentford": ["brentford"],
    "brighton": ["brighton", "brighton and hove albion", "brighton & hove albion"],
    "burnley": ["burnley"],
    "chelsea": ["chelsea"],
    "coventry city": ["coventry", "coventry city"],
    "crystal palace": ["crystal palace", "palace"],
    "everton": ["everton"],
    "fulham": ["fulham"],
    "hull city": ["hull", "hull city"],
    "ipswich town": ["ipswich", "ipswich town"],
    "leeds united": ["leeds", "leeds united", "leeds utd"],
    "leicester city": ["leicester", "leicester city"],
    "liverpool": ["liverpool"],
    "luton town": ["luton", "luton town"],
    "manchester city": ["man city", "manchester city"],
    "manchester united": ["man united", "man utd", "manchester utd", "manchester united"],
    "newcastle united": ["newcastle", "newcastle utd", "newcastle united"],
    "nottingham forest": [
        "nottingham", "nottingham forest", "nott'm forest", "nott'ham forest",
        "nottm forest", "forest",
    ],
    "sheffield united": ["sheffield united", "sheffield utd"],
    "southampton": ["southampton"],
    "sunderland": ["sunderland"],
    "tottenham": ["tottenham", "tottenham hotspur", "spurs"],
    "west bromwich albion": ["west brom", "west bromwich", "west bromwich albion"],
    "west ham united": ["west ham", "west ham united", "west ham utd"],
    "wolverhampton": ["wolves", "wolverhampton", "wolverhampton wanderers"],
}

def _normalise(name: str) -> str:
    """Lower-case, drop punctuation and any 'FC'/'AFC', squeeze whitespace."""
    cleaned = "".join(
        c.lower() if (c.isalnum() or c.isspace()) else " " for c in str(name)
    )
    parts = [p for p in cleaned.split() if p not in {"fc", "afc"}]
    return " ".join(parts)


# Aliases are normalised on the way in, so "Nott'ham Forest" and "Nott'm
# Forest" both reduce to the same lookup key as the canonical spelling.
_ALIAS_LOOKUP = {}
for _canonical, _spellings in CLUB_ALIASES.items():
    for _s in {_canonical, *_spellings}:
        _ALIAS_LOOKUP[_normalise(_s)] = _canonical


def canonical_team(name: str) -> str:
    """Map any spelling of a club onto its canonical key."""
    key = _normalise(name)
    if key in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[key]
    raise KeyError(
        f"Unrecognised club name {name!r} (normalised {key!r}). "
        f"Add the spelling to CLUB_ALIASES in analysis.py."
    )

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
    df["club"] = df["team"].map(canonical_team)
    if df["club"].duplicated().any():
        dupes = sorted(df.loc[df["club"].duplicated(), "team"])
        raise ValueError(f"Two handicap rows resolve to the same club: {dupes}")
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

    # FBref-style export: Home / Away / "3-0" (any dash) in one Score column.
    if {"Home", "Away", "Score"}.issubset(df.columns):
        df = df.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam"})
        goals = (
            df["Score"].astype("string")
            .str.replace(r"[\u2010-\u2015\u2212]", "-", regex=True)
            .str.extract(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
        )
        df["FTHG"], df["FTAG"] = goals[0], goals[1]

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
    # Blank separator rows and unplayed fixtures both drop out here, so a
    # part-season export with future fixtures still listed works as-is.
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    df = df[df["HomeTeam"].astype(str).str.strip() != ""]
    df["FTHG"] = df["FTHG"].astype(int)
    df["FTAG"] = df["FTAG"].astype(int)
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, format="mixed")
    for col in ("HomeTeam", "AwayTeam"):
        df[col] = df[col].map(canonical_team)
    return df.sort_values("Date").reset_index(drop=True)


def _points_for(scored: int, conceded: int) -> int:
    if scored > conceded:
        return WIN_PTS
    if scored == conceded:
        return DRAW_PTS
    return LOSS_PTS


def build_team_games(results: pd.DataFrame, handicaps: pd.DataFrame) -> pd.DataFrame:
    """One row per team per game, with base and handicap-adjusted points."""
    per_game = dict(zip(handicaps["club"], handicaps["handicap"] / GAMES_PER_SEASON))
    display_name = dict(zip(handicaps["club"], handicaps["team"]))

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


def market_view(handicaps: pd.DataFrame) -> pd.DataFrame:
    """Implied probabilities from decimal odds on winning the handicap league.

    ``implied`` is the raw book percentage (1 / odds). Those sum to more than
    1 by the bookmaker's margin, so ``fair_prob`` renormalises them to sum to
    1 and ``fair_odds`` is the corresponding margin-free price.
    """
    if "odds" not in handicaps.columns:
        raise ValueError("This season's handicap file has no odds column.")

    df = handicaps[["team", "handicap", "odds"]].copy()
    df["implied"] = 1.0 / df["odds"]
    book = df["implied"].sum()
    df["fair_prob"] = df["implied"] / book
    df["fair_odds"] = 1.0 / df["fair_prob"]
    df.attrs["book"] = float(book)
    df.attrs["overround"] = float(book - 1.0)
    return df.sort_values(["odds", "team"]).reset_index(drop=True)


def load_all(season: str = "2025_2026"):
    handicaps = load_handicaps(season)
    results = load_results(season)
    games = build_team_games(results, handicaps)
    standings = build_standings(games, handicaps)
    return handicaps, results, games, standings
