"""Infer a handicap from 1X2 decimal odds.

Some sources publish only home/draw/away win odds, not a handicap. This turns
one into the other, which is possible because both describe the same
distribution of match margins from different angles: the win odds say how often
the home side finishes ahead, the handicap says by how much it is expected to.
Tie them together with a distribution of margins and either gives the other.

The model
---------
Take the margin ``M`` (home points minus away) as normal with standard
deviation ``sigma``. A handicap is the value that splits the outcome in two, so
the fair line is minus the expected margin, and the expected margin follows
from the win probability::

    P(M > 0) = p        ->      E[M] = sigma * Phi^-1(p)
                                line = -sigma * Phi^-1(p)

``p`` is taken as ``p_home + p_draw / 2``: a rugby draw is the mass sitting
exactly on zero, and a continuous approximation splits it either side.

Two things have to be right for this to work, and both are checkable.

**Removing the bookmaker's margin.** Quoted odds sum to more than certainty
(about 8.3% more in the URC sample). Dividing through by that sum - the obvious
fix - systematically overstates short prices, because the margin is not spread
evenly across outcomes. ``shin_probabilities`` uses Shin's method instead,
which models the book as protecting itself against better-informed traders and
so takes proportionally more out of the longshots. On the 50 URC matches this
was fitted against, Shin gave a 48% home cover rate against its own inferred
lines, against 54% for proportional de-vigging - 50% being what a fair line
must produce.

**The value of sigma.** Fitted by maximum likelihood on those 50 matches at
**16.0 points**, with the two independent estimates agreeing closely (the
regression slope gave 15.9, the residual spread 16.0), which is the check that
the normal model is self-consistent rather than merely fitted.

Where it fails
--------------
At very short prices the quote is too coarse to carry a spread. Decimal odds
move in steps of 0.01, and near 1.01 one step is worth about **1.8 points of
handicap**; by 1.15 it is under 0.7 and by 1.50 it is 0.15. So a line inferred
from a 1.01 shot is uncertain by a couple of points *before* any modelling
error. ``tick_sensitivity`` reports this per match so those rows can be flagged
rather than trusted silently.

This is also why the far tail cannot be rescued by a better model: the
information is not in the input.
"""

from __future__ import annotations

import math
from statistics import NormalDist

NORMAL = NormalDist()

# Standard deviation of URC match margins, in points. Fitted by maximum
# likelihood on 50 matches of 2025-26 (see module docstring). Re-fit with
# ``fit_sigma`` as more seasons arrive.
DEFAULT_SIGMA = 16.0

# Above this many points of line per 0.01 odds tick, the quote is too coarse to
# pin a handicap and the row is flagged rather than trusted.
COARSE_POINTS_PER_TICK = 1.0


def shin_probabilities(home: float, draw: float, away: float) -> tuple[float, float, float]:
    """De-vig 1X2 decimal odds into probabilities by Shin's method.

    Solves for the insider-trading proportion ``z`` that makes the implied
    probabilities sum to one. Unlike dividing through by the book sum, this
    takes proportionally more margin out of longshots, which is where the
    overround actually sits.
    """
    pi = [1.0 / home, 1.0 / draw, 1.0 / away]
    booksum = sum(pi)
    if booksum <= 1.0:  # no overround to remove (or a mispriced quote)
        return tuple(p / booksum for p in pi)

    def implied(z: float) -> list[float]:
        return [(math.sqrt(z * z + 4 * (1 - z) * p * p / booksum) - z) / (2 * (1 - z))
                for p in pi]

    lo, hi = 1e-12, 0.5
    for _ in range(200):  # bisection: total is monotone decreasing in z
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if sum(implied(mid)) > 1.0 else (lo, mid)
    p = implied((lo + hi) / 2)
    total = sum(p)
    return tuple(x / total for x in p)  # normalise away the bisection residual


def two_way_home(p_home: float, p_draw: float) -> float:
    """P(home finishes ahead), with the draw split either side of zero."""
    return min(max(p_home + p_draw / 2, 1e-6), 1 - 1e-6)


def line_from_odds(home: float, draw: float, away: float,
                   sigma: float = DEFAULT_SIGMA) -> float:
    """1X2 decimal odds -> the home handicap (negative = home favoured)."""
    p_home, p_draw, _ = shin_probabilities(home, draw, away)
    return -sigma * NORMAL.inv_cdf(two_way_home(p_home, p_draw))


def tick_sensitivity(home: float, draw: float, away: float,
                     sigma: float = DEFAULT_SIGMA) -> float:
    """Points of handicap moved by one 0.01 step of the shortest quoted price.

    The precision the quote itself allows, before any modelling error. Small
    for an even match, large for a heavy favourite - which is the honest reason
    a 1.01 shot cannot be converted to a reliable line.
    """
    shortest = min(home, away)
    z = -line_from_odds(home, draw, away, sigma) / sigma
    density = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
    return sigma * (0.01 / (shortest * shortest)) / max(density, 1e-12)


def is_coarse(home: float, draw: float, away: float,
              sigma: float = DEFAULT_SIGMA) -> bool:
    """True when the quote is too coarse to pin a handicap worth trusting."""
    return tick_sensitivity(home, draw, away, sigma) > COARSE_POINTS_PER_TICK


def fit_sigma(quotes: list[tuple[float, float, float]], margins: list[float],
              lo: float = 6.0, hi: float = 30.0, steps: int = 4801) -> dict:
    """Maximum-likelihood ``sigma`` from quoted odds and the margins that followed.

    Under ``M ~ Normal(sigma * z, sigma)`` the same parameter sets both the
    expected margin and its spread, so the fit is only credible when the two
    agree - which is why both are returned. A large gap means the normal model
    is the wrong shape, not that sigma needs nudging.
    """
    zs = [NORMAL.inv_cdf(two_way_home(*shin_probabilities(*q)[:2])) for q in quotes]
    best, best_ll = lo, -math.inf
    for i in range(steps):
        s = lo + (hi - lo) * i / (steps - 1)
        ll = sum(-math.log(s) - (m - s * z) ** 2 / (2 * s * s)
                 for z, m in zip(zs, margins))
        if ll > best_ll:
            best, best_ll = s, ll
    zz = sum(z * z for z in zs)
    slope = sum(z * m for z, m in zip(zs, margins)) / zz if zz else float("nan")
    resid = [m - best * z for z, m in zip(zs, margins)]
    mean_r = sum(resid) / len(resid)
    resid_sd = math.sqrt(sum((r - mean_r) ** 2 for r in resid) / (len(resid) - 1))
    return {"sigma": best, "slope_estimate": slope, "residual_sd": resid_sd,
            "n": len(margins), "log_likelihood": best_ll}
