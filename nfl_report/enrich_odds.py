"""Fill gaps in the aussportsbetting odds files from the nflverse schedule.

``data/schedule_lines.csv`` is a slimmed nflverse ``games`` export (2018–2026)
carrying, per game, the closing spread and whether the game was played at a
neutral venue. It is a second, independent source and is used only to repair
two specific gaps in ``data/odds_<year>.csv``:

* **Missing lines** — where a game has neither a closing nor an opening line,
  the nflverse spread is written into ``Home Line Close``. Without it the game
  can never be bet; 14 games of 2025 were in this state.
* **Neutral venues** — international games have no home-field advantage, and
  the power fit zeroes its 3-point term for them. The odds export flags only
  some of them; nflverse flags all.

Existing lines are **never** overwritten: a line we already have always wins,
so seasons keep the book they were built on.

Sign convention: nflverse ``spread_line`` is positive when the home team is
favoured, the opposite of this project's ``line``, so it is negated.

Games are matched on the team pair within ±1 day — the two sources date late
and international kick-offs a day apart.

Run: ``python enrich_odds.py`` (then ``season_report.py`` and ``build_site.py``).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
SCHEDULE = DATA_DIR / "schedule_lines.csv"

# nflverse team codes -> the nicknames used throughout this project.
NICKNAME = {
    "ARI": "Cardinals", "ATL": "Falcons", "BAL": "Ravens", "BUF": "Bills",
    "CAR": "Panthers", "CHI": "Bears", "CIN": "Bengals", "CLE": "Browns",
    "DAL": "Cowboys", "DEN": "Broncos", "DET": "Lions", "GB": "Packers",
    "HOU": "Texans", "IND": "Colts", "JAX": "Jaguars", "KC": "Chiefs",
    "LA": "Rams", "LAC": "Chargers", "LV": "Raiders", "MIA": "Dolphins",
    "MIN": "Vikings", "NE": "Patriots", "NO": "Saints", "NYG": "Giants",
    "NYJ": "Jets", "OAK": "Raiders", "PHI": "Eagles", "PIT": "Steelers",
    "SD": "Chargers", "SEA": "Seahawks", "SF": "49ers", "STL": "Rams",
    "TB": "Buccaneers", "TEN": "Titans", "WAS": "Commanders",
}

ODDS_COLUMNS = ["Date", "Home Team", "Away Team", "Home Score", "Away Score",
                "Home Line Open", "Home Line Close", "Neutral Venue?", "Playoff Game?"]


def parse_dates(col: pd.Series) -> pd.Series:
    """nflverse exports date as ISO (2026-09-13) or day-first (13/09/2026)."""
    iso = pd.to_datetime(col, format="%Y-%m-%d", errors="coerce")
    if iso.notna().all():
        return iso
    return pd.to_datetime(col, format="%d/%m/%Y")


def load_schedule() -> pd.DataFrame:
    s = pd.read_csv(SCHEDULE)
    s["date"] = parse_dates(s["gameday"])
    s["home"] = s["home_team"].map(NICKNAME)
    s["away"] = s["away_team"].map(NICKNAME)
    s["line"] = -s["spread_line"]  # nflverse is positive-home-favoured
    return s[["season", "date", "home", "away", "line", "location"]]


def nickname_of(full_name: str) -> str:
    return "Commanders" if full_name.endswith(("Redskins", "Football Team")) \
        else full_name.split()[-1]


def enrich_year(year: int, schedule: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Return (updated odds frame, lines filled, neutral flags added)."""
    odds = pd.read_csv(DATA_DIR / f"odds_{year}.csv", parse_dates=["Date"])
    # An all-empty flag column reads as float64, which will not take "Y".
    for flag in ("Neutral Venue?", "Playoff Game?"):
        odds[flag] = odds[flag].astype(object)
    season = schedule[schedule["season"] == year]

    filled = flagged = 0
    for i, row in odds.iterrows():
        home, away = nickname_of(row["Home Team"]), nickname_of(row["Away Team"])
        cand = season[(season["home"] == home) & (season["away"] == away)]
        cand = cand[(cand["date"] - row["Date"]).abs() <= pd.Timedelta(days=1)]
        if cand.empty:
            continue
        match = cand.iloc[0]

        no_line = pd.isna(row["Home Line Close"]) and pd.isna(row["Home Line Open"])
        if no_line and not pd.isna(match["line"]):
            odds.at[i, "Home Line Close"] = match["line"]
            filled += 1
        if match["location"] == "Neutral" and row.get("Neutral Venue?") != "Y":
            odds.at[i, "Neutral Venue?"] = "Y"
            flagged += 1

    return odds, filled, flagged


def main() -> None:
    schedule = load_schedule()
    years = sorted(int(p.stem.split("_")[1]) for p in DATA_DIR.glob("odds_*.csv"))
    for year in years:
        odds, filled, flagged = enrich_year(year, schedule)
        if filled or flagged:
            odds[ODDS_COLUMNS].to_csv(DATA_DIR / f"odds_{year}.csv", index=False)
        note = ", ".join(
            p for p in (f"{filled} line(s) filled" if filled else "",
                        f"{flagged} neutral venue(s) flagged" if flagged else "")
            if p) or "nothing to repair"
        print(f"{year}: {note}")


if __name__ == "__main__":
    main()
