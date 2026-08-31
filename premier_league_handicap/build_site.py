"""Render the static handicap page for a season.

Reads the season's handicap and results CSVs via analysis.py, computes the
standings, per-game adjusted points and cumulative totals, then fills
template.html with that data and writes the season's index.html.

Usage:
    python build_site.py                 # build every season that has results
    python build_site.py 2026_2027       # build one season
"""

import json
import math
import sys
from pathlib import Path

from analysis import (GAMES_PER_SEASON, SEASONS, has_results, load_all,
                      load_handicaps, market_view, season_dir)

HERE = Path(__file__).parent
TEMPLATE = HERE / "template.html"

# Every season gets an archive page at <season>/index.html. The most recent
# season that has results is ALSO written to index.html, so the folder's
# canonical Pages URL always shows the latest season.

SHORT_NAMES = {
    "Manchester City": "Man City",
    "Manchester Utd": "Man Utd",
    "Newcastle Utd": "Newcastle",
    "Nott'ham Forest": "Forest",
    "Crystal Palace": "Palace",
    "Leeds United": "Leeds",
    "Sheffield Utd": "Sheffield Utd",
}

DATA_START = "/*__DATA__*/"
DATA_END = "/*__END_DATA__*/"


def market_payload(handicaps) -> dict:
    """Odds market on winning the handicap league, if this season has odds."""
    if "odds" not in handicaps.columns:
        return {}
    mv = market_view(handicaps)
    return {
        "overround": round(mv.attrs["overround"], 4),
        "book": round(mv.attrs["book"], 4),
        "rows": [
            {
                "name": r["team"],
                "short": SHORT_NAMES.get(r["team"], r["team"]),
                "handicap": int(r["handicap"]),
                "odds": float(r["odds"]),
                "implied": round(float(r["implied"]), 5),
                "fairProb": round(float(r["fair_prob"]), 5),
                "fairOdds": round(float(r["fair_odds"]), 2),
            }
            for _, r in mv.iterrows()
        ],
    }


def preseason_payload(season: str) -> dict:
    """Payload for a season that has handicaps (and maybe odds) but no results."""
    handicaps = load_handicaps(season)
    teams = []
    for _, row in handicaps.sort_values(["handicap", "team"]).iterrows():
        entry = {
            "name": row["team"],
            "short": SHORT_NAMES.get(row["team"], row["team"]),
            "handicap": int(row["handicap"]),
            "perGame": round(float(row["handicap"]) / GAMES_PER_SEASON, 4),
        }
        if "odds" in handicaps.columns:
            entry["odds"] = float(row["odds"])
        teams.append(entry)
    return {
        "season": SEASONS[season]["label"],
        "hasResults": False,
        "complete": False,
        "maxPlayed": 0,
        "gamesPerSeason": GAMES_PER_SEASON,
        "teams": teams,
        "market": market_payload(handicaps),
    }


def build_payload(season: str) -> dict:
    handicaps, results, games, standings = load_all(season)
    max_played = int(standings["played"].max())
    complete = bool((standings["played"] == GAMES_PER_SEASON).all())

    teams = []
    for _, row in standings.iterrows():
        name = row["team"]
        tg = games[games["team"] == name].sort_values("match_no")
        entry = {
            "name": name,
            "short": SHORT_NAMES.get(name, name),
            "handicap": int(row["handicap"]),
            "actual": int(row["actual_points"]),
            "adjusted": int(round(row["adjusted_full"])),
            "adjustedFull": int(round(row["adjusted_full"])),
            "adjustedToDate": round(float(row["adjusted_points"]), 3),
            "handicapToDate": round(float(row["handicap_to_date"]), 3),
            "played": int(row["played"]),
            "actualRank": int(row["actual_rank"]),
            "adjRank": int(row["adjusted_rank"]),
            "w": int(row["wins"]),
            "dr": int(row["draws"]),
            "l": int(row["losses"]),
            "gf": int(row["goals_for"]),
            "ga": int(row["goals_against"]),
            "games": [
                {
                    "d": g["date"].strftime("%d %b"),
                    "o": SHORT_NAMES.get(g["opponent"], g["opponent"]),
                    "v": "H" if g["venue"] == "Home" else "A",
                    "gf": int(g["gf"]),
                    "ga": int(g["ga"]),
                    "p": int(g["base_points"]),
                }
                for _, g in tg.iterrows()
            ],
            "cum": [round(v, 3) for v in tg["cum_adjusted_points"]],
            "cumActual": [int(v) for v in tg["cum_base_points"]],
        }
        if "odds" in standings.columns:
            entry["odds"] = float(row["odds"])
        teams.append(entry)

    actual_pts = [t["actual"] for t in teams]
    handicap_pts = [t["handicap"] for t in teams]
    n = len(teams)
    mean_a = sum(actual_pts) / n
    mean_h = sum(handicap_pts) / n
    cov = sum((a - mean_a) * (h - mean_h) for a, h in zip(actual_pts, handicap_pts))
    var_a = sum((a - mean_a) ** 2 for a in actual_pts)
    var_h = sum((h - mean_h) ** 2 for h in handicap_pts)
    corr = cov / math.sqrt(var_a * var_h) if var_a and var_h else 0.0

    return {
        "season": SEASONS[season]["label"],
        "hasResults": True,
        "complete": complete,
        "maxPlayed": max_played,
        "gamesPerSeason": GAMES_PER_SEASON,
        "meanAdjusted": round(sum(t["adjustedToDate"] for t in teams) / n, 2),
        "handicapActualCorr": round(corr, 3),
        "teams": teams,
        "market": market_payload(handicaps),
    }


def copy_for(payload: dict) -> dict:
    label = payload["season"]
    played = payload["maxPlayed"]
    if not payload["hasResults"]:
        return {
            "SEASON_LABEL": label,
            "STATUS": "before a ball is kicked",
            "INTRO": (
                f"The {label} handicaps are set and the market has priced them. No "
                "games have been played yet, so this page covers the handicaps "
                "themselves and what the odds say about them; the adjusted table and "
                "the game-by-game race appear as results come in."
            ),
        }
    if payload["complete"]:
        status = "final"
        intro = (
            f"This page re-scores the finished {label} season on that basis: the "
            "adjusted table, how the race unfolded game by game, and how well the "
            "handicaps actually levelled the field."
        )
    else:
        games_txt = "1 game played" if played == 1 else f"{played} games played"
        status = games_txt
        intro = (
            f"This page re-scores the {label} season as it happens &mdash; {games_txt} "
            "so far: the adjusted table, how the race is unfolding game by game, and "
            "how well the handicaps are levelling the field."
        )
    return {"SEASON_LABEL": label, "STATUS": status, "INTRO": intro}


def render(season: str, payload: dict, others: list) -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    copy = copy_for(payload)
    copy["SEASON_NAV"] = "".join(
        f'<a href="{href}">{SEASONS[s]["label"]}</a>' for s, href in others
    )
    for key, value in copy.items():
        html = html.replace("{{" + key + "}}", value)

    blob = json.dumps(payload, separators=(",", ":"))
    start = html.index(DATA_START) + len(DATA_START)
    end = html.index(DATA_END)
    return html[:start] + blob + html[end:]


def main() -> None:
    # A season is buildable once it has handicaps; results just add sections.
    wanted = [
        s for s in (sys.argv[1:] or list(SEASONS))
        if (season_dir(s) / "season_handicap.csv").exists()
    ]
    if not wanted:
        raise SystemExit("No season had a season_handicap.csv to build from.")

    latest = max(wanted)
    for season in wanted:
        payload = build_payload(season) if has_results(season) else preseason_payload(season)
        # links to the other seasons, relative to <season>/index.html
        others = [
            (s, ("../" if s == latest else f"../{s}/"))
            for s in sorted(wanted, reverse=True) if s != season
        ]
        html = render(season, payload, others)
        archive = HERE / season / "index.html"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text(html, encoding="utf-8")
        state = ("complete" if payload["complete"]
                 else "in progress" if payload["hasResults"] else "pre-season")
        print(
            f"{season}: {len(payload['teams'])} teams, up to {payload['maxPlayed']} "
            f"games ({state}) -> {season}/index.html"
        )

        if season == latest:
            # same page at the canonical URL; links need root-relative paths
            root_others = [
                (s, f"{s}/") for s in sorted(wanted, reverse=True) if s != season
            ]
            (HERE / "index.html").write_text(
                render(season, payload, root_others), encoding="utf-8"
            )
            print(f"{season}: also written to index.html (latest season)")


if __name__ == "__main__":
    main()
