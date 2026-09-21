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

MIN_MATCHES = 40   # below this the estimate is noise, not a measurement


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

    if len(df) < MIN_MATCHES:
        print(f"\nthat is under the {MIN_MATCHES}-match floor, so no estimate is "
              f"reported: with this little data the home term and the club "
              f"ratings are not separable.\ncurrent settings stand - "
              f"HOME_ADVANTAGE = {season_report.HOME_ADVANTAGE}, "
              f"LONG_HAUL_PENALTY = {season_report.LONG_HAUL_PENALTY}")
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
