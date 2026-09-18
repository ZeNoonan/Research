"""Fill gaps in the aussportsbetting odds files from the nflverse schedule.

``data/schedule_lines.csv`` is a slimmed nflverse ``games`` export (2018–2026)
carrying, per game, the closing spread and whether the game was played at a
neutral venue. It is a second, independent source and is used only to repair
two specific gaps in ``data/odds_<year>.csv``:

* **Missing lines** — where a game has neither a closing nor an opening line,
  the nflverse spread is written into ``Home Line Close``. Without it the game
  can never be bet; 14 games of 2025 were in this state.
* **Opening lines standing in for closes** — the model is defined on the closing
  line, so where our export has only an *opening* number, the nflverse closing
  spread replaces it. An opening line is a different quantity, not a noisier
  version of the same one: 2025's 64 such games agreed with the second source
  only 8/64 exactly (mean gap 2.3 points) against 92/221 and 0.88 points for our
  genuine closes, and one — Raiders +15.5 as a *home* underdog — is impossible.
  2025 was the only season affected; every other is closing lines throughout.
* **Neutral venues** — international games have no home-field advantage, and
  the power fit zeroes its 3-point term for them. The odds export flags only
  some of them; nflverse flags all.

A genuine closing line we already hold is **never** overwritten, so seasons keep
the book they were built on. Only the two gaps above are repaired.

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
NO_LIMIT = 10_000  # pricing horizon for a season that has finished

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
    return s[["season", "week", "date", "home", "away", "line", "location"]]


def nickname_of(full_name: str) -> str:
    return "Commanders" if full_name.endswith(("Redskins", "Football Team")) \
        else full_name.split()[-1]


def pricing_horizon(year: int) -> int:
    """The furthest week worth importing a line for.

    A week can only be picked once the previous one has finished (the turnover
    factors need its results), so importing a line further ahead than that just
    locks in an early number when a closer-to-closing one will be available by
    the time the game matters. Returns the first week that is not yet complete,
    which for a finished season is past the last week, so nothing is held back.
    """
    results = pd.read_csv(DATA_DIR / f"results_{year}.csv")
    results = results.dropna(subset=["Winner/tie", "Loser/tie"])
    played = results["Pts"].notna() & results["Pts.1"].notna()
    if played.all():
        return NO_LIMIT  # season finished: import every line, playoffs included
    weeks = pd.to_numeric(results["Week"], errors="coerce")
    complete = {w for w in weeks.dropna().unique() if played[weeks == w].all()}
    horizon = 1
    while horizon in complete:
        horizon += 1
    return horizon


def enrich_year(year: int, schedule: pd.DataFrame,
                horizon: int) -> tuple[pd.DataFrame, int, int, int]:
    """Return (odds frame, lines filled, neutral flags, held back, opens replaced)."""
    odds = pd.read_csv(DATA_DIR / f"odds_{year}.csv", parse_dates=["Date"])
    # An all-empty flag column reads as float64, which will not take "Y".
    for flag in ("Neutral Venue?", "Playoff Game?"):
        odds[flag] = odds[flag].astype(object)
    season = schedule[schedule["season"] == year]

    filled = flagged = held = replaced = 0
    for i, row in odds.iterrows():
        home, away = nickname_of(row["Home Team"]), nickname_of(row["Away Team"])
        cand = season[(season["home"] == home) & (season["away"] == away)]
        cand = cand[(cand["date"] - row["Date"]).abs() <= pd.Timedelta(days=1)]
        if cand.empty:
            continue
        match = cand.iloc[0]

        # No close of our own: either nothing at all, or only an opening number
        # standing in for one. Both are repaired from the second source; a close
        # we already hold is left alone.
        needs_close = pd.isna(row["Home Line Close"])
        if needs_close and not pd.isna(match["line"]):
            if match["week"] <= horizon:
                odds.at[i, "Home Line Close"] = match["line"]
                if pd.isna(row["Home Line Open"]):
                    filled += 1
                else:
                    replaced += 1
            else:
                held += 1  # priced further ahead than we can pick
        if match["location"] == "Neutral" and row.get("Neutral Venue?") != "Y":
            odds.at[i, "Neutral Venue?"] = "Y"
            flagged += 1

    return odds, filled, flagged, held, replaced


def main() -> None:
    schedule = load_schedule()
    years = sorted(int(p.stem.split("_")[1]) for p in DATA_DIR.glob("odds_*.csv"))
    for year in years:
        horizon = pricing_horizon(year)
        odds, filled, flagged, held, replaced = enrich_year(year, schedule, horizon)
        if filled or flagged or replaced:
            odds[ODDS_COLUMNS].to_csv(DATA_DIR / f"odds_{year}.csv", index=False)
        note = ", ".join(
            p for p in (f"{filled} line(s) filled" if filled else "",
                        f"{replaced} opening line(s) replaced with closes" if replaced else "",
                        f"{flagged} neutral venue(s) flagged" if flagged else "",
                        f"{held} priced beyond week {horizon}, held back" if held else "")
            if p) or "nothing to repair"
        print(f"{year}: {note}")


if __name__ == "__main__":
    main()
