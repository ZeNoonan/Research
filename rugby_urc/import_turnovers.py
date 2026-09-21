"""Merge a turnover sheet from the URC match centre into a season file.

The match centre reports, for each side, turnovers **won** and turnovers
**conceded** (sometimes labelled "lost"). Both are needed: a club's last-game
turnover margin is its own conceded minus its own won, and in rugby those are
separate counts rather than two views of the same events - see ``add_lgt`` in
``season_report.py`` for why that distinction changes picks.

Matches are joined to the season file on the **club pair**, not the date, and
then checked: sources disagree about dates more often than they disagree about
who played. Any gap is reported rather than quietly resolved, and the season
file's own date is kept, since that is what the rest of the pipeline has
ordered everything by.

Accepts ``.xlsx`` or ``.csv``. Column names are matched loosely, so
``home_turnovers_lost`` and ``home_turnovers_conceded`` are both understood.

Run::

    python import_turnovers.py turnovers.xlsx --season 2025
    python import_turnovers.py turnovers.xlsx --season 2025 --sheet rugby_results
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

import teams
from season_report import SEASON_COLUMNS

DATA_DIR = Path(__file__).parent / "data"
DATE_TOLERANCE_DAYS = 7

# Season-file column -> the fragments a source column name may use for it.
WANTED = {
    "home_turnovers_conceded": ("home", ("conceded", "lost")),
    "away_turnovers_conceded": ("away", ("conceded", "lost")),
    "home_turnovers_won": ("home", ("won", "win")),
    "away_turnovers_won": ("away", ("won", "win")),
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def find_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map our column names onto whatever this sheet calls them."""
    found = {}
    for target, (side, words) in WANTED.items():
        for col in df.columns:
            key = _slug(col)
            if "turnover" in key and side in key and any(w in key for w in words):
                found[target] = col
                break
    missing = set(WANTED) - set(found)
    if missing:
        raise SystemExit(
            f"could not find {', '.join(sorted(missing))} in this sheet.\n"
            f"columns present: {', '.join(map(str, df.columns))}")
    return found


def load_source(path: Path, sheet: str | None) -> pd.DataFrame:
    raw = (pd.read_csv(path) if path.suffix.lower() == ".csv"
           else pd.read_excel(path, sheet_name=sheet or 0))
    cols = find_columns(raw)

    home_col = next(c for c in raw.columns if _slug(c) in ("hometeam", "home"))
    away_col = next(c for c in raw.columns if _slug(c) in ("awayteam", "away"))
    date_col = next((c for c in raw.columns if _slug(c) == "date"), None)

    out = pd.DataFrame({
        "home": raw[home_col].map(teams.canonical),
        "away": raw[away_col].map(teams.canonical),
        **{target: pd.to_numeric(raw[src], errors="coerce")
           for target, src in cols.items()},
    })
    out["source_date"] = (pd.to_datetime(raw[date_col], errors="coerce")
                          if date_col else pd.NaT)
    return out.dropna(subset=["home", "away"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--sheet", help="worksheet name, for a multi-sheet workbook")
    args = ap.parse_args()

    incoming = load_source(args.source, args.sheet)
    season_path = DATA_DIR / f"season_{args.season}.csv"
    season = pd.read_csv(season_path, dtype=str).fillna("")
    for col in SEASON_COLUMNS:
        if col not in season.columns:
            season[col] = ""
    season_dates = pd.to_datetime(season["date"], errors="coerce")

    applied, unmatched, date_gaps = 0, [], []
    for r in incoming.itertuples():
        hit = season.index[(season["home"] == r.home) & (season["away"] == r.away)]
        if not len(hit):
            unmatched.append(f"{r.home} v {r.away}")
            continue
        if len(hit) > 1 and pd.notna(r.source_date):  # same pair twice: nearest date
            hit = [min(hit, key=lambda i: abs((season_dates[i] - r.source_date).days))]
        i = hit[0]
        if pd.notna(r.source_date) and pd.notna(season_dates[i]):
            gap = abs((season_dates[i] - r.source_date).days)
            if gap:
                date_gaps.append((r.home, r.away, season_dates[i].date(),
                                  r.source_date.date(), gap))
        for col in WANTED:
            value = getattr(r, col)
            if pd.notna(value):
                season.at[i, col] = str(int(value))
        applied += 1

    season[SEASON_COLUMNS].to_csv(season_path, index=False)
    print(f"read {len(incoming)} matches, applied turnovers to {applied} rows of "
          f"{season_path.name}")

    if unmatched:
        print(f"\n{len(unmatched)} not found in the season file:")
        for u in unmatched:
            print(f"  {u}")
    if date_gaps:
        print(f"\n{len(date_gaps)} match(es) dated differently by the two sources. "
              f"The season\nfile's date is kept - everything is ordered by it - "
              f"but worth confirming:")
        for home, away, ours, theirs, gap in date_gaps:
            print(f"  {home} v {away}: season file {ours}, turnover sheet "
                  f"{theirs} ({gap} days)")
        if max(g[4] for g in date_gaps) > DATE_TOLERANCE_DAYS:
            print(f"  (one exceeds {DATE_TOLERANCE_DAYS} days - check it is the "
                  f"same match)")

    # Which clubs now have a margin for their most recent match?
    filled = season[season["home_turnovers_won"].str.strip() != ""]
    covered = set(filled["home"]) | set(filled["away"])
    missing = sorted(set(teams.TEAMS) - covered)
    print(f"\n{len(covered)} of {len(teams.TEAMS)} clubs have a turnover margin "
          f"somewhere in this season file")
    if missing:
        print(f"  still without one: {', '.join(missing)}")


if __name__ == "__main__":
    main()
