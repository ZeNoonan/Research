"""Extensions beyond the papers.

1. house_roi: the exact, discrete return on each stage of development,
   exposing what Part I's linearized beta_i hides (the famous third house).
2. break_even_cash: how much table cash it takes before the green group's
   bigger hotel rents beat the light blue's faster percentage return -
   quantifying Part I's growth-vs-value discussion.
"""

from board import STREET_BY_SQUARE, GROUPS, GROUP_LABELS


def house_roi(freq):
    """For each color group and each development stage (adding one house to
    every street of the group at once), the increase in rent roll per dollar
    spent, per opponent roll. Stage 0 is going from doubled base rent to one
    house each; stage 4 is houses-to-hotels.

    This is the exact stepwise version of Part I's constant beta_i."""
    out = {}
    for g, members in GROUPS.items():
        cost = sum(STREET_BY_SQUARE[q].house_cost for q in members)
        stages = []
        for h in range(5):
            gain = 0.0
            for q in members:
                s = STREET_BY_SQUARE[q]
                prev = 2 * s.rents[0] if h == 0 else s.rents[h]
                gain += (s.rents[h + 1] - prev) * freq[q]
            stages.append({"stage": h + 1, "cost": cost,
                           "delta_rent_roll": gain, "roi": gain / cost})
        out[g] = {"label": GROUP_LABELS[g], "stages": stages}
    return out


def payback_rolls(freq):
    """Opponent rolls needed for each fully-hotelled group to pay back its
    total cost (group purchase + hotels) out of rent, ignoring discounting.
    A simple 'value vs growth' summary per group."""
    out = {}
    for g, members in GROUPS.items():
        price = sum(STREET_BY_SQUARE[q].price for q in members)
        hotels = sum(5 * STREET_BY_SQUARE[q].house_cost for q in members)
        rent_roll = sum(STREET_BY_SQUARE[q].rents[5] * freq[q] for q in members)
        out[g] = {"label": GROUP_LABELS[g], "total_cost": price + hotels,
                  "rent_roll": rent_roll,
                  "rolls_to_payback": (price + hotels) / rent_roll}
    return out
