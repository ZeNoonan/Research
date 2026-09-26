"""Export a season as a spreadsheet to type into, and read it back.

The two inputs this project needs - handicaps from an odds site, turnover
counts from the URC match centre - are read off web pages by hand. This builds
the sheet to hold them and reads the filled sheet back into
``data/season_<year>.csv``, so nothing is hand-edited in the CSV itself.

The workbook has a frozen header, a **Clubs** sheet the ``home``/``away``
columns validate against (so a misspelt club is rejected at the cell rather
than found later by the importer), and a **How to fill this in** sheet holding
the sign conventions.

Run::

    python entry_sheet.py export --season 2026            # -> entry/urc_2026_entry.xlsx + .csv
    python entry_sheet.py export --season 2025 --skeleton # blank rows, rounds pre-filled
    python entry_sheet.py import --season 2026            # filled sheet -> data/season_2026.csv
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import season_report
import teams
from season_report import SEASON_COLUMNS

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
ENTRY_DIR = HERE / "entry"

# Columns the user fills in, and what belongs in them.
GUIDE = [
    ("round", "Round number. 1-18 regular season, 19 = quarter-final, "
              "20 = semi-final, 21 = grand final."),
    ("date", "Match date, YYYY-MM-DD."),
    ("home", "Home club, from the Clubs sheet. Sponsor names are fine on import "
             "(\"Vodacom Bulls\"), but the dropdown keeps it tidy."),
    ("away", "Away club."),
    ("neutral", "Y if played at neither club's ground, otherwise leave blank. "
                "Turns off the home-advantage term in the rating fit."),
    ("opening_line", "The handicap when the round is first priced, from the home "
                     "team's point of view. NEGATIVE = home favoured (-7.5 means "
                     "home must win by 8 to cover); POSITIVE = home receiving "
                     "points. The model picks on it only until closing_line is "
                     "filled; after that it is kept as a record of the move."),
    ("closing_line", "The handicap as late as practical before kick-off - after "
                     "the teams are named. Same sign convention. THIS is the line "
                     "the model picks, rates and grades on, as nfl_report does. "
                     "Leave blank until you have it."),
    ("line_source", "Leave blank for a handicap you read off a spread market. "
                    "\"inferred-1x2\" means it was derived from win odds by "
                    "spread_from_odds.py and is an estimate, not a quote."),
    ("home_score", "Home points scored. Leave blank until played."),
    ("away_score", "Away points scored."),
    ("home_turnovers_conceded", "Turnovers the HOME side conceded, from the URC "
                                "match centre. Leave blank until played."),
    ("away_turnovers_conceded", "Turnovers the AWAY side conceded."),
    ("home_turnovers_won", "Turnovers the HOME side won. Needed as well as "
                           "conceded: a club's margin is its own conceded minus "
                           "its own won, and in rugby those are separate counts."),
    ("away_turnovers_won", "Turnovers the AWAY side won."),
]

# The shape of a URC season, used to lay out a blank skeleton.
SKELETON = [(r, 8) for r in range(15, 19)] + [(19, 4), (20, 2), (21, 1)]

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
FILLME_FILL = PatternFill("solid", fgColor="FFF2CC")


def season_frame(year: int, skeleton: bool) -> pd.DataFrame:
    """The rows to export: the known fixtures, or a blank skeleton to type into."""
    path = DATA_DIR / f"season_{year}.csv"
    df = pd.read_csv(path, dtype=str).fillna("") if path.exists() else pd.DataFrame()
    for col in SEASON_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[SEASON_COLUMNS]
    if skeleton and df.empty:
        df = pd.DataFrame(
            [{**{c: "" for c in SEASON_COLUMNS}, "round": rnd}
             for rnd, count in SKELETON for _ in range(count)],
            columns=SEASON_COLUMNS)
    return df.reset_index(drop=True)


def export(year: int, skeleton: bool) -> tuple[Path, Path]:
    df = season_frame(year, skeleton)
    ENTRY_DIR.mkdir(exist_ok=True)
    label = season_report.season_label(year)
    csv_path = ENTRY_DIR / f"urc_{year}_entry.csv"
    xlsx_path = ENTRY_DIR / f"urc_{year}_entry.xlsx"
    df.to_csv(csv_path, index=False)

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Fixtures", index=False)
        pd.DataFrame({"Club": sorted(teams.TEAMS),
                      "Territory": [teams.TEAMS[t] for t in sorted(teams.TEAMS)]}
                     ).to_excel(writer, sheet_name="Clubs", index=False)
        pd.DataFrame(GUIDE, columns=["Column", "What goes in it"]).to_excel(
            writer, sheet_name="How to fill this in", index=False)

        book = writer.book
        sheet = writer.sheets["Fixtures"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for i, col in enumerate(SEASON_COLUMNS, start=1):
            cell = sheet.cell(row=1, column=i)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = HEADER_FILL
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
            sheet.column_dimensions[get_column_letter(i)].width = max(11, min(len(col) + 4, 26))

        last = max(len(df) + 1, 2)
        # Highlight the columns that are actually typed in.
        for col in ("opening_line", "closing_line", "home_score", "away_score",
                    "home_turnovers_conceded", "away_turnovers_conceded",
                    "home_turnovers_won", "away_turnovers_won"):
            letter = get_column_letter(SEASON_COLUMNS.index(col) + 1)
            for row in range(2, last + 1):
                sheet[f"{letter}{row}"].fill = FILLME_FILL

        club_range = f"'Clubs'!$A$2:$A${len(teams.TEAMS) + 1}"
        for col in ("home", "away"):
            letter = get_column_letter(SEASON_COLUMNS.index(col) + 1)
            dv = DataValidation(type="list", formula1=club_range, allow_blank=True,
                                showErrorMessage=True, errorTitle="Not a URC club",
                                error="Pick a club from the Clubs sheet.")
            sheet.add_data_validation(dv)
            dv.add(f"{letter}2:{letter}{last}")

        guide = writer.sheets["How to fill this in"]
        guide.column_dimensions["A"].width = 28
        guide.column_dimensions["B"].width = 96
        guide["A1"].font = guide["B1"].font = Font(bold=True, color="FFFFFF")
        guide["A1"].fill = guide["B1"].fill = HEADER_FILL
        for row in range(2, len(GUIDE) + 2):
            guide[f"B{row}"].alignment = Alignment(wrap_text=True, vertical="top")
            guide[f"A{row}"].font = Font(bold=True)
        book.properties.title = f"URC {label} data entry"

    print(f"{label}: {len(df)} rows")
    print(f"  {xlsx_path.relative_to(HERE)}")
    print(f"  {csv_path.relative_to(HERE)}")
    return xlsx_path, csv_path


def read_filled(year: int, source: Path | None) -> pd.DataFrame:
    """Read the filled entry sheet, preferring .xlsx, then .csv."""
    candidates = [source] if source else [
        ENTRY_DIR / f"urc_{year}_entry.xlsx", ENTRY_DIR / f"urc_{year}_entry.csv"]
    for path in candidates:
        if path and path.exists():
            df = (pd.read_excel(path, sheet_name="Fixtures", dtype=str)
                  if path.suffix == ".xlsx" else pd.read_csv(path, dtype=str))
            return df.fillna(""), path
    raise FileNotFoundError(
        f"no filled sheet for {year}; looked for {', '.join(str(c) for c in candidates)}")


KEY = ["date", "home", "away"]
# Filled in once a match is played. A row holding any of these is a result.
RESULT_COLUMNS = ["home_score", "away_score",
                  "home_turnovers_conceded", "away_turnovers_conceded",
                  "home_turnovers_won", "away_turnovers_won"]


def keep_existing(sheet: pd.DataFrame, current: pd.DataFrame,
                  name: str) -> tuple[pd.DataFrame, int]:
    """Merge a sheet over the season file without ever erasing a value.

    The sheet is typed in by hand while other inputs arrive separately - a
    round's scores and turnovers come from ``urc_scraper.py`` through
    ``import_turnovers.py`` - so a sheet exported on Monday and sent back on
    Thursday has blank cells for everything loaded in between. Writing it over
    the season file wholesale would erase those results without a word.

    So, cell by cell: a value in the sheet wins (that is how a line is
    corrected), and a blank keeps whatever the season file already holds. A
    column missing from the sheet altogether is the same case, so a sheet from
    an older export imports safely rather than being refused. The one thing
    refused outright is a played match missing from the sheet entirely, since
    dropping the row would drop its result.
    """
    for col in SEASON_COLUMNS:
        if col not in current.columns:
            current[col] = ""
    stored = current.set_index(KEY)

    typed = set(map(tuple, sheet[KEY].to_numpy()))
    played = current[(current[RESULT_COLUMNS].apply(lambda c: c.str.strip()) != "").any(axis=1)]
    lost = [f"{r.date} {r.home} v {r.away}" for r in played.itertuples()
            if (r.date, r.home, r.away) not in typed]
    if lost:
        raise ValueError(
            f"cannot import {name}: it leaves out {len(lost)} played match(es) "
            f"whose results the season file holds, and the import would drop "
            f"them: {'; '.join(lost[:4])}")

    sheet = sheet.copy()
    kept = 0
    for i, row in sheet.iterrows():
        key = (row["date"], row["home"], row["away"])
        if key not in stored.index:
            continue
        for col in SEASON_COLUMNS:
            if col in KEY:
                continue
            if str(row[col]).strip() == "" and str(stored.at[key, col]).strip() != "":
                sheet.at[i, col] = stored.at[key, col]
                kept += 1
    return sheet, kept


def import_sheet(year: int, source: Path | None) -> Path:
    df, path = read_filled(year, source)
    out = DATA_DIR / f"season_{year}.csv"
    absent = [c for c in SEASON_COLUMNS if c not in df.columns]
    ignored = [c for c in df.columns if c not in SEASON_COLUMNS]
    # Columns the sheet lacks (an older export) are treated as blank, and a
    # blank never erases - see keep_existing below.
    for col in absent:
        df[col] = ""
    df = df[SEASON_COLUMNS]
    df = df[(df["home"].str.strip() != "") & (df["away"].str.strip() != "")].copy()

    # Normalise club names now so a sponsor spelling never reaches data/.
    problems = []
    for col in ("home", "away"):
        resolved = []
        for i, name in df[col].items():
            try:
                resolved.append(teams.canonical(name))
            except KeyError:
                problems.append(f"row {i + 2}: unrecognised club {name!r}")
                resolved.append(name)
        df[col] = resolved
    # Excel turns a typed date into a timestamp; keep the plain date.
    df["date"] = (pd.to_datetime(df["date"], errors="coerce", format="mixed")
                  .dt.strftime("%Y-%m-%d").fillna(""))
    if problems:
        raise ValueError("cannot import:\n  " + "\n  ".join(problems))

    kept = 0
    if out.exists():
        df, kept = keep_existing(df, pd.read_csv(out, dtype=str).fillna(""), path.name)

    df = df.sort_values(["date", "round", "home"])
    if out.exists():
        shutil.copy(out, out.with_suffix(".csv.bak"))
    df.to_csv(out, index=False)

    has_open = df["opening_line"].str.strip() != ""
    has_close = df["closing_line"].str.strip() != ""
    turns = int((df["home_turnovers_conceded"].str.strip() != "").sum())
    print(f"read {path.name}: {len(df)} matches -> {out.relative_to(HERE)}")
    print(f"  {int((has_open | has_close).sum())} with a handicap "
          f"({int(has_close.sum())} closing), {turns} with turnover counts")
    if kept:
        print(f"  kept {kept} value(s) already in {out.name} that the sheet left "
              f"blank - a blank never erases")
    if absent:
        print(f"  not in the sheet, so kept from {out.name}: {', '.join(absent)}")
    if ignored:
        print(f"  not a season column, so ignored: {', '.join(ignored)}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("export", "import"))
    ap.add_argument("--season", type=int, required=True, help="season start year")
    ap.add_argument("--skeleton", action="store_true",
                    help="export blank rows with round numbers pre-filled")
    ap.add_argument("--file", type=Path, help="explicit sheet to import")
    args = ap.parse_args()

    if args.action == "export":
        export(args.season, args.skeleton)
    else:
        import_sheet(args.season, args.file)


if __name__ == "__main__":
    main()
