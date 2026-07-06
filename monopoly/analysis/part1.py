"""Part I of "Monopoly 101": rent rolls, the safe zone, the lurking
exponential, and first-cut property values on a uniformly-visited board.
"""

import numpy as np

from board import (
    STREETS, STREET_BY_SQUARE, GROUPS, RAILROADS, RAILROAD_RENT, UTILITIES,
    UTILITY_MULT, EXPECTED_ROLL, group_hotel_rent, group_base_rent,
    group_hotel_cost,
)
from bankflow import uniform_phi


# ---------------------------------------------------------------------------
# Aggregate rents
# ---------------------------------------------------------------------------

def total_rent_undeveloped():
    """All 28 properties held singly (no color groups completed): street base
    rents, $25 per railroad, 4x the average dice roll per utility.
    Paper: $547."""
    streets = sum(s.rents[0] for s in STREETS)
    rails = len(RAILROADS) * RAILROAD_RENT[1]
    utils = len(UTILITIES) * UTILITY_MULT[1] * EXPECTED_ROLL
    return streets + rails + utils


def total_rent_fully_developed():
    """Every color group a hotel-built monopoly, one owner for all four
    railroads, one for both utilities. Paper: $22,790."""
    streets = sum(group_hotel_rent(g) for g in GROUPS)
    rails = len(RAILROADS) * RAILROAD_RENT[4]
    utils = len(UTILITIES) * UTILITY_MULT[2] * EXPECTED_ROLL
    return streets + rails + utils


def safe_zone(n_players=4):
    """A player only bleeds if her rent roll is more than Phi/n below the
    table average: per round of n rolls, player i nets
    n*(R_i - Rbar) + Phi. Paper: $7.60 for four players."""
    return uniform_phi() / n_players


# ---------------------------------------------------------------------------
# Who is forced to trade? Monte Carlo of the no-trading endgame.
# ---------------------------------------------------------------------------

def rent_roll_of(owned, uniform=True, freq=None):
    """Rent roll (expected rent collected per opponent roll) of a set of
    owned squares, with complete color groups developed to hotels and
    incomplete ones at single base rent."""
    w = (lambda q: 1.0 / 40.0) if uniform else (lambda q: freq[q])
    total = 0.0
    owned = set(owned)
    for g, members in GROUPS.items():
        if set(members) <= owned:
            total += sum(STREET_BY_SQUARE[q].rents[5] * w(q) for q in members)
        else:
            total += sum(STREET_BY_SQUARE[q].rents[0] * w(q)
                         for q in members if q in owned)
    k = len(owned & set(RAILROADS))
    if k:
        total += sum(RAILROAD_RENT[k] * w(q) for q in RAILROADS if q in owned)
    u = len(owned & set(UTILITIES))
    if u:
        total += sum(UTILITY_MULT[u] * EXPECTED_ROLL * w(q)
                     for q in UTILITIES if q in owned)
    return total


PROPERTY_SQUARES = sorted(
    [s.square for s in STREETS] + list(RAILROADS) + list(UTILITIES))


def rent_roll_distribution(n_players=4, n_samples=200_000, seed=7):
    """Assign each of the 28 properties to a uniformly random player (the
    'everyone buys whatever they land on' endgame), develop all complete
    monopolies to hotels, and study rent roll minus the table average.
    Paper: mean 0, sd $28.63, highly right-skewed, and P(shortfall > $7.60)
    is about 40%."""
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_samples)
    threshold = -safe_zone(n_players)
    below = 0
    for i in range(n_samples):
        owners = rng.integers(0, n_players, size=len(PROPERTY_SQUARES))
        rolls = [rent_roll_of([q for q, o in zip(PROPERTY_SQUARES, owners)
                               if o == p]) for p in range(n_players)]
        avg = sum(rolls) / n_players
        d = rolls[0] - avg          # player 0 is exchangeable with the rest
        diffs[i] = d
        below += sum(1 for r in rolls if r - avg < threshold) / n_players
    return {
        "mean": float(diffs.mean()),
        "sd": float(diffs.std()),
        "skew": float(((diffs - diffs.mean()) ** 3).mean() / diffs.std() ** 3),
        "p_below_safe_zone": below / n_samples,
        "sample": diffs[:5000].tolist(),
    }


# ---------------------------------------------------------------------------
# First-cut betas: linearized return on housing investment
# ---------------------------------------------------------------------------

def naive_betas():
    """beta_i = (hotel rent - doubled base rent) / cost of hotels / 40:
    the linearized rent-roll increase per dollar of development, per roll.
    Paper: 3.2% for the green group, 5.5% for the light blue, ~4% average."""
    out = {}
    for g in GROUPS:
        gain = group_hotel_rent(g) - group_base_rent(g, doubled=True)
        out[g] = gain / group_hotel_cost(g) / 40.0
    return out


# ---------------------------------------------------------------------------
# How long until all properties are bought? (coupon collector)
# ---------------------------------------------------------------------------

def expected_rolls_to_buy_all(n_property_squares=28, n_squares=40):
    """With uniform landing, expected rolls until every property square has
    been hit at least once: 40 * H_28 ~ 157."""
    return n_squares * sum(1.0 / k for k in range(1, n_property_squares + 1))


def present_value_example(fv=10_000.0, rate=0.04, rolls=None):
    """Brown: a monopoly worth $10,000 when development starts is worth ~$18
    at the first roll, discounted at 4% per roll."""
    rolls = rolls if rolls is not None else expected_rolls_to_buy_all()
    return fv / (1 + rate) ** rolls


# ---------------------------------------------------------------------------
# The lurking exponential: wealth dynamics with reinvestment
# ---------------------------------------------------------------------------

def wealth_paths(r0, betas, phi, t_max=120.0, dt=0.01, clamp=True):
    """Integrate the Part I ODE system for n players. Time is measured in
    rounds (each player rolls once per round). Player i's rent roll is
    R_i = r0_i + beta_i * W_i; per round she nets n*R_i - sum(R) + phi.

    With clamp=True (realistic) a player cannot invest negative wealth, so
    her rent roll never falls below r0_i; clamp=False is the pure linear
    system Brown solves in closed form."""
    n = len(r0)
    W = np.zeros(n)
    ts, paths = [], []
    steps = int(t_max / dt)
    for k in range(steps + 1):
        if k % max(1, steps // 400) == 0:
            ts.append(k * dt)
            paths.append(W.copy())
        Weff = np.maximum(W, 0.0) if clamp else W
        R = np.array(r0) + np.array(betas) * Weff
        dW = n * R - R.sum() + phi
        W = W + dW * dt
    return np.array(ts), np.array(paths)


def survival_measure(r, beta_i, beta_bar, phi, n):
    """The quantity that decides a player's fate (and prices properties):
    annuity rent plus the player's share of the Bank's money, valued through
    the option to build. C > 0 in the exponential solution iff this exceeds
    the opponents' analogous quantity."""
    return r + beta_i * phi / ((n - 1) * beta_i + beta_bar)


def consistency_beta(betas, tol=1e-12):
    """The game-wide rate beta_bar solving sum_i beta_i/((n-1)beta_i+beta)=1,
    so that the players' shares of Phi add up to Phi. For n=2 this is exactly
    the geometric mean of the beta_i (Brown's characterization); for n>2 it
    is close to it."""
    n = len(betas)
    lo, hi = 1e-9, max(betas) * n
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        s = sum(b / ((n - 1) * b + mid) for b in betas)
        if s > 1.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
