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
    ("line", "THE HANDICAP, from the home team's point of view. "
             "NEGATIVE = home favoured (-7.5 means home must win by 8 to cover); "
             "POSITIVE = home receiving points. This is the one number needed to "
             "make a pick."),
    ("home_score", "Home points scored. Leave blank until played."),
    ("away_score", "Away points scored."),
    ("home_turnovers_conceded", "Turnovers the HOME side conceded, from the URC "
                                "match centre. Leave blank until played."),
    ("away_turnovers_conceded", "Turnovers the AWAY side conceded."),
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
        for col in ("line", "home_score", "away_score",
                    "home_turnovers_conceded", "away_turnovers_conceded"):
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


def import_sheet(year: int, source: Path | None) -> Path:
    df, path = read_filled(year, source)
    for col in SEASON_COLUMNS:
        if col not in df.columns:
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

    df = df.sort_values(["date", "round", "home"])
    out = DATA_DIR / f"season_{year}.csv"
    if out.exists():
        shutil.copy(out, out.with_suffix(".csv.bak"))
    df.to_csv(out, index=False)

    priced = int((df["line"].str.strip() != "").sum())
    turns = int((df["home_turnovers_conceded"].str.strip() != "").sum())
    print(f"read {path.name}: {len(df)} matches -> {out.relative_to(HERE)}")
    print(f"  {priced} with a handicap, {turns} with turnover counts")
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
