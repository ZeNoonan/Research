"""Rouge et Noir -- the security from Aaron Brown's Wilmott column (Sept 2013).

The game: roll a fair six-sided die, call the result D. Put D black chips
and 6 - D red chips into a hat (six chips total). Chips are then drawn one
at a time WITHOUT replacement over six rounds. Each round, teams bid on a
security that pays $100 if the next chip drawn is black, $0 if it is red.

This script computes the expected value of the security in every reachable
state (B blacks and R reds drawn so far) two independent ways:

  1. Bayes / hypergeometric closed form (the way the article describes), and
  2. brute-force enumeration of every die roll and every chip ordering,

verifies they agree, checks the result against the article's published
Table 1, and demonstrates two things the closed form hides:

  * for B >= 1 the value is EXACTLY Laplace's rule of succession,
    100 * (B + 1) / (B + R + 2), and
  * the B = 0 column is the lone exception (the die guarantees at least
    one black chip), which is why drawing reds eventually RAISES the value.

It also works the "simple version" used as the warm-up on the web page:
flip a coin, put 1 or 2 black chips into a hat of three.

Everything is exact rational arithmetic (fractions.Fraction); no
dependencies outside the standard library.
"""

from fractions import Fraction
from itertools import permutations
from math import comb


# ----------------------------------------------------------------------
# 1. Bayes / hypergeometric closed form
# ----------------------------------------------------------------------

def value_bayes(B, R, n_chips=6, d_values=None, prior=None):
    """Expected payoff of the security after observing B blacks and R reds.

    d_values : possible chip counts D (default: die faces 1..6)
    prior    : prior probability of each D (default: uniform)

    Returns a Fraction in [0, 1]; multiply by 100 for dollars.
    Also returns the per-D breakdown used to build the page's
    "show your work" tables:
        [(D, likelihood, posterior, p_next_black, contribution), ...]
    """
    if d_values is None:
        d_values = range(1, n_chips + 1)
    d_values = list(d_values)
    if prior is None:
        prior = {d: Fraction(1, len(d_values)) for d in d_values}

    remaining = n_chips - B - R
    if remaining <= 0:
        raise ValueError("no chips left to draw")

    rows, norm = [], Fraction(0)
    for d in d_values:
        if d < B or (n_chips - d) < R:
            continue  # this die roll cannot have produced the observation
        # P(exactly B blacks and R reds in the first B+R draws | D = d)
        like = Fraction(comb(d, B) * comb(n_chips - d, R),
                        comb(n_chips, B + R))
        weight = prior[d] * like
        norm += weight
        rows.append([d, like, weight])

    value = Fraction(0)
    breakdown = []
    for d, like, weight in rows:
        post = weight / norm
        p_black = Fraction(d - B, remaining)
        value += post * p_black
        breakdown.append((d, like, post, p_black, post * p_black))
    return value, breakdown


# ----------------------------------------------------------------------
# 2. Brute force: enumerate every die roll and every chip ordering
# ----------------------------------------------------------------------

def value_brute_exact(B, R, n_chips=6, d_values=None):
    """Same expectation by raw enumeration -- no Bayes, no cleverness.

    For every equally likely die roll, walk ALL n! orderings of the chips
    (blacks and reds treated as distinguishable, so every ordering is
    equally likely). Keep the orderings whose first B+R draws contain
    exactly B blacks; among those, the fraction where draw B+R+1 is black
    is the answer:  P(next black | obs) = P(obs and next black) / P(obs).
    """
    if d_values is None:
        d_values = range(1, n_chips + 1)
    num = den = Fraction(0)
    for d in d_values:
        chips = "B" * d + "R" * (n_chips - d)
        n_obs = n_black_next = total_perms = 0
        for seq in permutations(chips):
            total_perms += 1
            if seq[:B + R].count("B") == B:
                n_obs += 1
                if seq[B + R] == "B":
                    n_black_next += 1
        num += Fraction(n_black_next, total_perms)
        den += Fraction(n_obs, total_perms)
    return num / den


# ----------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------

# Table 1 of the article, row k = after k draws, column = number of blacks B
PUBLISHED = [
    ["58.33"],
    ["46.67", "66.67"],
    ["43.75", "50.00", "75.00"],
    ["46.67", "40.00", "60.00", "80.00"],
    ["58.33", "33.33", "50.00", "66.67", "83.33"],
    ["100.00", "28.57", "42.86", "57.14", "71.43", "85.71"],
]

GARP_SEQUENCE = "RBRRRR"  # the draws at the 2013 GARP convention


def dollars(frac):
    return f"${float(100 * frac):.2f}"


def full_game_report():
    print("=" * 72)
    print("FULL GAME: die roll D in 1..6, D black + (6-D) red chips")
    print("=" * 72)
    all_match = True
    for k in range(6):  # draws so far
        line = []
        for b in range(k + 1):
            r = k - b
            v, _ = value_bayes(b, r)
            v2 = value_brute_exact(b, r)
            assert v == v2, f"Bayes vs brute force disagree at B={b} R={r}"
            cell = f"{float(100 * v):.2f}"
            ok = cell == PUBLISHED[k][b]
            all_match &= ok
            line.append(f"{cell}{'' if ok else '  <-- MISMATCH vs article'}")
        print(f"after {k} draws:  " + "   ".join(line))
    print(f"\nBayes == brute-force enumeration for all 21 states: OK")
    print(f"All 21 values match the article's Table 1: "
          f"{'OK' if all_match else 'NO'}")

    print("\nRule of succession check, 100*(B+1)/(B+R+2), for B >= 1:")
    for k in range(6):
        for b in range(1, k + 1):
            r = k - b
            v, _ = value_bayes(b, r)
            laplace = Fraction(b + 1, b + r + 2)
            assert v == laplace, (b, r)
    print("  exact match in every state with at least one black drawn: OK")

    print("\nCounterfactual: a die with faces 0..6 (so an all-red hat is "
          "possible)\nwould satisfy the rule of succession in EVERY state:")
    for k in range(6):
        for b in range(k + 1):
            r = k - b
            v, _ = value_bayes(b, r, d_values=range(0, 7))
            assert v == Fraction(b + 1, b + r + 2), (b, r)
    print("  verified exactly for all 21 states: OK "
          "(the real die's missing zero is the whole B = 0 anomaly)")

    print("\nThe B = 0 column (no blacks yet) -- the exception:")
    for r in range(6):
        v, _ = value_bayes(0, r)
        print(f"  after {r} reds, 0 blacks: {dollars(v)}"
              f"   (rule of succession would say "
              f"{dollars(Fraction(1, r + 2))})")

    print("\nExpected value along the actual GARP path "
          f"({'-'.join(GARP_SEQUENCE)}):")
    b = r = 0
    for i, c in enumerate(GARP_SEQUENCE):
        v, _ = value_bayes(b, r)
        print(f"  round {i + 1}: seen {b} black, {r} red -> value "
              f"{dollars(v)}; chip drawn: {'black' if c == 'B' else 'red'}")
        if c == "B":
            b += 1
        else:
            r += 1


def simple_game_report():
    print()
    print("=" * 72)
    print("SIMPLE GAME (warm-up): coin flip, D in {1, 2}, 3 chips in the hat")
    print("=" * 72)
    d_values = [1, 2]
    for k in range(3):
        line = []
        for b in range(k + 1):
            r = k - b
            try:
                v, _ = value_bayes(b, r, n_chips=3, d_values=d_values)
            except ZeroDivisionError:
                continue
            v2 = value_brute_exact(b, r, n_chips=3, d_values=d_values)
            assert v == v2
            line.append(f"B={b},R={r}: {dollars(v)}")
        print(f"after {k} draws:   " + "    ".join(line))
    print("\nNote the flip: drawing BLACK first sends the value DOWN "
          "($50.00 -> $33.33)\nand drawing RED sends it UP ($50.00 -> "
          "$66.67) -- depletion beats learning\nwhen the die (coin) can't "
          "spread the chip count far.")


def show_one_worked_state(B=1, R=2):
    print()
    print("=" * 72)
    print(f"WORKED EXAMPLE: B = {B} black, R = {R} red drawn "
          f"(round {B + R + 1} of the full game)")
    print("=" * 72)
    v, breakdown = value_bayes(B, R)
    print(f"{'D':>3} {'P(obs|D)':>12} {'posterior':>12} "
          f"{'P(black|D)':>12} {'contribution':>13}")
    for d, like, post, p_black, contrib in breakdown:
        print(f"{d:>3} {str(like):>12} {str(post):>12} "
              f"{str(p_black):>12} {str(contrib):>13}")
    print(f"expected payoff = 100 x {v} = {dollars(v)}")


if __name__ == "__main__":
    full_game_report()
    simple_game_report()
    show_one_worked_state()
