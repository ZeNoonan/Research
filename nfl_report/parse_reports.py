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

PDF quirk
---------
When extracted with PyMuPDF the table is a flat stream of cell tokens. Every
game is exactly ten numeric cells (Line, two scores, six factor values and the
System #) optionally followed by a Bet (team name) and Result (``W``/``L``).
The wrinkle is that the report's two tracking teams, the **Seahawks** and
**Steelers**, are rendered in a separate text layer: their *team-column*
occurrences are pulled out of the row and dumped at the foot of each page. So
games involving those teams have a blank home or away slot, and each page ends
with a pile of ``Seahawks``/``Steelers`` tokens. We strip that footer pile and,
where possible, recover the missing name from the Bet column.

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


def _split_date_token(token: str) -> tuple[str, str | None]:
    """A date cell is either ``YY-MM-DD`` or ``YY-MM-DD HomeTeam``."""
    parts = token.split(maxsplit=1)
    date = parts[0]
    home = parts[1] if len(parts) > 1 else None
    return date, home


def _parse_games(tokens: list[str]) -> list[dict]:
    games: list[dict] = []
    i = 0
    n = len(tokens)
    while i < n:
        token = tokens[i]
        if not _is_date(token):
            i += 1
            continue

        date, home = _split_date_token(token)
        i += 1

        # An away team name sits between the date and the numeric block; if the
        # next cell is already numeric the away slot was blank (a footer team).
        away = None
        if i < n and not NUMERIC_RE.match(tokens[i]) and not _is_date(tokens[i]):
            away = tokens[i]
            i += 1

        # Exactly ten numeric cells.
        nums: list[float] = []
        while i < n and len(nums) < 10 and NUMERIC_RE.match(tokens[i]):
            nums.append(float(tokens[i]))
            i += 1
        if len(nums) < 10:
            # Malformed row; skip what we have and resync on the next date.
            continue

        # Optional Bet (team) and Result (W/L).
        bet = result = None
        if i < n and not NUMERIC_RE.match(tokens[i]) and not _is_date(tokens[i]):
            bet = tokens[i]
            i += 1
            if i < n and tokens[i] in ("W", "L"):
                result = tokens[i]
                i += 1

        row = {"date": date, "home": home, "away": away}
        row.update(dict(zip(NUMERIC_FIELDS, nums)))
        row["system_bet"] = bet
        row["result"] = result

        # Recover a blank home/away name from the Bet column when the bet was on
        # the missing side (the Bet cell keeps its text even when the team cell
        # was pulled to the footer).
        if bet:
            if home is None and row["system_num"] > 0:
                row["home"] = bet
            elif away is None and row["system_num"] < 0:
                row["away"] = bet
        games.append(row)
    return games


def parse_report(pdf_path: Path) -> pd.DataFrame:
    doc = fitz.open(pdf_path)
    games: list[dict] = []
    for page in doc:
        games.extend(_parse_games(_page_tokens(page.get_text())))
    df = pd.DataFrame(games, columns=COLUMNS)
    # Scores are whole numbers; keep them as nullable ints for clean display.
    for col in ("home_score", "away_score", "system_num"):
        df[col] = df[col].astype("Int64")
    return df


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    for year in (2015, 2016):
        pdf = REFERENCE_DIR / f"NFL_Report_{year}.pdf"
        df = parse_report(pdf)
        out = DATA_DIR / f"report_{year}.csv"
        df.to_csv(out, index=False)
        bets = df["system_bet"].notna().sum()
        missing = (df["home"].isna() | df["away"].isna()).sum()
        print(
            f"{year}: {len(df)} games, {bets} bets, "
            f"{missing} rows with an unrecovered team name -> {out.name}"
        )


if __name__ == "__main__":
    main()
