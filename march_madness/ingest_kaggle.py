"""Ingest historical NCAA pick-frequency data from a downloaded Kaggle dataset.

The Wayback route (scrape_pick_frequencies.py) needs web.archive.org egress.
This is the fallback for years that route can't reach (notably 2023+, after
ESPN moved Tournament Challenge to a JavaScript platform the archives can't
capture). Community datasets on Kaggle -- e.g. nishaanamin/march-madness-data,
which carries a "Public Picks" table -- republish ESPN/Yahoo pick percentages.

Kaggle blocks anonymous scraping (HTTP 403) and needs an API token, so there
are two ways in:

  A. Manual download (works with no special network access):
     download the dataset zip in your browser, unzip anywhere, then
       python3 ingest_kaggle.py <path-to-unzipped-folder>

  B. Kaggle API (needs www.kaggle.com egress + a token):
     set KAGGLE_USERNAME / KAGGLE_KEY in the environment, then
       python3 ingest_kaggle.py --download nishaanamin/march-madness-data
     which fetches into data/kaggle/ and ingests.

Either way the script scans for any CSV whose columns look like per-round pick
percentages, normalises team names to the workbook's spelling, and writes
data/pick_freq_<year>.csv with columns team,R64,R32,S16,E8,F4,C6 (fractions in
0..1, matching 'Brackets - freq' in the workbook). Run with --inspect to dump
the schema of every CSV found without writing anything -- do that first on a
new dataset, since column names vary between sources.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
KAGGLE_DIR = HERE / "data" / "kaggle"
OUT = HERE / "data"

ROUND_COLS = ["R64", "R32", "S16", "E8", "F4", "C6"]
# Header tokens that map to our six rounds, lower-cased and stripped of spaces.
ROUND_ALIASES = {
    "R64": ["r64", "round64", "roundof64", "r1", "round1", "secondround", "first"],
    "R32": ["r32", "round32", "roundof32", "r2", "round2", "thirdround", "second"],
    "S16": ["s16", "sweet16", "sweetsixteen", "r3", "round3", "regionalsemifinal"],
    "E8":  ["e8", "elite8", "eliteeight", "r4", "round4", "regionalfinal"],
    "F4":  ["f4", "final4", "finalfour", "r5", "round5", "semifinal", "nationalsemifinal"],
    "C6":  ["c6", "champion", "champ", "championship", "title", "winner", "natchamp",
            "nationalchampion", "r6", "round6", "final"],
}
TEAM_ALIASES = {"team", "teamname", "school", "name", "team_name"}
YEAR_ALIASES = {"year", "season", "yr"}


def norm_header(h):
    return re.sub(r"[^a-z0-9]", "", str(h).lower())


def norm_team(name):
    """Loose team-name key for matching across sources (accents, punctuation,
    common abbreviations). Returns a comparison key, not a display name."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = s.lower().strip()
    s = re.sub(r"\bst\.?\b", "state", s)          # 'St' -> 'state' (over-broad;
    s = re.sub(r"\buniv(ersity)?\b", "", s)       # St. John's handled by overrides)
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def load_workbook_team_keys():
    """Map normalised key -> workbook display name, from model_2019.json, so
    ingested rows line up with the rest of the pipeline. Returns {} if absent."""
    f = OUT / "model_2019.json"
    if not f.exists():
        return {}
    model = json.loads(f.read_text())
    keys = {}
    for t in model["teams"]:
        for variant in (t["name"], t.get("longName", "")):
            if variant:
                keys[norm_team(variant)] = t["name"]
    return keys


def find_columns(header):
    """Return (team_idx, year_idx_or_None, {round: col_idx}) or None if this
    CSV doesn't look like a pick-frequency table."""
    nh = [norm_header(h) for h in header]
    team_idx = next((i for i, h in enumerate(nh) if h in TEAM_ALIASES), None)
    if team_idx is None:
        return None
    year_idx = next((i for i, h in enumerate(nh) if h in YEAR_ALIASES), None)
    round_idx = {}
    for rnd, aliases in ROUND_ALIASES.items():
        for i, h in enumerate(nh):
            if h in aliases:
                round_idx[rnd] = i
                break
    # Need most of the rounds present to treat it as a pick table
    if len(round_idx) >= 4:
        return team_idx, year_idx, round_idx
    return None


def to_fraction(v):
    """'42.3%' / '42.3' / '0.423' -> 0.423. None for blanks."""
    if v is None or str(v).strip() == "":
        return None
    s = str(v).replace("%", "").strip()
    try:
        x = float(s)
    except ValueError:
        return None
    return x / 100.0 if x > 1.0 else x


def iter_csvs(root):
    root = Path(root)
    if root.is_file() and root.suffix.lower() == ".zip":
        with zipfile.ZipFile(root) as z:
            for n in z.namelist():
                if n.lower().endswith(".csv"):
                    with z.open(n) as fh:
                        yield n, [r for r in csv.reader(
                            (line.decode("utf-8", "replace") for line in fh))]
        return
    for p in sorted(root.rglob("*.csv")):
        with open(p, newline="", encoding="utf-8", errors="replace") as fh:
            yield str(p.relative_to(root)), list(csv.reader(fh))


def inspect(root):
    for name, rows in iter_csvs(root):
        if not rows:
            continue
        match = find_columns(rows[0])
        tag = "  <-- pick-frequency table" if match else ""
        print(f"{name}: {len(rows) - 1} rows, cols={rows[0]}{tag}")


def ingest(root):
    team_keys = load_workbook_team_keys()
    by_year = {}                                   # year -> {team: [6 fracs]}
    unknown = set()
    for name, rows in iter_csvs(root):
        if not rows:
            continue
        match = find_columns(rows[0])
        if not match:
            continue
        team_idx, year_idx, round_idx = match
        # Year from a column, else from the filename, else 'unknown'
        fname_year = re.search(r"(19|20)\d\d", name)
        for row in rows[1:]:
            if len(row) <= team_idx or not row[team_idx].strip():
                continue
            year = (row[year_idx].strip() if year_idx is not None
                    and len(row) > year_idx else
                    (fname_year.group(0) if fname_year else "unknown"))
            key = norm_team(row[team_idx])
            display = team_keys.get(key, row[team_idx].strip())
            if team_keys and key not in team_keys:
                unknown.add(f"{year}: {row[team_idx].strip()}")
            fracs = [to_fraction(row[round_idx[r]]) if r in round_idx
                     and len(row) > round_idx[r] else None for r in ROUND_COLS]
            by_year.setdefault(str(year), {})[display] = fracs

    if not by_year:
        print("No pick-frequency tables found. Run with --inspect to see the "
              "schemas, then extend ROUND_ALIASES/TEAM_ALIASES if needed.")
        return
    for year, teams in sorted(by_year.items()):
        dest = OUT / f"pick_freq_{year}.csv"
        with open(dest, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["team"] + ROUND_COLS)
            for team, fracs in sorted(teams.items()):
                w.writerow([team] + ["" if x is None else f"{x:.4f}" for x in fracs])
        print(f"{year}: wrote {dest} ({len(teams)} teams)")
    if unknown:
        print(f"\n{len(unknown)} team names not matched to the workbook "
              f"(add overrides in norm_team):")
        for u in sorted(unknown)[:40]:
            print(f"  {u}")


def kaggle_download(slug):
    if not (os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY")):
        sys.exit("Set KAGGLE_USERNAME and KAGGLE_KEY to use --download, or "
                 "download the dataset manually and pass its folder path.")
    KAGGLE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError:
        sys.exit("pip install kaggle first (needs www.kaggle.com egress).")
    api = KaggleApi()
    api.authenticate()
    api.dataset_download_files(slug, path=str(KAGGLE_DIR), unzip=True)
    print(f"Downloaded {slug} into {KAGGLE_DIR}")
    return KAGGLE_DIR


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if args[0] == "--download":
        root = kaggle_download(args[1])
        ingest(root)
    elif args[0] == "--inspect":
        inspect(args[1] if len(args) > 1 else KAGGLE_DIR)
    else:
        ingest(args[0])


if __name__ == "__main__":
    main()
