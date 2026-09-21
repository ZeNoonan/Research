"""Estimate the home-advantage constants from the handicaps actually entered.

``season_report.HOME_ADVANTAGE`` starts at a provisional 5.0 because the URC
has no settled equivalent of the NFL's 3-point home field. That guess should
not survive contact with data. This fits it - and the long-haul penalty for
crossing between Europe and South Africa - from the handicaps themselves.

The market's handicap is the best available estimate of a match's true margin,
so regressing it on club strength plus a home term recovers what the market
thinks home advantage is worth::

    line = away_power - home_power - home_edge

with ``home_edge = HOME_ADVANTAGE + LONG_HAUL_PENALTY * (away side flew)``,
and zero at a neutral venue. Club ratings are nuisance parameters here; only
the two edge terms are reported.

This needs a decent spread of matches - ideally a full season, and at minimum
enough that every club appears home and away. It prints the counts so you can
judge that, and refuses to report a number it cannot support.

Run: ``python calibrate.py``
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import season_report
import teams

MIN_MATCHES = 40   # below this the fit is noise, not a measurement


def naive_edge(df: pd.DataFrame) -> float | None:
    """Mean of ``-line``: the home edge, *if* club strengths cancel out.

    They cancel exactly when every club has played as often at home as away.
    Early in a season they do not, so this carries club strength as well as
    home advantage - which is why it is reported beside a balance count rather
    than on its own.
    """
    played = df[~df["neutral"]]
    return None if played.empty else float(-played["line"].mean())


def balance(df: pd.DataFrame) -> tuple[int, int]:
    """(clubs whose home and away counts differ, the largest such gap)."""
    counts = pd.concat([
        df["home"].value_counts().rename("home"),
        df["away"].value_counts().rename("away"),
    ], axis=1).fillna(0).astype(int)
    gap = (counts["home"] - counts["away"]).abs()
    return int((gap > 0).sum()), int(gap.max())


def early_read(df: pd.DataFrame) -> None:
    """Print the naive home edge, split by trip type, with its health warning."""
    print("\nEarly read on home advantage - the mean of -line, which measures "
          "\nhome edge only once club strengths cancel out:\n")
    groups = [("all non-neutral", df),
              ("domestic only", df[~df["long_haul"]]),
              ("long-haul away trip", df[df["long_haul"]])]
    for label, block in groups:
        edge = naive_edge(block)
        if edge is None:
            print(f"  {label:<22} -       (none priced yet)")
        else:
            print(f"  {label:<22} {edge:+.1f} pts over {len(block[~block['neutral']])} matches")

    unbalanced, worst = balance(df)
    total_clubs = len(set(df["home"]) | set(df["away"]))
    if unbalanced:
        print(f"\n  {unbalanced} of {total_clubs} clubs have not played as often "
              f"at home as away (largest gap {worst}),")
        print("  so these figures still carry club strength, not just venue. "
              "Treat them\n  as a direction of travel, not a measurement.")
    else:
        print("\n  Every club has played as often at home as away, so club "
              "strengths cancel\n  and these figures are a fair read on venue alone.")


def gather() -> pd.DataFrame:
    """Every priced match across all season files."""
    frames = []
    for year in season_report.available_seasons():
        df = season_report.load_season(year)
        if not df.empty:
            frames.append(df[df["line"].notna()])
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def fit(df: pd.DataFrame) -> dict:
    """Least-squares fit of the two edge terms alongside club ratings."""
    clubs = sorted(set(df["home"]) | set(df["away"]))
    idx = {c: i for i, c in enumerate(clubs)}
    n_club = len(clubs)
    has_long_haul = bool((df["long_haul"] & ~df["neutral"]).any())
    width = n_club + 1 + int(has_long_haul)

    rows, targets = [], []
    for r in df.itertuples():
        row = np.zeros(width)
        row[idx[r.away]] += 1.0
        row[idx[r.home]] -= 1.0
        if not r.neutral:
            row[n_club] -= 1.0                      # HOME_ADVANTAGE
            if has_long_haul and r.long_haul:
                row[n_club + 1] -= 1.0              # LONG_HAUL_PENALTY
        rows.append(row)
        targets.append(r.line)

    A, b = np.array(rows), np.array(targets)
    params, *_ = np.linalg.lstsq(A, b, rcond=None)
    residual = b - A @ params
    return {
        "home_advantage": float(params[n_club]),
        "long_haul_penalty": float(params[n_club + 1]) if has_long_haul else None,
        "matches": len(df),
        "clubs": n_club,
        "residual_sd": float(residual.std(ddof=1)) if len(residual) > 1 else float("nan"),
        "ratings": {c: float(params[i]) for c, i in idx.items()},
    }


def main() -> None:
    df = gather()
    if df.empty:
        print("no priced matches yet - enter some handicaps and re-run")
        return

    home_away = pd.concat([
        df["home"].value_counts().rename("home"),
        df["away"].value_counts().rename("away"),
    ], axis=1).fillna(0).astype(int)
    print(f"{len(df)} priced matches across "
          f"{df['season'].nunique()} season file(s), {len(home_away)} clubs")

    early_read(df)

    if len(df) < MIN_MATCHES:
        print(f"\nUnder the {MIN_MATCHES}-match floor, so no *fitted* estimate is "
              f"reported: with this little\ndata the home term and the club ratings "
              f"are not separable. Current settings\nstand - HOME_ADVANTAGE = "
              f"{season_report.HOME_ADVANTAGE}, LONG_HAUL_PENALTY = "
              f"{season_report.LONG_HAUL_PENALTY}.")
        return

    one_sided = home_away[(home_away["home"] == 0) | (home_away["away"] == 0)]
    if len(one_sided):
        print(f"\nnote: {len(one_sided)} club(s) appear on only one side of the "
              f"draw, which the home term cannot be separated from:\n"
              f"{one_sided.to_string()}")

    r = fit(df)
    print(f"\nfitted home advantage : {r['home_advantage']:+.2f} pts "
          f"(currently set to {season_report.HOME_ADVANTAGE})")
    if r["long_haul_penalty"] is not None:
        print(f"fitted long-haul term : {r['long_haul_penalty']:+.2f} pts "
              f"(currently set to {season_report.LONG_HAUL_PENALTY})")
    else:
        print("fitted long-haul term : n/a - no Europe/South Africa trips priced yet")
    print(f"residual SD           : {r['residual_sd']:.2f} pts")

    ratings = pd.Series(r["ratings"]).sort_values(ascending=False)
    ratings -= ratings.mean()
    print("\nimplied club ratings over this sample (centred, points):")
    for club, value in ratings.items():
        print(f"  {club:<10} {value:+6.2f}   {teams.TEAMS[club]}")
    print("\nTo adopt these, edit HOME_ADVANTAGE / LONG_HAUL_PENALTY in "
          "season_report.py, then re-run season_report.py.")


if __name__ == "__main__":
    main()
