"""Check inferred handicaps against real ones, and re-fit sigma from them.

``spread_from_odds`` turns 1X2 odds into a handicap through one free parameter,
the margin standard deviation ``sigma``. Fitting it from results needs a lot of
matches, because a margin is a noisy draw around the line. **A real handicap is
not noisy**: it is the quantity being estimated, observed directly. So a
handful of quoted lines pins sigma far harder than fifty results do.

For each checked match, ``sigma = -actual_line / z``, where ``z`` is the
standardised win probability from the odds. The precision of that is best at
moderate lines: near a pick'em ``z`` is close to zero and dividing by it
explodes, and at a heavy favourite ``z`` is itself poorly determined because
the odds are quantised. The sample this exports is weighted accordingly.

Run::

    python line_check.py export --season 2025     # -> entry/urc_2025_line_check.csv
    python line_check.py check  --season 2025     # after filling actual_line
    python line_check.py coarse --season 2025     # only the un-inferable matches
    python line_check.py close  --season 2025     # bets a line error could flip
    python line_check.py apply  --season 2025     # write every real line filled in
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import season_report
import spread_from_odds as sfo

HERE = Path(__file__).parent
ENTRY_DIR = HERE / "entry"

COLUMNS = ["date", "round", "home", "away", "odds_home", "odds_draw", "odds_away",
           "inferred_line", "pts_per_tick", "actual_line"]
CLOSE_COLUMNS = ["date", "round", "home", "away", "inferred_line", "bet", "result",
                 "covered_by", "actual_line"]

# How far an inferred line can be trusted: about a point and a half from a
# readable quote (the line check's error on those), about three from a quote
# too coarse to pin (two 1.01 shots came back three points apart).
FINE_BAND = 1.5
COARSE_BAND = 3.0

# Every sheet a real handicap can be typed into: (file stem, worksheet name).
SHEETS = (("line_check", "Line check"), ("coarse_lines", "Coarse quotes"),
          ("close_calls", "Close calls"))


def select(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    """A sample spread across the range, weighted where sigma is best measured.

    Bands are by inferred line: the middle bands carry most of the sample
    because that is where a quoted line constrains sigma tightest, with a few
    from each extreme to test the ends rather than assume them.
    """
    bands = [(0.0, 4.0, 2), (4.0, 9.0, 3), (9.0, 15.0, 4),
             (15.0, 22.0, 3), (22.0, 99.0, 2)]
    picked = []
    for lo, hi, want in bands:
        block = df[df["inferred_line"].abs().between(lo, hi, inclusive="left")]
        if block.empty:
            continue
        # Spread the picks across the band rather than taking neighbours.
        step = max(len(block) // want, 1)
        picked.append(block.iloc[::step].head(want))
    out = pd.concat(picked).drop_duplicates(subset=["date", "home", "away"])
    return out.sort_values(["date", "home"]).head(n)


def coarse(season: int) -> Path:
    """Export only the matches whose quote is too coarse to infer a line from.

    These are the ones a real handicap would actually improve. Everywhere else
    the odds already pin the line to within about a point, so a quoted number
    would only confirm what is there; here the odds carry almost nothing - two
    matches priced identically at 1.01 had real handicaps three points apart.
    """
    rows, quotes = _load(season)
    merged = rows.merge(quotes, on=["date", "home", "away"], how="inner")
    merged["pts_per_tick"] = [
        round(sfo.tick_sensitivity(r.odds_home, r.odds_draw, r.odds_away), 2)
        for r in merged.itertuples()]
    merged["inferred_line"] = merged["closing_line"]
    merged["actual_line"] = ""
    # Carry over anything already answered in the line check, so the same
    # number is never looked up twice.
    known = _known_lines(season)
    if known:
        merged["actual_line"] = [
            known.get((r.date, r.home, r.away), "") for r in merged.itertuples()]
    sample = merged[merged["pts_per_tick"] > sfo.COARSE_POINTS_PER_TICK]
    sample = sample.sort_values("pts_per_tick", ascending=False)[COLUMNS]

    out = _write_sheet(sample, season, "coarse_lines", "Coarse quotes")
    print(f"{len(sample)} matches the odds cannot price -> "
          f"{out.relative_to(HERE)} (+ .xlsx)")
    print("Fill `actual_line` with the real home handicap "
          "(negative = home favoured).")
    print("Once filled, re-run import_oddsportal.py: a quoted line is never "
          "overwritten by\nan inferred one, so these will stick.")
    return out


def _sheet_lines(season: int, stem: str, sheet: str) -> dict:
    """Real handicaps filled in one entry sheet, by match - the .xlsx if present."""
    for path in (ENTRY_DIR / f"urc_{season}_{stem}.xlsx",
                 ENTRY_DIR / f"urc_{season}_{stem}.csv"):
        if not path.exists():
            continue
        df = (pd.read_excel(path, sheet_name=sheet) if path.suffix == ".xlsx"
              else pd.read_csv(path))
        df = df[pd.to_numeric(df["actual_line"], errors="coerce").notna()]
        return {(str(r.date)[:10], r.home, r.away): float(r.actual_line)
                for r in df.itertuples()}
    return {}


def _known_lines(season: int) -> dict:
    """Every real handicap filled in any entry sheet, by match."""
    known = {}
    for stem, sheet in SHEETS:
        known.update(_sheet_lines(season, stem, sheet))
    return known


def _write_sheet(frame: pd.DataFrame, season: int, stem: str, sheet: str) -> Path:
    """Write an entry sheet as .csv and .xlsx; the .xlsx is the one to fill."""
    ENTRY_DIR.mkdir(exist_ok=True)
    out = ENTRY_DIR / f"urc_{season}_{stem}.csv"
    frame.to_csv(out, index=False)
    with pd.ExcelWriter(out.with_suffix(".xlsx"), engine="openpyxl") as w:
        frame.to_excel(w, sheet_name=sheet, index=False)
        ws = w.sheets[sheet]
        ws.freeze_panes = "A2"
        for i, col in enumerate(frame.columns, start=1):
            ws.column_dimensions[chr(64 + i)].width = max(12, len(col) + 3)
    return out


def close_calls(season: int) -> Path:
    """Export the graded bets that a small error in an inferred line could flip.

    A backtest on inferred lines grades every bet against a line known only to
    within a point or two. Where the bet covered, or failed to, by less than
    that, the W or L rests on the inference rather than the result - so those
    are the matches where a real handicap changes the record, and the only
    ones worth looking up. Settled on a quoted line, a bet is final and is
    left out.
    """
    report = season_report.build_reports()[season]
    rows, quotes = _load(season)
    rows = rows.astype({"date": str})
    graded = (report[report["result"].notna()]
              .merge(rows[["date", "home", "away", "line_source"]],
                     on=["date", "home", "away"])
              .merge(quotes, on=["date", "home", "away"], how="left"))
    inferred = graded["line_source"] == season_report.LINE_INFERRED
    graded = graded[inferred].copy()
    home_by = graded["home_score"] - graded["away_score"] + graded["line"]
    graded["covered_by"] = home_by.where(graded["system_bet"] == graded["home"], -home_by)
    coarse = [sfo.is_coarse(r.odds_home, r.odds_draw, r.odds_away)
              for r in graded.itertuples()]
    band = pd.Series(coarse, index=graded.index).map({True: COARSE_BAND, False: FINE_BAND})
    sample = graded[graded["covered_by"].abs() <= band].copy()
    sample["inferred_line"] = sample["line"]
    sample["bet"] = sample["system_bet"]
    known = _known_lines(season)
    sample["actual_line"] = [known.get((r.date, r.home, r.away), "")
                             for r in sample.itertuples()]
    sample = sample[CLOSE_COLUMNS]

    out = _write_sheet(sample, season, "close_calls", "Close calls")
    wins = int((sample["result"] == "W").sum())
    print(f"{len(graded)} bets graded on inferred lines; {len(sample)} settled within "
          f"the line's uncertainty ({wins} W, {len(sample) - wins} L) -> "
          f"{out.name} (+ .xlsx)")
    print("Fill `actual_line` with the real home handicap (negative = home "
          "favoured),\nthen run `apply` and season_report.py.")
    return out


def apply_real(season: int) -> None:
    """Write every real handicap found in the entry sheets into the season file.

    They land with a blank ``line_source``, which marks them as quoted rather
    than inferred - and that is what stops ``import_oddsportal.py`` overwriting
    them on its next run.
    """
    known = _known_lines(season)
    if not known:
        raise SystemExit("no real handicaps filled in yet")

    season_path = season_report.DATA_DIR / f"season_{season}.csv"
    df = pd.read_csv(season_path, dtype=str).fillna("")
    applied = []
    for i, r in df.iterrows():
        value = known.get((str(r["date"])[:10], r["home"], r["away"]))
        if value is None:
            continue
        was = r["closing_line"]
        df.at[i, "closing_line"] = f"{value:g}"
        df.at[i, "line_source"] = season_report.LINE_QUOTED
        applied.append((r["date"], r["home"], r["away"], was, f"{value:g}"))
    df.to_csv(season_path, index=False)

    print(f"{len(applied)} real handicap(s) written to {season_path.name}, "
          f"marked as quoted:\n")
    print(f"  {'date':<12}{'match':<26}{'was':>8}{'now':>8}")
    for date, home, away, was, now in applied:
        print(f"  {date:<12}{home + ' v ' + away:<26}{was:>8}{now:>8}")
    print("\nRe-run season_report.py to fold them into the power ratings.")


def _load(season: int):
    season_file = season_report.DATA_DIR / f"season_{season}.csv"
    odds_file = ENTRY_DIR / f"urc_{season}_odds.csv"
    if not odds_file.exists():
        raise SystemExit(f"need the quoted odds: expected {odds_file}, "
                         f"written by import_oddsportal.py")
    raw = pd.read_csv(odds_file)
    return (pd.read_csv(season_file),
            raw[["date", "home", "away", "odds_home", "odds_draw", "odds_away"]])


def export(season: int) -> Path:
    season_file = season_report.DATA_DIR / f"season_{season}.csv"
    rows = pd.read_csv(season_file)
    raw = pd.read_csv(ENTRY_DIR / f"urc_{season}_odds.csv") if (
        ENTRY_DIR / f"urc_{season}_odds.csv").exists() else None
    if raw is None:
        raise SystemExit(
            f"need the quoted odds to check against: expected "
            f"{ENTRY_DIR / f'urc_{season}_odds.csv'}, written by import_oddsportal.py")

    # Both frames carry `round`; keep the season file's and take only the
    # quotes from the odds file, so the merge does not produce round_x/round_y.
    quotes = raw[["date", "home", "away", "odds_home", "odds_draw", "odds_away"]]
    merged = rows.merge(quotes, on=["date", "home", "away"], how="inner")
    merged["inferred_line"] = merged["closing_line"]
    merged["pts_per_tick"] = [
        round(sfo.tick_sensitivity(r.odds_home, r.odds_draw, r.odds_away), 2)
        for r in merged.itertuples()]
    merged["actual_line"] = ""
    sample = select(merged)[COLUMNS]

    out = _write_sheet(sample, season, "line_check", "Line check")
    print(f"{len(sample)} matches -> {out.relative_to(HERE)} (+ .xlsx)")
    print("Fill `actual_line` with the real home handicap "
          "(negative = home favoured), then run `check`.")
    return out


def check(season: int) -> None:
    path = ENTRY_DIR / f"urc_{season}_line_check.csv"
    xlsx = path.with_suffix(".xlsx")
    df = (pd.read_excel(xlsx, sheet_name="Line check") if xlsx.exists()
          else pd.read_csv(path))
    df = df[pd.to_numeric(df["actual_line"], errors="coerce").notna()].copy()
    if df.empty:
        raise SystemExit(f"no actual_line values filled in {path.name} yet")
    df["actual_line"] = pd.to_numeric(df["actual_line"])

    # z straight from the odds, not back-derived from the rounded inferred line.
    df["z"] = [sfo.NORMAL.inv_cdf(
        sfo.two_way_home(*sfo.shin_probabilities(r.odds_home, r.odds_draw,
                                                 r.odds_away)[:2]))
        for r in df.itertuples()]
    df["error"] = df["inferred_line"] - df["actual_line"]
    df["coarse"] = df["pts_per_tick"] > sfo.COARSE_POINTS_PER_TICK

    print(f"{len(df)} checked matches\n")
    print(df[["date", "home", "away", "inferred_line", "actual_line", "error",
              "pts_per_tick"]].to_string(index=False))

    def sigma_of(block: pd.DataFrame) -> float:
        """Least-squares sigma: minimises sum (actual + sigma*z)^2.

        Weighting by z falls out of the algebra, so a near-pick'em - where
        dividing one line by one z would explode - contributes almost nothing
        instead of having to be thrown away by hand.
        """
        zz = (block["z"] ** 2).sum()
        return float("nan") if zz == 0 else -(block["z"] * block["actual_line"]).sum() / zz

    fine, coarse = df[~df["coarse"]], df[df["coarse"]]
    print(f"\noverall bias (inferred - actual): {df['error'].mean():+.2f} pts, "
          f"MAE {df['error'].abs().mean():.2f}")
    print("\nBut that overall bias is two opposite errors cancelling, so split them:\n")
    for label, block in (("quotes fine enough to read", fine),
                         ("quotes too coarse (1.01-ish)", coarse)):
        if block.empty:
            continue
        print(f"  {label:<30} n={len(block):<3} bias {block['error'].mean():+5.2f}  "
              f"MAE {block['error'].abs().mean():4.2f}  sigma {sigma_of(block):5.2f}")

    print(f"\nsigma currently set to {sfo.DEFAULT_SIGMA}; "
          f"fitted on the readable quotes: {sigma_of(fine):.2f}")
    if not coarse.empty:
        print(f"The coarse rows want {sigma_of(coarse):.2f} instead - the two cannot "
              f"both be right\nwith one normal, which is a finding, not a fitting "
              f"problem. See the README.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("export", "check", "coarse", "close", "apply"))
    ap.add_argument("--season", type=int, required=True)
    args = ap.parse_args()
    {"export": export, "check": check, "coarse": coarse, "close": close_calls,
     "apply": apply_real}[args.action](args.season)


if __name__ == "__main__":
    main()
