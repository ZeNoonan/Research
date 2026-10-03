"""Season data for the private bet ledger (ledger.html).

The ledger is a claude.ai page, not part of the public site: bets logged in it
are kept in each viewer's private storage there and never reach this repo. What
it needs from here is public — every scheduled game of the season with its
line, score and system pick — and this script writes that as
build/ledger_games_<year>.json, the body of the page's ``seasons/<year>``
document. Run it after season_report.py in each weekly update, then push the
file to the page's database.

    python ledger.py            # the latest season with a results file
    python ledger.py 2025
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

import season_report as sr

BUILD_DIR = Path(__file__).parent / "build"


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


def main() -> None:
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
