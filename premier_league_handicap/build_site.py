"""Generate the data payload embedded in index.html (the GitHub Pages site).

Reads the handicap and results CSVs via analysis.py, computes the season
standings, per-game adjusted points and cumulative totals, and injects the
JSON blob between the __DATA__ markers in index.html.

Usage:  python build_site.py
"""

import json
import math
from pathlib import Path

from analysis import GAMES_PER_SEASON, load_all

HERE = Path(__file__).parent
SITE = HERE / "index.html"

SHORT_NAMES = {
    "Manchester City": "Man City",
    "Manchester Utd": "Man Utd",
    "Newcastle Utd": "Newcastle",
    "Nott'ham Forest": "Forest",
    "Crystal Palace": "Palace",
    "Leeds United": "Leeds",
}

DATA_START = "/*__DATA__*/"
DATA_END = "/*__END_DATA__*/"


def build_payload() -> dict:
    handicaps, results, games, standings = load_all()

    teams = []
    for _, row in standings.iterrows():
        name = row["team"]
        tg = games[games["team"] == name].sort_values("match_no")
        team_games = [
            {
                "d": g["date"].strftime("%d %b"),
                "o": SHORT_NAMES.get(g["opponent"], g["opponent"]),
                "v": "H" if g["venue"] == "Home" else "A",
                "gf": int(g["gf"]),
                "ga": int(g["ga"]),
                "p": int(g["base_points"]),
            }
            for _, g in tg.iterrows()
        ]
        teams.append(
            {
                "name": name,
                "short": SHORT_NAMES.get(name, name),
                "handicap": int(row["handicap"]),
                "actual": int(row["actual_points"]),
                "adjusted": int(row["adjusted_points"]),
                "actualRank": int(row["actual_rank"]),
                "adjRank": int(row["adjusted_rank"]),
                "w": int(row["wins"]),
                "dr": int(row["draws"]),
                "l": int(row["losses"]),
                "gf": int(row["goals_for"]),
                "ga": int(row["goals_against"]),
                "games": team_games,
                "cum": [round(v, 3) for v in tg["cum_adjusted_points"]],
                "cumActual": [int(v) for v in tg["cum_base_points"]],
            }
        )

    actual_pts = [t["actual"] for t in teams]
    handicap_pts = [t["handicap"] for t in teams]
    n = len(teams)
    mean_a = sum(actual_pts) / n
    mean_h = sum(handicap_pts) / n
    cov = sum(
        (a - mean_a) * (h - mean_h) for a, h in zip(actual_pts, handicap_pts)
    )
    var_a = sum((a - mean_a) ** 2 for a in actual_pts)
    var_h = sum((h - mean_h) ** 2 for h in handicap_pts)
    corr = cov / math.sqrt(var_a * var_h)

    return {
        "season": "2025-2026",
        "gamesPerSeason": GAMES_PER_SEASON,
        "meanAdjusted": round(sum(t["adjusted"] for t in teams) / n, 2),
        "handicapActualCorr": round(corr, 3),
        "teams": teams,
    }


def main() -> None:
    payload = build_payload()
    blob = json.dumps(payload, separators=(",", ":"))

    html = SITE.read_text(encoding="utf-8")
    start = html.index(DATA_START) + len(DATA_START)
    end = html.index(DATA_END)
    SITE.write_text(html[:start] + blob + html[end:], encoding="utf-8")
    print(
        f"Injected {len(blob):,} bytes of data "
        f"({len(payload['teams'])} teams) into {SITE.name}"
    )


if __name__ == "__main__":
    main()
