"""Every stat the feed publishes for a match, kept beside the season file.

The season file holds what the five factors read - lines, scores, turnover
counts - and is typed into by hand. The scrapers fetch far more than that:
about a hundred home/away stat pairs per match, from cards to kicking to
visits to the 22. Those are machine data, so they live in their own file,
``data/stats_<year>.csv``, one row per match keyed on the season file's own
date and club names. ``shadow_factors.py`` reads it.

Both loaders write it: ``import_season.py`` for a whole past season,
``import_turnovers.py`` a round at a time. A match loaded twice keeps its
latest stats, and a stat that appears for the first time adds a column.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
KEY = ["date", "home", "away"]


def path_for(year: int) -> Path:
    return DATA_DIR / f"stats_{year}.csv"


def stat_pairs(frame: pd.DataFrame) -> list[str]:
    """The ``home_x``/``away_x`` columns of a scraped file, in pairs.

    Skips ``*_date``: an early build of ``urc_scraper.py`` read the year out of
    a timestamp as a stat, and those files still carry ``home_date = 2026``.
    """
    cols = []
    for col in frame.columns:
        if not col.startswith("home_") or col.endswith("_date"):
            continue
        partner = "away_" + col[len("home_"):]
        if partner in frame.columns:
            cols += [col, partner]
    return cols


def load(year: int) -> pd.DataFrame:
    """The stats file for a season, or an empty frame keyed like one."""
    path = path_for(year)
    if not path.exists():
        return pd.DataFrame(columns=KEY)
    return pd.read_csv(path)


def upsert(year: int, rows: pd.DataFrame) -> Path:
    """Merge ``rows`` (KEY plus stat pairs) into the season's stats file.

    Anything that is not a home/away pair is dropped, and so are the junk
    ``*_date`` pairs (see ``stat_pairs``).
    """
    path = path_for(year)
    rows = rows[KEY + stat_pairs(rows)].assign(
        date=pd.to_datetime(rows["date"]).dt.strftime("%Y-%m-%d"))
    merged = pd.concat([load(year), rows], ignore_index=True)
    merged = (merged.drop_duplicates(subset=KEY, keep="last")
              .sort_values(KEY).reset_index(drop=True))
    stats = [c for c in merged.columns if c not in KEY]
    path.parent.mkdir(parents=True, exist_ok=True)
    merged[KEY + stats].to_csv(path, index=False)
    return path
