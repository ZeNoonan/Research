"""Build gw<N>.csv files for a season from the official FPL API.

Run after any gameweek finishes; rewrites one CSV per finished gameweek in
the season directory, in the same one-row-per-player-per-gameweek format as
the sample ``data/2025-26/gw38.csv`` (the API does not provide the sample's
``xP`` column; the model does not use it).

    python fetch_data.py                      # -> data/2026-27/gw<N>.csv
    python fetch_data.py --season 2026-27 --gws 1,2,3

Endpoints (no key needed):
  bootstrap-static/        players, teams, positions, gameweek states
  element-summary/{id}/    a player's per-gameweek history for the season

One request per player (~700), throttled; a full refresh takes a minute or
two. Player prices for the new season appear in bootstrap-static when the
game relaunches in July; per-gameweek rows appear as gameweeks finish.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).parent
API = "https://fantasy.premierleague.com/api"
HEADERS = {"User-Agent": "Mozilla/5.0 (research; fantasy_premier_league model)"}
THROTTLE = 0.05  # seconds between player requests

# Sample-file column order (xP and modified are the exporter's own, not API).
COLUMNS = ["name", "position", "team", "assists", "bonus", "bps",
           "clean_sheets", "clearances_blocks_interceptions", "creativity",
           "defensive_contribution", "element", "expected_assists",
           "expected_goal_involvements", "expected_goals",
           "expected_goals_conceded", "fixture", "goals_conceded",
           "goals_scored", "ict_index", "influence", "kickoff_time",
           "minutes", "opponent_team", "own_goals", "penalties_missed",
           "penalties_saved", "recoveries", "red_cards", "round", "saves",
           "selected", "starts", "tackles", "team_a_score", "team_h_score",
           "threat", "total_points", "transfers_balance", "transfers_in",
           "transfers_out", "value", "was_home", "yellow_cards"]


def get(session: requests.Session, url: str, retries: int = 4) -> dict:
    for attempt in range(retries):
        resp = session.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return {}
        time.sleep(2 ** attempt)
    resp.raise_for_status()
    return {}


def fetch_season(out_dir: Path, gws: set[int] | None) -> None:
    session = requests.Session()
    boot = get(session, f"{API}/bootstrap-static/")
    if not boot:
        sys.exit("bootstrap-static returned nothing - is the API reachable?")

    teams = {t["id"]: t["name"] for t in boot["teams"]}
    positions = {t["id"]: t["singular_name_short"].replace("GKP", "GK")
                 for t in boot["element_types"]}
    players = boot["elements"]
    finished = {e["id"] for e in boot["events"] if e["finished"]}
    if not finished:
        sys.exit("No finished gameweeks yet - nothing to write. "
                 "(Prices and squads are in the API; run again after GW1.)")

    rows: list[dict] = []
    for i, p in enumerate(players, 1):
        summary = get(session, f"{API}/element-summary/{p['id']}/")
        for h in summary.get("history", []):
            if h["round"] not in finished:
                continue
            if gws and h["round"] not in gws:
                continue
            h = dict(h)
            h["name"] = f"{p['first_name']} {p['second_name']}"
            h["position"] = positions[p["element_type"]]
            h["team"] = teams[p["team"]]
            rows.append(h)
        if i % 100 == 0:
            print(f"  {i}/{len(players)} players fetched")
        time.sleep(THROTTLE)

    if not rows:
        sys.exit("No per-gameweek rows matched - check --gws against "
                 f"finished gameweeks {sorted(finished)}")

    df = pd.DataFrame(rows)
    keep = [c for c in COLUMNS if c in df.columns]
    dropped = [c for c in COLUMNS if c not in df.columns]
    if dropped:
        print(f"NOTE: API did not provide {dropped}; writing without them.")

    out_dir.mkdir(parents=True, exist_ok=True)
    for gw, block in df.groupby("round"):
        path = out_dir / f"gw{int(gw)}.csv"
        block[keep].to_csv(path, index=False)
        print(f"wrote {path} ({len(block)} players)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--season", default="2026-27",
                    help="season directory name under data/")
    ap.add_argument("--gws", default=None,
                    help="comma-separated gameweeks (default: all finished)")
    args = ap.parse_args()

    gws = ({int(g) for g in args.gws.split(",")} if args.gws else None)
    fetch_season(HERE / "data" / args.season, gws)


if __name__ == "__main__":
    main()
