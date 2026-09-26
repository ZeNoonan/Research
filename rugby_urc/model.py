"""The five-factor against-the-spread system, applied to the URC.

This is the same additive binary-factor engine as ``nfl_report/model.py`` —
Aaron Brown's demonstration system — with the turnover factor re-expressed for
rugby union. The logic is deliberately unchanged: five binary factors each vote
for the home side (+1), the away side (-1) or neither (0), their sum is the
**System #**, and the system bets the home side at +3 or more and the away side
at -3 or less.

Nothing here is yet validated on rugby. The NFL version reproduces seven
published seasons; this one inherits its structure on the argument that the
three intuitions behind it — line over-reaction, turnover luck and the
bookmaker's interest in a ~50% cover rate — are not football-specific. Whether
they hold in the URC is the question this project exists to answer, so treat
the thresholds as inherited defaults, not as findings.

Sign conventions (as stored in the report and in ``data/``)
----------------------------------------------------------
* ``line``  - the home handicap: **negative = home favoured**, positive = home
  receiving points. A home side at -7.5 must win by 8 to cover.
* ``lgt``   - *Last Game Turnover*: a side's **net turnovers conceded** in its
  previous match (own turnovers conceded minus the opponent's). Positive = it
  coughed up more ball than its opponent did. Zero-sum by construction, so the
  two sides in a match carry equal and opposite values. (Not own conceded
  minus own won: see ``season_report.add_lgt`` for why that fails in rugby.)
* ``stdc``  - *Season To Date Cover*: net handicap covers so far this season
  (covers minus non-covers). Negative = a "hungry" side that has been failing
  to cover; positive = a "fat" one.
* ``power`` - the side's power rating in points, fit from recent handicaps by
  ``season_report.py``.

The five factors
----------------
1. Power / over-reaction - back the side the handicap shortchanges against the
   power ratings.
2. Turnover, home - back a home side that lost the turnover count last time out.
3. Turnover, away - back an away side that lost the turnover count last time out.
4. Hunger, home   - back a hungry home side (negative season covers).
5. Hunger, away   - back a hungry away side (negative season covers).
"""

from __future__ import annotations

import pandas as pd

BET_THRESHOLD = 3  # |System #| at or above this triggers a bet.


def _sign(x: float) -> int:
    """-1 / 0 / +1, with ``-0.0`` treated as 0 (neutral)."""
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


# --- the five factors (each: +1 favours home, -1 favours away, 0 neither) -----

def power_factor(home_power: float, away_power: float, line: float) -> int:
    """Power / over-reaction factor.

    The power-implied handicap (positive = home underdog) is
    ``away_power - home_power``. When the actual handicap leaves the home side a
    bigger underdog, or a smaller favourite, than the ratings imply, the market
    has moved against them relative to a slow-moving rating, so back the home
    side (+1); the reverse backs the away side (-1).

    As in the NFL replication, the home-advantage term lives *inside* the rating
    fit (the ratings are neutral-venue) and is **not** re-added here. That is
    the construction that reproduced the published reports, and it leaves a
    systematic home-edge residual which makes this factor lean away. For the URC
    that residual is whatever ``season_report.HOME_ADVANTAGE`` is set to, which
    is still provisional - see ``calibrate.py``.
    """
    return _sign(line - (away_power - home_power))


def turnover_factor_home(home_lgt: float) -> int:
    """Back a home side that conceded more turnovers than its opponent last match."""
    return _sign(home_lgt)


def turnover_factor_away(away_lgt: float) -> int:
    """Back an away side that conceded the turnover count last match (-1 = away)."""
    return -_sign(away_lgt)


def hunger_factor_home(home_stdc: float) -> int:
    """Back a hungry home side (negative season-to-date covers)."""
    return -_sign(home_stdc)


def hunger_factor_away(away_stdc: float) -> int:
    """Back a hungry away side (stdc < 0 gives -1, i.e. favours away)."""
    return _sign(away_stdc)


def system_number(
    home_lgt: float, home_stdc: float, home_power: float,
    away_lgt: float, away_stdc: float, away_power: float,
    line: float,
) -> int:
    """Sum of the five factors: positive favours home, negative favours away."""
    return (
        power_factor(home_power, away_power, line)
        + turnover_factor_home(home_lgt)
        + turnover_factor_away(away_lgt)
        + hunger_factor_home(home_stdc)
        + hunger_factor_away(away_stdc)
    )


def pick(system_num: int) -> str | None:
    """'home', 'away', or None (no bet) given the System #."""
    if system_num >= BET_THRESHOLD:
        return "home"
    if system_num <= -BET_THRESHOLD:
        return "away"
    return None


# --- grading against the handicap --------------------------------------------

def _known(*values) -> bool:
    """True when every value is present (not NaN/NA)."""
    return not any(pd.isna(v) for v in values)


def cover(home_score, away_score, line: float) -> int:
    """+1 home covered, -1 away covered, 0 push or unknown.

    Returns 0 - moving nothing - when the match has not been played or carries
    no handicap. Rugby handicaps are often whole numbers, so exact pushes are
    meaningfully more common here than in the NFL data.
    """
    if not _known(home_score, away_score, line):
        return 0
    return _sign((home_score - away_score) + line)


def grade(system_num: int, home_score, away_score, line: float) -> str | None:
    """'W' / 'L' for the recommended bet, or None for no bet, a push, or a
    fixture not yet played (the pick stands, ungraded)."""
    side = pick(system_num)
    if side is None or not _known(home_score, away_score, line):
        return None
    c = cover(home_score, away_score, line)
    if c == 0:
        return None  # push: stake returned
    return "W" if (side == "home") == (c > 0) else "L"


# --- season-to-date covers ----------------------------------------------------

def season_to_date_covers(df: pd.DataFrame) -> pd.DataFrame:
    """Each match's home/away STDC: running net covers over earlier matches.

    Matches are taken in the order given (the report is chronological), and a
    side's value is its record *entering* the match, so the first appearance is
    0 by definition.
    """
    running: dict[str, int] = {}
    home_calc: list[float | None] = []
    away_calc: list[float | None] = []

    for row in df.itertuples():
        home, away = row.home, row.away
        home_known, away_known = isinstance(home, str), isinstance(away, str)
        home_calc.append(running.get(home) if home_known else None)
        away_calc.append(running.get(away) if away_known else None)

        c = cover(row.home_score, row.away_score, row.line)
        if home_known:
            running[home] = running.get(home, 0) + c
        if away_known:
            running[away] = running.get(away, 0) - c

    out = df.copy()
    out["home_stdc_calc"] = home_calc
    out["away_stdc_calc"] = away_calc
    return out


def apply_system(df: pd.DataFrame) -> pd.DataFrame:
    """Add recomputed System #, pick and result columns to a report frame."""
    out = df.copy()
    out["system_num_calc"] = [
        system_number(r.home_lgt, r.home_stdc, r.home_power,
                      r.away_lgt, r.away_stdc, r.away_power, r.line)
        for r in df.itertuples()
    ]
    out["pick_calc"] = out["system_num_calc"].map(pick)
    out["result_calc"] = [
        grade(r.system_num_calc, r.home_score, r.away_score, r.line)
        for r in out.itertuples()
    ]
    return out
