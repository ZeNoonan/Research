"""Data in and out of the bet ledger (ledger.html).

The ledger is a claude.ai page where bets are logged from a phone; they are
kept in the logger's own storage there. Two things move between it and this
repo after each weekly update:

* **Out to the ledger:** every scheduled game of the season with its line,
  score and system pick, written as build/ledger_games_<year>.json and loaded
  into the page's ``seasons/<year>`` document.
* **In from the ledger:** the logged bets, exported from the page's database
  (one JSON file per bet) and copied to data/my_bets_<year>.csv, which the
  public site shows beside the system's record. The owner chose to publish
  them.

    python ledger.py                      # games JSON for the latest season
    python ledger.py 2025
    python ledger.py --import-bets DIR    # bets JSON files -> my_bets_<year>.csv
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

import season_report as sr

BUILD_DIR = Path(__file__).parent / "build"
STD_ODDS = 1 + 100 / 110  # the standard -110 price, as decimal odds
BET_COLUMNS = ["week", "home", "away", "kind", "side", "line", "odds", "stake",
               "result", "note", "created", "id"]


def _int(value) -> int | None:
    return None if pd.isna(value) else int(value)


def _float(value) -> float | None:
    return None if pd.isna(value) else float(value)


def season_games(year: int) -> list[dict]:
    """All scheduled games, in kickoff order, with line and pick where priced.

    Priced games take orientation, line, scores and system number from the
    report (so they match the public site exactly); games not priced yet come
    from the schedule alone. Bets are graded in the page from these scores.
    """
    schedule = sr.load_results(year).sort_values(["week", "Date"], kind="stable")
    report = pd.read_csv(sr.DATA_DIR / f"report_{year}.csv")
    priced = {(int(r.week), frozenset((r.home, r.away))): r for r in report.itertuples()}

    games = []
    for g in schedule.itertuples():
        r = priced.pop((int(g.week), frozenset((g.home, g.away))), None)
        src = g if r is None else r
        games.append({
            "week": int(g.week),
            "date": g.Date.date().isoformat(),
            "playoff": bool(g.playoff),
            "home": src.home,
            "away": src.away,
            "line": None if r is None else _float(r.line),
            "home_score": _int(src.home_score),
            "away_score": _int(src.away_score),
            "system_num": None if r is None else _int(r.system_num),
            "system_bet": None if r is None or pd.isna(r.system_bet) else r.system_bet,
        })
    if priced:
        raise ValueError(f"{year}: report games missing from the schedule: {sorted(priced)}")
    return games


def bets_path(year: int) -> Path:
    return sr.DATA_DIR / f"my_bets_{year}.csv"


def import_bets(json_dir: Path, year: int) -> Path:
    """Copy the ledger's exported bets (one JSON file per bet) to my_bets_<year>.csv."""
    rows = []
    for f in sorted(Path(json_dir).glob("*.json")):
        bet = json.loads(f.read_text())
        if bet.get("season", year) == year:
            rows.append({**{c: bet.get(c) for c in BET_COLUMNS}, "id": f.stem})
    bets = pd.DataFrame(rows, columns=BET_COLUMNS).sort_values(["week", "created", "id"])
    bets.to_csv(bets_path(year), index=False)
    return bets_path(year)


def load_bets(year: int) -> pd.DataFrame | None:
    path = bets_path(year)
    return pd.read_csv(path) if path.exists() else None


def settle(bets: pd.DataFrame, report: pd.DataFrame) -> pd.DataFrame:
    """Add each bet's result and profit, settled the way the ledger page does it.

    A result entered on the slip stands; otherwise a spread bet settles from the
    final score at the bet's own line (builders stay open until marked). A win
    pays at the bet's decimal odds, or at -110 when none were entered.
    """
    games = {(int(r.week), frozenset((r.home, r.away))): r for r in report.itertuples()}
    results, profits = [], []
    for b in bets.itertuples():
        res = b.result if b.result in ("W", "L", "P") else None
        g = games.get((int(b.week), frozenset((b.home, b.away))))
        if (res is None and b.kind == "single" and g is not None
                and not pd.isna(g.home_score) and not pd.isna(b.line)
                and b.side in (g.home, g.away)):
            margin = (g.home_score - g.away_score) * (1 if b.side == g.home else -1)
            m = margin + b.line
            res = "W" if m > 0 else "L" if m < 0 else "P"
        odds = b.odds if not pd.isna(b.odds) and b.odds > 1 else STD_ODDS
        profits.append(None if res is None else
                       b.stake * (odds - 1) if res == "W" else -b.stake if res == "L" else 0.0)
        results.append(res)
    return bets.assign(res=results, pnl=profits)


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "--import-bets":
        year = int(sys.argv[3]) if len(sys.argv) > 3 else max(sr.available_years())
        path = import_bets(Path(sys.argv[2]), year)
        print(f"{path.name}: {len(pd.read_csv(path))} bets")
        return
    year = int(sys.argv[1]) if len(sys.argv) > 1 else max(sr.available_years())
    games = season_games(year)
    BUILD_DIR.mkdir(exist_ok=True)
    out = BUILD_DIR / f"ledger_games_{year}.json"
    doc = {"season": year, "updated": date.today().isoformat(), "games": games}
    out.write_text(json.dumps(doc, separators=(",", ":")))

    played = [g for g in games if g["home_score"] is not None]
    priced = [g for g in games if g["line"] is not None]
    picks = [g for g in priced if g["system_bet"]]
    print(f"{out.name}: {len(games)} games, {len(played)} played, "
          f"{len(priced)} priced (to week {max((g['week'] for g in priced), default=0)}), "
          f"{len(picks)} system picks, {out.stat().st_size / 1024:.1f} KiB")


if __name__ == "__main__":
    main()
