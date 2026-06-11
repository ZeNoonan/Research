"""Parse the published NFL Report PDFs into tidy CSVs.

The reports (``reference/NFL_Report_2015.pdf`` and ``NFL_Report_2016.pdf``) are
Aaron Brown's weekly NFL betting system output. Each row is one game with the
following columns, in order:

    Date, Home team, Away team, Line, Home score, Away score,
    Home LGT, Home STDC, Home Power, Away LGT, Away STDC, Away Power,
    System #, System Bet, Result

``Line`` is the point spread in *home* terms: negative means the home team is
favoured by that many points, positive means the home team is an underdog
getting that many points.

How the parse works
-------------------
The numeric cells, the Bet (team name) and the Result (``W``/``L``) are read
from the flat token stream PyMuPDF produces: every game is exactly ten numeric
cells (Line, two scores, six factor values and the System #) optionally followed
by a Bet and Result.

Team names are read separately, from word **coordinates**. The report's two
tracking teams, the **Seahawks** and **Steelers**, live on a separate text layer
whose words are emitted out of order in the flat stream (they pile up at the foot
of each page), which is why a naive linear parse leaves those rows' home/away
cells blank. But every name keeps its true position, so we group words into rows
by their y-coordinate and pick the home name from the home column (x ~ 97) and
the away name from the away column (x ~ 145). This recovers every name except two
games where the tracking team's word is dropped from the PDF entirely; those two
are filled from ``STRAGGLERS`` below.

This script only needs to run when regenerating the CSVs; the committed CSVs in
``data/`` make the rest of the project self-contained.
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd

REFERENCE_DIR = Path(__file__).parent / "reference"
DATA_DIR = Path(__file__).parent / "data"

DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{2}$")
NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
FOOTER_TEAMS = {"Seahawks", "Steelers"}

# Column x-windows (PDF points) for the team-name cells. Names are left-aligned,
# so a cell's left edge is stable regardless of name length; the date sits at
# x ~ 67 and the first numeric column (Line) at x >= ~190, so these windows
# contain team names only.
DATE_X = (55, 86)
HOME_X = (86, 135)
AWAY_X = (135, 186)

# Two games drop the tracking team's name from the PDF text layer entirely (the
# word is absent, not merely repositioned). Each is pinned down two ways: the
# *other* tracking team already appears on that date, and the blank side's power
# rating continues the remaining team's week-to-week trajectory. Both also match
# the historical schedule. Keyed by (year, date) -> (side, team).
STRAGGLERS = {
    (2016, "16-10-23"): ("home", "Steelers"),   # New England @ Pittsburgh
    (2015, "15-10-22"): ("away", "Seahawks"),   # Seattle @ San Francisco
}

COLUMNS = [
    "date", "home", "away", "line", "home_score", "away_score",
    "home_lgt", "home_stdc", "home_power",
    "away_lgt", "away_stdc", "away_power",
    "system_num", "system_bet", "result",
]
NUMERIC_FIELDS = [
    "line", "home_score", "away_score",
    "home_lgt", "home_stdc", "home_power",
    "away_lgt", "away_stdc", "away_power", "system_num",
]


def _is_date(token: str) -> bool:
    """True for a date cell, whether bare (``YY-MM-DD``) or ``YY-MM-DD Home``."""
    return bool(DATE_RE.match(token.split()[0]))


# --- numeric / bet / result, from the flat token stream ----------------------

def _page_tokens(page_text: str) -> list[str]:
    """Cell tokens for one page, with header and footer junk removed."""
    tokens = [ln.strip() for ln in page_text.splitlines() if ln.strip()]

    # Drop everything before the first date cell (page title + column headers).
    start = next((i for i, t in enumerate(tokens) if _is_date(t)), len(tokens))
    tokens = tokens[start:]

    # Drop the trailing Seahawks/Steelers footer pile.
    end = len(tokens)
    while end > 0 and tokens[end - 1] in FOOTER_TEAMS:
        end -= 1
    return tokens[:end]


def _parse_numeric_rows(tokens: list[str]) -> list[dict]:
    """One dict per game with the numeric fields, system_bet and result.

    Team names are intentionally ignored here; they come from coordinates. The
    leading date cell and the optional away-name cell are skipped over.
    """
    rows: list[dict] = []
    i, n = 0, len(tokens)
    while i < n:
        if not _is_date(tokens[i]):
            i += 1
            continue
        date = tokens[i].split()[0]
        i += 1

        # Skip an away-name cell if present (the date cell already carried any
        # home name); a numeric next cell means the name slot was blank.
        if i < n and not NUMERIC_RE.match(tokens[i]) and not _is_date(tokens[i]):
            i += 1

        nums: list[float] = []
        while i < n and len(nums) < 10 and NUMERIC_RE.match(tokens[i]):
            nums.append(float(tokens[i]))
            i += 1
        if len(nums) < 10:
            continue  # malformed; resync on the next date

        bet = result = None
        if i < n and not NUMERIC_RE.match(tokens[i]) and not _is_date(tokens[i]):
            bet = tokens[i]
            i += 1
            if i < n and tokens[i] in ("W", "L"):
                result = tokens[i]
                i += 1

        row = {"date": date}
        row.update(dict(zip(NUMERIC_FIELDS, nums)))
        row["system_bet"] = bet
        row["result"] = result
        rows.append(row)
    return rows


# --- team names, from word coordinates ---------------------------------------

def _name_rows(doc: fitz.Document) -> list[dict]:
    """One dict per game ``{date, home, away}`` in reading order, from positions."""
    rows: list[dict] = []
    for page in doc:
        bands: dict[int, list[tuple[float, str]]] = {}
        for x0, y0, x1, y1, text, *_ in page.get_text("words"):
            bands.setdefault(round(y0 / 2) * 2, []).append((x0, text))
        for y in sorted(bands):
            cells = bands[y]
            date = next(
                (t for x, t in cells if DATE_X[0] <= x <= DATE_X[1] and DATE_RE.match(t)),
                None,
            )
            if not date:
                continue  # page title / column-header / non-data band
            home = next((t for x, t in cells if HOME_X[0] < x <= HOME_X[1]), None)
            away = next((t for x, t in cells if AWAY_X[0] < x <= AWAY_X[1]), None)
            rows.append({"date": date, "home": home, "away": away})
    return rows


def parse_report(pdf_path: Path, year: int) -> pd.DataFrame:
    doc = fitz.open(pdf_path)
    numeric_rows: list[dict] = []
    for page in doc:
        numeric_rows.extend(_parse_numeric_rows(_page_tokens(page.get_text())))
    name_rows = _name_rows(doc)

    if len(numeric_rows) != len(name_rows):
        raise ValueError(
            f"{pdf_path.name}: {len(numeric_rows)} numeric rows vs "
            f"{len(name_rows)} name rows"
        )

    games: list[dict] = []
    for nrow, name in zip(numeric_rows, name_rows):
        if nrow["date"] != name["date"]:
            raise ValueError(
                f"{pdf_path.name}: date misalignment {nrow['date']} vs {name['date']}"
            )
        home, away = name["home"], name["away"]
        if home is None or away is None:
            side, team = STRAGGLERS.get((year, nrow["date"]), (None, None))
            if side == "home":
                home = team
            elif side == "away":
                away = team
        games.append({**nrow, "home": home, "away": away})

    df = pd.DataFrame(games, columns=COLUMNS)
    for col in ("home_score", "away_score", "system_num"):
        df[col] = df[col].astype("Int64")
    return df


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    for year in (2015, 2016):
        pdf = REFERENCE_DIR / f"NFL_Report_{year}.pdf"
        df = parse_report(pdf, year)
        out = DATA_DIR / f"report_{year}.csv"
        df.to_csv(out, index=False)
        bets = df["system_bet"].notna().sum()
        missing = (df["home"].isna() | df["away"].isna()).sum()
        print(f"{year}: {len(df)} games, {bets} bets, {missing} blank team names -> {out.name}")


if __name__ == "__main__":
    main()
