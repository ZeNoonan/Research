"""The NFL demonstration system: factor logic.

This module is a clean, self-contained implementation of Aaron Brown's
"additive binary factor" NFL betting system (see ``reference/`` for the source
write-up and the Wilmott article). It is the engine we use to *replicate* the
published reports.

Five binary factors each vote for the home team (+1), the away team (-1), or
neither (0). Their sum is the **System #**; we bet the home team when the sum
is +3 or more and the away team when it is -3 or less.

Sign conventions (matching the report columns)
-----------------------------------------------
* ``line``  – home spread: negative = home favoured, positive = home underdog
  (the points the home team is receiving).
* ``lgt``   – Last Game Turnover: net giveaways in a team's previous game
  (giveaways - takeaways). Positive = gave the ball away more than it took it.
* ``stdc``  – Season To Date Cover: net spread covers so far this season
  (covers - non-covers). Negative = a "hungry" team that has been failing to
  cover; positive = a "fat" team.
* ``power`` – a team's power rating (points). The home team is expected to be
  favoured by ``home_power - away_power + 3`` (a 3-point home-field edge).

The five factors
----------------
1. Power / over-reaction  – bet the team the line shortchanges versus the power
   ratings (favoured by fewer points, or an underdog by more, than implied).
2. Turnover, home team     – bet a home team that gave the ball away last game.
3. Turnover, away team     – bet an away team that gave the ball away last game.
4. Hunger, home team       – bet a hungry home team (negative season covers).
5. Hunger, away team       – bet a hungry away team (negative season covers).
"""

from __future__ import annotations

import pandas as pd

BET_THRESHOLD = 3  # |System #| at or above this triggers a bet.


def _sign(x: float) -> int:
    """-1 / 0 / +1. Note ``-0.0`` is treated as 0 (neutral), as in the report."""
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


# --- the five factors (each returns +1 favours home, -1 favours away, 0 none) -

def power_factor(home_power: float, away_power: float, line: float) -> int:
    """Power / over-reaction factor.

    The power-implied line (report terms, positive = home underdog) is simply
    ``away_power - home_power``. If the actual line leaves the home team a bigger
    underdog / smaller favourite than implied, the line has moved against the
    home team versus the ratings, so we back the home team (+1); if it leaves
    them a bigger favourite, we back the away team (-1).

    Note: the write-up describes a 3-point home-field advantage *inside the
    rating fit* (the ratings are neutral-field), but at pick time the published
    reports compare the line to the raw power difference with no home-field
    term re-added. Refitting ratings from the reports' own lines confirms this:
    a weighted fit with a 3-point HFA reproduces the published implied lines at
    0.999 correlation (weeks 5+). The raw comparison leaves a ~2-point average
    home-edge residual, so the published power factor genuinely leans away
    (2016: 195 away votes vs 72 home). Using ``away_power - home_power``
    reproduces 532/534 of the published System # values; the two misses are
    exact ties created by the power column being rounded to one decimal in the
    PDF.
    """
    implied_line = away_power - home_power
    return _sign(line - implied_line)


def turnover_factor_home(home_lgt: float) -> int:
    """Back a home team that gave the ball away more than it took it last game."""
    return _sign(home_lgt)


def turnover_factor_away(away_lgt: float) -> int:
    """Back an away team that gave the ball away last game (so -1 favours away)."""
    return -_sign(away_lgt)


def hunger_factor_home(home_stdc: float) -> int:
    """Back a hungry home team (negative season-to-date covers)."""
    return -_sign(home_stdc)


def hunger_factor_away(away_stdc: float) -> int:
    """Back a hungry away team (so a hungry away team, stdc < 0, gives -1)."""
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
    """'home', 'away', or None given the System #."""
    if system_num >= BET_THRESHOLD:
        return "home"
    if system_num <= -BET_THRESHOLD:
        return "away"
    return None


# --- grading against the spread ----------------------------------------------

def cover(home_score: int, away_score: int, line: float) -> int:
    """+1 home covered, -1 away covered, 0 push (margin lands exactly on line)."""
    return _sign((home_score - away_score) + line)


def grade(system_num: int, home_score: int, away_score: int, line: float) -> str | None:
    """'W' / 'L' for the recommended bet, or None for no bet or a push."""
    side = pick(system_num)
    if side is None:
        return None
    c = cover(home_score, away_score, line)
    if c == 0:
        return None  # push: stake returned, no win or loss
    bet_covered = (side == "home" and c > 0) or (side == "away" and c < 0)
    return "W" if bet_covered else "L"


# --- reconstructing Season To Date Cover from scores + lines -----------------

def season_to_date_covers(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute each game's home/away STDC from prior results in the file.

    A team's STDC entering a game is its running net covers (covers minus
    non-covers) over all earlier games in the same file. Games are taken in the
    order they appear (the reports are chronological). Returns a frame with
    ``home_stdc_calc`` and ``away_stdc_calc`` columns aligned to ``df``.

    Rows whose home or away name was lost in the PDF (the Seahawks/Steelers
    footer quirk) cannot be tracked by name; their calculated value, and any
    later game that team plays, is left as NA.
    """
    running: dict[str, int] = {}
    home_calc: list[float | None] = []
    away_calc: list[float | None] = []

    for row in df.itertuples():
        home, away = row.home, row.away
        home_known = isinstance(home, str)
        away_known = isinstance(away, str)

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
        system_number(
            r.home_lgt, r.home_stdc, r.home_power,
            r.away_lgt, r.away_stdc, r.away_power, r.line,
        )
        for r in df.itertuples()
    ]
    out["pick_calc"] = out["system_num_calc"].map(pick)
    out["result_calc"] = [
        grade(r.system_num_calc, r.home_score, r.away_score, r.line)
        for r in out.itertuples()
    ]
    return out
