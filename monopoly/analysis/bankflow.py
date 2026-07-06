"""Phi: the expected net payment from the Bank to the table per dice roll.

Part I computes Phi under the assumption that all 40 squares are equally
likely ($30.40). Part II recomputes it from the Markov chain ($23.62).
This module reproduces the uniform-board arithmetic and the popular
house-rule variant the paper warns about.
"""

from board import (
    GO_SALARY, INCOME_TAX_AMOUNT, LUXURY_TAX_AMOUNT, EXPECTED_ROLL,
    CHANCE_CARDS, CHEST_CARDS, card_bank_total,
)

N_CARDS = 32
CARD_SQUARES = 6  # three Chance + three Community Chest


def uniform_phi():
    """Part I: every square equally likely, Go passed every 40/7 rolls.
    Phi = 200*(7/40) - 200/40 - 75/40 + (6/40)*(485/32) = $30.40."""
    salary = GO_SALARY * EXPECTED_ROLL / 40.0
    taxes = (INCOME_TAX_AMOUNT + LUXURY_TAX_AMOUNT) / 40.0
    cards = (CARD_SQUARES / 40.0) * (card_bank_total() / N_CARDS)
    return salary - taxes + cards


def house_rule_phi():
    """Casual variant: $300 for passing Go; taxes and card payments to the
    Bank accumulate in a Free Parking pot ($500 seed) paid to whoever lands
    there. Taxes and card fines become player-to-player transfers (zero net),
    so the only Bank flows are the bigger salary, the $500 Free Parking seed,
    and the positive card payouts."""
    salary = 300.0 * EXPECTED_ROLL / 40.0
    free_parking_seed = 500.0 / 40.0
    positive_cards = sum(c[2] for c in CHANCE_CARDS if c[2] > 0) + \
        sum(c[2] for c in CHEST_CARDS if c[2] > 0)
    cards = (CARD_SQUARES / 40.0) * (positive_cards / N_CARDS)
    return salary + free_parking_seed + cards
