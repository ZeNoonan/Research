"""The Monopoly board as a Markov process, following Part II of Brown's
"Monopoly 101" (Wilmott, March 2003).

States. Brown's construction uses 120 states: squares 0-39 crossed with
{fresh turn, after one double, after two doubles}. Square 30 ("Go To Jail")
is never an end state, so its three copies are repurposed as jail turns:

    state 30  = In Jail, first turn
    state 70  = In Jail, second turn
    state 110 = In Jail, third turn
    square 10 = Just Visiting (all three blocks)

Players are assumed to stay in jail as long as possible (the late-game
optimum, and the regime that matters for valuation). Tournament rules:
doubles get you out and end your turn; on the third turn you pay $50 and
move regardless.

The same transition generator produces both the transition matrix (for the
stationary distribution = long-run square frequencies) and the expected
Bank cash flow per roll (Phi), so the two are guaranteed consistent.
"""

from dataclasses import dataclass
import numpy as np

from board import (
    CHANCE_CARDS, CHEST_CARDS, CHANCE_SQUARES, CHEST_SQUARES, NEAREST_RR,
    NEAREST_UTIL, REPAIRS, INCOME_TAX, LUXURY_TAX, INCOME_TAX_AMOUNT,
    LUXURY_TAX_AMOUNT, GO_SALARY, JAIL_FINE,
)

N_STATES = 120
JAIL_STATES = (30, 70, 110)

# All 36 ordered dice outcomes as (sum, is_double, probability).
DICE = [(a + b, a == b, 1.0 / 36.0) for a in range(1, 7) for b in range(1, 7)]


@dataclass
class Outcome:
    prob: float
    state: int          # next state, 0..119
    cash: float = 0.0   # fixed Bank->player cash (salary, taxes, card cash, fine)
    house_coef: float = 0.0   # Bank cash per house owned by the roller (repairs)
    hotel_coef: float = 0.0   # Bank cash per hotel owned by the roller
    rr_double: float = 0.0    # indicator: "advance to nearest RR, pay double" drawn
    util_card: float = 0.0    # indicator: "advance to nearest utility" drawn
    go_passes: float = 0.0


def _forward_passes(from_sq, to_sq):
    """Go collections when a card moves the token forward from from_sq to
    to_sq (wrapping). Landing on Go counts once."""
    return 1 if to_sq <= from_sq else 0


def _square_effects(sq, passes, base_prob, next_block, opts, depth=0):
    """Resolve landing on `sq` (already moved there having passed Go `passes`
    times). Returns a list of Outcome fragments with probability weights
    summing to base_prob. next_block is the block index (0/1/2) for the state
    the token settles in if the turn continues (doubles), already decided by
    the caller; jail always overrides to state 30."""
    outs = []
    cash = GO_SALARY * passes
    # Brown's Phi ($30.40 uniform, $23.62 exact) credits Go money only for
    # dice movement, not for passes/landings caused by card moves. Set this
    # option False to replicate the paper; True (default) for full accounting.
    credit_cards = opts.get("credit_card_go_passes", True)

    if sq == INCOME_TAX:
        cash -= INCOME_TAX_AMOUNT
        outs.append(Outcome(base_prob, next_block * 40 + sq, cash, go_passes=passes))
        return outs
    if sq == LUXURY_TAX:
        cash -= LUXURY_TAX_AMOUNT
        outs.append(Outcome(base_prob, next_block * 40 + sq, cash, go_passes=passes))
        return outs

    if sq in CHANCE_SQUARES or sq in CHEST_SQUARES:
        deck = CHANCE_CARDS if sq in CHANCE_SQUARES else CHEST_CARDS
        for label, move, card_cash, special in deck:
            p = base_prob / 16.0
            c = cash + card_cash
            hc = ho = rrd = utc = 0.0
            if special in REPAIRS:
                hc, ho = (-REPAIRS[special][0], -REPAIRS[special][1])
            if special == "rr_double":
                rrd = 1.0
            if special == "util_10x":
                utc = 1.0
            if move is None:
                outs.append(Outcome(p, next_block * 40 + sq, c, hc, ho, rrd, utc, passes))
                continue
            if move == "jail":
                outs.append(Outcome(p, 30, c, hc, ho, rrd, utc, passes))
                continue
            if move == "back3":
                tgt = sq - 3
                extra = 0
            else:
                tgt = NEAREST_RR[sq] if move == "nearest_rr" else (
                    NEAREST_UTIL[sq] if move == "nearest_util" else move)
                extra = _forward_passes(sq, tgt)
            total_passes = passes + extra
            c = c + (GO_SALARY * extra if credit_cards else 0)
            if opts.get("chain_card_effects", True) and depth == 0 and (
                    tgt in (INCOME_TAX, LUXURY_TAX) or tgt in CHEST_SQUARES or tgt in CHANCE_SQUARES):
                # e.g. "Go Back 3 Spaces" from 7 lands on Income Tax, from 36
                # lands on a Community Chest square and draws again.
                sub = _square_effects(tgt, 0, p, next_block, opts, depth=1)
                for o in sub:
                    outs.append(Outcome(o.prob, o.state, o.cash + c,
                                        o.house_coef + hc, o.hotel_coef + ho,
                                        o.rr_double + rrd, o.util_card + utc,
                                        o.go_passes + total_passes))
            else:
                outs.append(Outcome(p, tgt + next_block * 40, c, hc, ho, rrd, utc,
                                    total_passes))
        return outs

    outs.append(Outcome(base_prob, next_block * 40 + sq, cash, go_passes=passes))
    return outs


def outcomes(state, opts=None):
    """All (probability, next state, cash...) outcomes of one dice roll from
    `state`."""
    opts = opts or {}
    outs = []

    if state in JAIL_STATES:
        turn = JAIL_STATES.index(state)  # 0, 1, 2
        for total, is_dbl, p in DICE:
            if is_dbl:
                # Doubles: leave jail, move from square 10, turn ends.
                sq = 10 + total
                outs.extend(_square_effects(sq, 0, p, 0, opts))
            elif turn < 2:
                outs.append(Outcome(p, JAIL_STATES[turn + 1]))
            else:
                # Third turn: pay the $50 fine and move out.
                sq = 10 + total
                for o in _square_effects(sq, 0, p, 0, opts):
                    o.cash -= JAIL_FINE
                    outs.append(o)
        return outs

    block, sq0 = divmod(state, 40)
    for total, is_dbl, p in DICE:
        if is_dbl and block == 2:
            outs.append(Outcome(p, 30))  # third consecutive double: to jail
            continue
        raw = sq0 + total
        passes = 1 if raw >= 40 else 0
        sq = raw % 40
        if sq == 30:  # Go To Jail square (never passes Go on the way)
            outs.append(Outcome(p, 30))
            continue
        next_block = block + 1 if is_dbl else 0
        outs.extend(_square_effects(sq, passes, p, next_block, opts))
    return outs


def transition_matrix(opts=None):
    T = np.zeros((N_STATES, N_STATES))
    for s in range(N_STATES):
        for o in outcomes(s, opts):
            T[s, o.state] += o.prob
    assert np.allclose(T.sum(axis=1), 1.0)
    return T


def stationary(T, tol=1e-14):
    pi = np.full(N_STATES, 1.0 / N_STATES)
    for _ in range(200000):
        nxt = pi @ T
        if np.abs(nxt - pi).max() < tol:
            return nxt / nxt.sum()
        pi = nxt
    return pi / pi.sum()


def square_frequencies(pi):
    """Collapse 120 states to the 40-square table of Part II. Index 10 is
    'Just Visiting', index 30 is 'In Jail' (all three jail turns)."""
    freq = np.zeros(40)
    for s in range(N_STATES):
        block, sq = divmod(s, 40)
        freq[30 if s in JAIL_STATES else sq] += pi[s]
    return freq


class Chain:
    """Convenience wrapper: build once, query frequencies and Phi."""

    def __init__(self, opts=None):
        self.opts = opts or {}
        self.T = transition_matrix(self.opts)
        self.pi = stationary(self.T)
        self.freq = square_frequencies(self.pi)
        # Steady-state per-roll expectations.
        cash = houses = hotels = rrd = utc = passes = 0.0
        for s in range(N_STATES):
            for o in outcomes(s, self.opts):
                w = self.pi[s] * o.prob
                cash += w * o.cash
                houses += w * o.house_coef
                hotels += w * o.hotel_coef
                rrd += w * o.rr_double
                utc += w * o.util_card
                passes += w * o.go_passes
        self.cash_per_roll = cash          # Phi with an empty board
        self.house_coef = houses           # per house owned by the roller
        self.hotel_coef = hotels
        self.p_rr_double_card = rrd        # P(draw "nearest RR, double rent")
        self.p_util_card = utc
        self.go_passes_per_roll = passes

    def phi(self, houses_on_board=0, hotels_on_board=0, n_players=4):
        """Expected net Bank payment per roll. Repairs cards are paid by the
        roller on her own buildings; with buildings spread evenly the roller
        owns 1/n of the board's stock, hence the division by n (as in the
        paper)."""
        return (self.cash_per_roll
                + self.house_coef * houses_on_board / n_players
                + self.hotel_coef * hotels_on_board / n_players)
