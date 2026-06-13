"""Collect historical ESPN 'Who Picked Whom' pick-frequency data from the
Wayback Machine.

ESPN published pick percentages per team per round every year. The page moved
hosts over the years:

  ~2010-2015  games.espn.go.com/tournament-challenge-bracket/<y>/en/whopickedwhom
  2016-2017   games.espn.com/tournament-challenge-bracket/<y>/en/whopickedwhom
  2018-2022   fantasy.espn.com/tournament-challenge-bracket/<y>/en/whopickedwhom
  2023+       new JS platform (snapshots usually unusable; handled separately)

Commands
  python3 scrape_pick_frequencies.py survey            # list snapshots per year
  python3 scrape_pick_frequencies.py fetch [years...]  # download best snapshots
  python3 scrape_pick_frequencies.py parse [years...]  # html -> data/pick_freq_<y>.csv

'fetch' caches raw HTML under data/wayback/ so parsing can be iterated offline.
The 'best' snapshot is the last one taken while that year's bracket data was
live (percentages freeze once brackets lock, so any in-season snapshot works;
later ones reflect the locked field).
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / "data" / "wayback"
OUT = HERE / "data"

CDX = "https://web.archive.org/cdx/search/cdx"
SNAP = "https://web.archive.org/web/{ts}id_/{url}"  # id_ = original page, no toolbar

URL_PATTERNS = {
    range(2010, 2016): "games.espn.go.com/tournament-challenge-bracket/{y}/en/whopickedwhom",
    range(2016, 2018): "games.espn.com/tournament-challenge-bracket/{y}/en/whopickedwhom",
    range(2018, 2023): "fantasy.espn.com/tournament-challenge-bracket/{y}/en/whopickedwhom",
}
YEARS = [y for y in range(2010, 2023) if y != 2020]  # 2020 tournament cancelled


def url_for(year):
    for rng, pat in URL_PATTERNS.items():
        if year in rng:
            return pat.format(y=year)
    return None


def http_get(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "research-backtest/1.0"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))


def cdx_snapshots(url):
    """All archived snapshots of url: list of (timestamp, statuscode)."""
    q = urllib.parse.urlencode({
        "url": url, "output": "json", "filter": "statuscode:200",
        "collapse": "timestamp:8",          # at most one per day
    })
    raw = http_get(f"{CDX}?{q}")
    rows = json.loads(raw) if raw.strip() else []
    return [(r[1], r[4]) for r in rows[1:]] if rows else []


def best_snapshot(year, snaps):
    """Prefer the last snapshot of the tournament season (March-June)."""
    season = [ts for ts, _ in snaps if f"{year}03" <= ts[:6] <= f"{year}06"]
    if season:
        return season[-1]
    anyyear = [ts for ts, _ in snaps if ts.startswith(str(year))]
    return anyyear[-1] if anyyear else (snaps[-1][0] if snaps else None)


def survey():
    for year in YEARS:
        url = url_for(year)
        try:
            snaps = cdx_snapshots(url)
        except Exception as e:
            print(f"{year}: CDX error: {e}")
            continue
        season = [ts for ts, _ in snaps if f"{year}03" <= ts[:6] <= f"{year}06"]
        pick = best_snapshot(year, snaps)
        print(f"{year}: {len(snaps)} snapshots, {len(season)} in Mar-Jun, "
              f"best={pick}  ({url})")
        time.sleep(1)


def fetch(years):
    CACHE.mkdir(parents=True, exist_ok=True)
    for year in years:
        dest = CACHE / f"whopickedwhom_{year}.html"
        if dest.exists():
            print(f"{year}: cached ({dest.stat().st_size/1024:.0f} kB)")
            continue
        url = url_for(year)
        snaps = cdx_snapshots(url)
        ts = best_snapshot(year, snaps)
        if not ts:
            print(f"{year}: no snapshots found")
            continue
        html = http_get(SNAP.format(ts=ts, url=url))
        dest.write_bytes(html)
        print(f"{year}: saved {ts} ({len(html)/1024:.0f} kB)")
        time.sleep(2)


PCT = re.compile(r"([\d.]+)\s*%")


def parse_year(year):
    """Parse cached HTML into [(team, [pct R64..C6])]. The old WPW page is a
    table: 6 round columns, each cell holding 'Team seed pct%' entries."""
    src = (CACHE / f"whopickedwhom_{year}.html").read_text(errors="replace")
    # Old platform: data lives in <td> cells with team/pct spans. Structure has
    # varied; parse all (team, pct) pairs column by column from the matrix
    # table, which is the only table with 64 rows of six percentage cells.
    raise NotImplementedError(
        "Inspect data/wayback/whopickedwhom_%d.html first, then implement "
        "the selector for that year's markup." % year)


def parse(years):
    for year in years:
        rows = parse_year(year)
        dest = OUT / f"pick_freq_{year}.csv"
        with open(dest, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["team", "R64", "R32", "S16", "E8", "F4", "C6"])
            w.writerows([name, *pcts] for name, pcts in rows)
        print(f"{year}: wrote {dest} ({len(rows)} teams)")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "survey"
    years = [int(y) for y in sys.argv[2:]] or YEARS
    if cmd == "survey":
        survey()
    elif cmd == "fetch":
        fetch(years)
    elif cmd == "parse":
        parse(years)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
