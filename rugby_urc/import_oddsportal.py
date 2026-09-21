"""Read an oddsportal results listing into a season file, inferring handicaps.

oddsportal publishes 1X2 decimal odds and the score, not a handicap, so each
match's line is derived with ``spread_from_odds`` and marked
``line_source = inferred-1x2`` - never left to pass as a quoted spread. Rows
whose quote is too coarse to pin a line (heavy favourites, where one 0.01 tick
is worth more than a point) are reported, and with ``--skip-coarse`` left
unpriced rather than filled with a number that cannot bear the weight.

The expected text is a copy of the results page, which repeats each club name
and separates fields by blank lines::

    16 May 2026
    1
    X
    2
    Finished

    24
    Munster
    Munster

    -
    Lions
    Lions

    17
    1.40

    22.02

    3.03

**Round numbers.** The listing carries dates and a stage label, not round
numbers. Regular match-weeks are therefore numbered backwards from
``--last-regular-round`` (default 18, the last round of a URC season), and
playoff weeks are numbered 19, 20, 21 in date order. If a round is missing from
the file the regular numbers shift, which is worth knowing but changes no
result: the power fit windows on calendar weeks, not round labels, and the only
thing the number decides is whether a match counts as a playoff.

Run::

    python import_oddsportal.py results.txt --season 2025
    python import_oddsportal.py results.txt --season 2025 --skip-coarse
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

import season_report
import spread_from_odds as sfo
import teams
from season_report import SEASON_COLUMNS

DATA_DIR = Path(__file__).parent / "data"

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
DATE_RE = re.compile(r"^(\d{1,2})\s+([A-Z][a-z]{2})\s+(20\d{2})(?:\s*-\s*(.+))?$")
FIELDS_PER_MATCH = 10  # score, club, club, "-", club, club, score, 1, X, 2


def parse(text: str) -> pd.DataFrame:
    """Pull (date, stage, clubs, score, odds) out of a pasted results page."""
    lines = [l.strip() for l in text.splitlines()]
    rows, skipped = [], []
    date, stage, i = None, "", 0

    while i < len(lines):
        line = lines[i]
        if m := DATE_RE.match(line):
            date = (f"{int(m.group(3))}-{MONTHS.index(m.group(2)) + 1:02d}-"
                    f"{int(m.group(1)):02d}")
            stage = (m.group(4) or "").strip()
            i += 1
            continue
        if line != "Finished":
            i += 1
            continue

        field, j = [], i + 1
        while j < len(lines) and len(field) < FIELDS_PER_MATCH:
            if lines[j]:
                field.append(lines[j])
            j += 1
        try:
            hs, home, _, dash, away, _, away_s, o1, ox, o2 = field
            if dash != "-":
                raise ValueError(f"expected '-' between the clubs, got {dash!r}")
            rows.append({
                "date": date, "stage": stage,
                "home": teams.canonical(home), "away": teams.canonical(away),
                "home_score": int(hs), "away_score": int(away_s),
                "odds_home": float(o1), "odds_draw": float(ox), "odds_away": float(o2),
            })
        except (ValueError, KeyError) as exc:
            skipped.append(f"{date}: {' / '.join(field[:6])} - {exc}")
        i = j

    if skipped:
        print(f"{len(skipped)} block(s) could not be read:")
        for s in skipped:
            print(f"  {s}")
    return pd.DataFrame(rows)


def assign_rounds(df: pd.DataFrame, last_regular: int) -> pd.DataFrame:
    """Number regular match-weeks backwards from ``last_regular``; playoffs after."""
    out = df.copy()
    day = pd.to_datetime(out["date"])
    iso = day.dt.isocalendar()
    out["week_key"] = iso["year"].astype(int) * 100 + iso["week"].astype(int)
    out["is_playoff"] = out["stage"].str.contains("play.?off", case=False, na=False)

    regular = sorted(out.loc[~out["is_playoff"], "week_key"].unique())
    rounds = {w: last_regular - (len(regular) - 1 - k) for k, w in enumerate(regular)}
    for k, w in enumerate(sorted(out.loc[out["is_playoff"], "week_key"].unique())):
        rounds[w] = season_report.REGULAR_ROUNDS + 1 + k

    out["round"] = out["week_key"].map(rounds)
    return out


def to_season_rows(df: pd.DataFrame, sigma: float, skip_coarse: bool) -> pd.DataFrame:
    rows = []
    for r in df.itertuples():
        quote = (r.odds_home, r.odds_draw, r.odds_away)
        coarse = sfo.is_coarse(*quote, sigma)
        priced = not (coarse and skip_coarse)
        rows.append({
            "round": int(r.round), "date": r.date,
            "home": r.home, "away": r.away, "neutral": "",
            "line": round(sfo.line_from_odds(*quote, sigma) * 2) / 2 if priced else "",
            "line_source": season_report.LINE_INFERRED if priced else "",
            "home_score": r.home_score, "away_score": r.away_score,
            "home_turnovers_conceded": "", "away_turnovers_conceded": "",
            "home_turnovers_won": "", "away_turnovers_won": "",
        })
    return pd.DataFrame(rows, columns=SEASON_COLUMNS)


def filled(value) -> bool:
    """True when a cell holds something, treating NaN/NA/"nan" as empty."""
    if value is None or pd.isna(value):
        return False
    return str(value).strip().lower() not in ("", "nan", "nat", "none")


def merge_into_season(new: pd.DataFrame, season: int) -> tuple[Path, int]:
    """Write these matches into the season file, keeping anything already there.

    A **quoted** handicap is never overwritten by an inferred one. A line whose
    ``line_source`` is blank was read off a real spread market, which is the
    better number by definition, so re-running this import leaves it alone -
    the same rule ``nfl_report`` applies to lines it already holds.
    """
    out = DATA_DIR / f"season_{season}.csv"
    kept = 0
    if out.exists():
        existing = pd.read_csv(out, dtype=str).fillna("")
        for col in SEASON_COLUMNS:
            if col not in existing.columns:
                existing[col] = ""
        quoted = {(r.date, r.home, r.away)
                  for r in existing.itertuples()
                  if str(r.line).strip() and not str(r.line_source).strip()}
        if quoted:
            drop = new.apply(lambda r: (r["date"], r["home"], r["away"]) in quoted,
                             axis=1)
            kept = int(drop.sum())
            new = new.copy()
            new.loc[drop, ["line", "line_source"]] = ""
        combined = pd.concat([existing[SEASON_COLUMNS], new.astype(str)],
                             ignore_index=True)
        # A later read of the same match wins, but only for the fields it fills.
        # ``filled`` must test for missing explicitly: ``str(float("nan"))`` is
        # "nan", which is truthy, so a blank would otherwise win the merge and
        # erase a value that was already there.
        combined = combined.groupby(["date", "home", "away"], as_index=False).agg(
            lambda col: next((v for v in reversed(list(col)) if filled(v)), ""))
    else:
        combined = new.astype(str)
    combined = combined[SEASON_COLUMNS].sort_values(["date", "round", "home"])
    combined.to_csv(out, index=False)
    return out, kept


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="text pasted from the results page")
    ap.add_argument("--season", type=int, required=True, help="season start year")
    ap.add_argument("--sigma", type=float, default=sfo.DEFAULT_SIGMA,
                    help="margin standard deviation used for the conversion")
    ap.add_argument("--last-regular-round", type=int, default=season_report.REGULAR_ROUNDS,
                    help="round number of the last regular match-week in this file")
    ap.add_argument("--skip-coarse", action="store_true",
                    help="leave heavy favourites unpriced rather than guessing")
    args = ap.parse_args()

    raw = parse(args.source.read_text(encoding="utf-8"))
    if raw.empty:
        raise SystemExit("no matches found - is this the results page text?")
    dated = assign_rounds(raw, args.last_regular_round)
    rows = to_season_rows(dated, args.sigma, args.skip_coarse)

    # Keep the raw quotes beside the season file: the inferred line is derived
    # from them, so a later check of sigma needs them, not just the result.
    quotes = dated[["date", "round", "home", "away",
                    "odds_home", "odds_draw", "odds_away"]]
    quote_path = Path(__file__).parent / "entry" / f"urc_{args.season}_odds.csv"
    quote_path.parent.mkdir(exist_ok=True)
    if quote_path.exists():
        prior = pd.read_csv(quote_path)
        quotes = (pd.concat([prior, quotes])
                  .drop_duplicates(subset=["date", "home", "away"], keep="last"))
    quotes.sort_values(["date", "home"]).to_csv(quote_path, index=False)

    coarse = [r for r in dated.itertuples()
              if sfo.is_coarse(r.odds_home, r.odds_draw, r.odds_away, args.sigma)]
    path, kept = merge_into_season(rows, args.season)

    weeks = dated.groupby("round")["date"].agg(["min", "max", "count"])
    print(f"read {len(raw)} matches, {raw['date'].min()} to {raw['date'].max()}")
    print(f"handicaps inferred at sigma = {args.sigma} -> "
          f"{path.relative_to(Path(__file__).parent)}\n")
    print("  round    dates                      matches")
    for rnd, row in weeks.iterrows():
        label = " (playoff)" if rnd > season_report.REGULAR_ROUNDS else ""
        span = row["min"] if row["min"] == row["max"] else f"{row['min']} .. {row['max']}"
        print(f"  {int(rnd):>5}    {span:<26} {int(row['count'])}{label}")

    if kept:
        print(f"\n{kept} match(es) already carry a handicap quoted as a handicap; "
              f"those are\nleft untouched - a real line beats an inferred one.")
    if coarse:
        verb = "left unpriced" if args.skip_coarse else "priced, but flagged"
        print(f"\n{len(coarse)} match(es) {verb}: the quote moves more than a point "
              f"of\nhandicap per 0.01 tick, so it cannot pin a line:")
        for r in coarse:
            pts = sfo.tick_sensitivity(r.odds_home, r.odds_draw, r.odds_away, args.sigma)
            print(f"  {r.date}  {r.home:<10} v {r.away:<10} "
                  f"{r.odds_home:>6} / {r.odds_away:<6}  {pts:.1f} pts per tick")


if __name__ == "__main__":
    main()
