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
    merged["inferred_line"] = merged["line"]
    merged["pts_per_tick"] = [
        round(sfo.tick_sensitivity(r.odds_home, r.odds_draw, r.odds_away), 2)
        for r in merged.itertuples()]
    merged["actual_line"] = ""
    sample = select(merged)[COLUMNS]

    ENTRY_DIR.mkdir(exist_ok=True)
    out = ENTRY_DIR / f"urc_{season}_line_check.csv"
    sample.to_csv(out, index=False)
    with pd.ExcelWriter(out.with_suffix(".xlsx"), engine="openpyxl") as w:
        sample.to_excel(w, sheet_name="Line check", index=False)
        sheet = w.sheets["Line check"]
        sheet.freeze_panes = "A2"
        for i, col in enumerate(COLUMNS, start=1):
            sheet.column_dimensions[chr(64 + i)].width = max(12, len(col) + 3)
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
    ap.add_argument("action", choices=("export", "check"))
    ap.add_argument("--season", type=int, required=True)
    args = ap.parse_args()
    (export if args.action == "export" else check)(args.season)


if __name__ == "__main__":
    main()
