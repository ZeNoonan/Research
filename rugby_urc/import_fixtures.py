"""Turn a pasted fixture or results list into a season file.

The URC fixture list is published as a web page, not a feed, so the reliable
way to get it in here is to copy the text and paste it into a file. This module
reads that text - from the URC site, Wikipedia, or any listing that names two
clubs per line - and writes the ``data/season_<year>.csv`` skeleton.

It is deliberately tolerant about layout and strict about content: a line is
only taken as a fixture when **two different URC clubs** can be resolved from
it (see ``teams.canonical``), and the result is then checked against the shape
a URC round must have. Anything it cannot read is reported, never guessed.

Recognised, in any mixture::

    Round 1                       <- sets the current round
    Friday 25 September 2026      <- sets the current date
    Benetton v Dragons            <- a fixture
    Benetton 24-17 Dragons        <- a played match (scores captured too)
    2026-09-25 Ulster v Edinburgh <- date on the line itself

Run::

    python import_fixtures.py paste.txt --season 2026
    python import_fixtures.py paste.txt --season 2025 --append
"""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

import teams

DATA_DIR = Path(__file__).parent / "data"

ROUND_RE = re.compile(r"^\s*(?:round|rd\.?|matchday|week)\s*[:\-]?\s*(\d{1,2})\b", re.I)
PLAYOFF_RE = re.compile(
    r"\b(quarter[- ]?finals?|semi[- ]?finals?|grand final|final)\b", re.I)

# Playoff rounds continue the numbering after the 18-round regular season.
REGULAR_ROUNDS = 18
PLAYOFF_ROUNDS = {"quarter-final": 19, "semi-final": 20, "final": 21}

_MONTHS = ("january february march april may june july august september "
           "october november december").split()
_MONTH_RE = "|".join(m[:3] for m in _MONTHS)

DATE_PATTERNS = (
    re.compile(r"(?P<y>20\d{2})-(?P<m>\d{1,2})-(?P<d>\d{1,2})"),
    re.compile(rf"(?P<d>\d{{1,2}})\s+(?P<mon>{_MONTH_RE})[a-z]*\.?,?\s*(?P<y>20\d{{2}})?", re.I),
    re.compile(rf"(?P<mon>{_MONTH_RE})[a-z]*\.?\s+(?P<d>\d{{1,2}}),?\s*(?P<y>20\d{{2}})?", re.I),
    re.compile(r"(?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<y>20\d{2})"),
)

# "Home v Away", "Home vs. Away", "Home 24-17 Away", "Home 24 - 17 Away".
SPLIT_RE = re.compile(
    r"^(?P<home>.+?)\s+(?:(?P<hs>\d{1,3})\s*[-–—:]\s*(?P<as>\d{1,3})|v\.?|vs\.?|@)\s+(?P<away>.+?)\s*$",
    re.I)


def _season_year(text: str, default: int) -> int:
    m = re.search(r"\b(20\d{2})\s*[/–\-]\s*(?:20)?\d{2}\b", text)
    return int(m.group(1)) if m else default


def parse_date(text: str, season: int) -> date | None:
    """First date found in ``text``, with the year inferred from the season.

    A URC season runs September to June, so a month from September on belongs to
    the season's start year and anything earlier to the next calendar year.
    """
    for pattern in DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        parts = m.groupdict()
        if parts.get("mon"):
            month = next(i for i, name in enumerate(_MONTHS, 1)
                         if name.startswith(parts["mon"][:3].lower()))
        else:
            month = int(parts["m"])
        year = int(parts["y"]) if parts.get("y") else (
            season if month >= 7 else season + 1)
        try:
            return date(year, month, int(parts["d"]))
        except ValueError:
            continue
    return None


def _strip_noise(text: str) -> str:
    """Drop the decoration around a fixture: times, venues, TV, footnotes."""
    text = re.sub(r"\[[^\]]*\]", " ", text)             # [1] wiki footnotes
    text = re.sub(r"\([^)]*\)", " ", text)              # (Stadio Monigo)
    text = re.sub(r"\b\d{1,2}[:.]\d{2}\s*(?:am|pm)?\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:ko|kick[- ]?off|live on|tv)\b.*$", " ", text, flags=re.I)
    text = re.sub(r"[•|]", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip(" ,;-–\t")


def parse_text(raw: str, season: int) -> tuple[pd.DataFrame, list[str]]:
    """Parse pasted text into (fixtures frame, list of unreadable lines)."""
    rows: list[dict] = []
    skipped: list[str] = []
    current_round: int | None = None
    current_date: date | None = None

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        if m := ROUND_RE.match(line):
            current_round = int(m.group(1))
            continue
        if (m := PLAYOFF_RE.search(line)) and not SPLIT_RE.match(_strip_noise(line)):
            label = m.group(1).lower().replace(" ", "-").rstrip("s")
            label = "final" if label == "grand-final" else label
            current_round = PLAYOFF_ROUNDS.get(label, current_round)
            continue

        if (found := parse_date(line, season)) is not None:
            current_date = found
        clean = _strip_noise(line)
        if not (m := SPLIT_RE.match(clean)):
            continue

        try:
            home = teams.canonical(m.group("home"))
            away = teams.canonical(m.group("away"))
        except KeyError:
            if re.search(r"\bv\.?s?\.?\b", clean, re.I):
                skipped.append(line)
            continue
        if home == away:
            skipped.append(line)
            continue

        rows.append({
            "round": current_round,
            "date": current_date,
            "home": home,
            "away": away,
            "neutral": "",
            "line": "",
            "home_score": m.group("hs") or "",
            "away_score": m.group("as") or "",
            "home_turnovers_conceded": "",
            "away_turnovers_conceded": "",
        })

    return pd.DataFrame(rows, columns=SEASON_COLUMNS), skipped


SEASON_COLUMNS = ["round", "date", "home", "away", "neutral", "line",
                  "home_score", "away_score",
                  "home_turnovers_conceded", "away_turnovers_conceded"]


def check(df: pd.DataFrame) -> list[str]:
    """Shape checks a real URC fixture list must satisfy.

    Each regular round pairs all 16 clubs exactly once, and over 18 rounds each
    club plays 18 matches, nine at home. Reported, not enforced: a partial list
    is a normal intermediate state, and the point is to show what is missing.
    """
    problems: list[str] = []
    if df.empty:
        return ["no fixtures parsed"]

    if df["round"].isna().any():
        problems.append(f"{int(df['round'].isna().sum())} fixtures with no round "
                        f"(no 'Round N' heading above them)")
    if df["date"].isna().any():
        problems.append(f"{int(df['date'].isna().sum())} fixtures with no date")

    for rnd, block in df[df["round"].notna()].groupby("round"):
        rnd = int(rnd)
        if rnd > REGULAR_ROUNDS:  # playoffs are not full rounds
            continue
        played = pd.concat([block["home"], block["away"]])
        duplicated = sorted(played[played.duplicated()].unique())
        missing = sorted(set(teams.TEAMS) - set(played))
        if len(block) != len(teams.TEAMS) // 2:
            problems.append(f"round {rnd}: {len(block)} matches, expected 8"
                            + (f" - missing {', '.join(missing)}" if missing else ""))
        if duplicated:
            problems.append(f"round {rnd}: {', '.join(duplicated)} appear twice")

    regular = df[df["round"].le(REGULAR_ROUNDS).fillna(False)]
    if len(regular) == REGULAR_ROUNDS * len(teams.TEAMS) // 2:
        for club in sorted(teams.TEAMS):
            home = int((regular["home"] == club).sum())
            away = int((regular["away"] == club).sum())
            if home + away != REGULAR_ROUNDS or home != away:
                problems.append(
                    f"{club}: {home} home + {away} away = {home + away} "
                    f"(expected 9 + 9 = 18)")

    dupes = df.duplicated(subset=["home", "away", "round"], keep=False)
    for r in df[dupes].itertuples():
        problems.append(f"duplicate fixture: round {r.round} {r.home} v {r.away}")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="text file pasted from the fixture list")
    ap.add_argument("--season", type=int, help="season start year, e.g. 2026")
    ap.add_argument("--append", action="store_true",
                    help="merge into the existing season file instead of replacing it")
    args = ap.parse_args()

    raw = args.source.read_text(encoding="utf-8")
    season = args.season or _season_year(raw, date.today().year)
    fixtures, skipped = parse_text(raw, season)
    print(f"parsed {len(fixtures)} fixtures for the {season}-{(season + 1) % 100:02d} season")

    out = DATA_DIR / f"season_{season}.csv"
    if args.append and out.exists():
        existing = pd.read_csv(out, dtype=str).fillna("")
        fixtures = pd.concat([existing, fixtures.astype(str)], ignore_index=True)
        fixtures = fixtures.drop_duplicates(subset=["round", "home", "away"], keep="last")

    # Date order: how the season is actually worked through, and it keeps a
    # split round (2026-27's round 8) beside the matches it is played among.
    fixtures = fixtures.sort_values(["date", "round", "home"], na_position="last")
    DATA_DIR.mkdir(exist_ok=True)
    fixtures.to_csv(out, index=False)
    print(f"wrote {out.relative_to(Path(__file__).parent)} ({len(fixtures)} rows)")

    if skipped:
        print(f"\n{len(skipped)} line(s) looked like fixtures but named no known club:")
        for line in skipped[:20]:
            print(f"  {line}")
    if problems := check(fixtures):
        print(f"\n{len(problems)} thing(s) to check - a partial list will say so here:")
        for p in problems[:40]:
            print(f"  - {p}")
    else:
        print("\nshape checks pass: every round pairs all 16 clubs once.")


if __name__ == "__main__":
    main()
