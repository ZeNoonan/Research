"""The Monopoly property pricing formula (Part II):

    V_i = (1/beta) * [ R_i + beta_i * Phi / ((n-1) * beta_i + beta) ]

where R_i is expected rent per opponent roll, beta_i the return on housing
investment for the property, beta the game-wide interest rate (geometric mean
of the players' betas), n the number of players and Phi the Bank's net
payment per roll. The first term is a rent annuity (Gordon-model style); the
second capitalizes the option to build, funded by the player's share of the
money the Bank injects.
"""

from board import (
    GROUPS, GROUP_LABELS, STREET_BY_SQUARE, RAILROADS, RAILROAD_RENT,
    UTILITIES, UTILITY_MULT, EXPECTED_ROLL, group_base_rent, group_hotel_rent,
)

# Brown's fitted betas (Part II table) - estimated by iterated simulation of
# endgames, NOT the naive linearization of Part I. Light blue and orange are
# the "growth stocks"; green is nearly a pure bond.
FITTED_BETAS = {
    "brown": 0.0333, "lightblue": 0.0765, "pink": 0.0436, "orange": 0.1189,
    "red": 0.0289, "yellow": 0.0341, "green": 0.0077, "darkblue": 0.0644,
    "railroads": 0.0, "utilities": 0.0,
}

# The scenarios of the paper's valuation table.
START_INTEREST, END_INTEREST = 0.016, 0.06
PAPER_PHI_START = 23.62      # empty board
PAPER_PHI_END = 13.17        # 2 players, 32 houses + 12 hotels


def value(rent_roll, beta_i, beta, phi, n_players):
    return (rent_roll + beta_i * phi / ((n_players - 1) * beta_i + beta)) / beta


def group_rent_rolls(freq, p_rr_double_card=0.0):
    """R_i per group from the long-run square frequencies.

    'start': whole group owned, undeveloped (doubled street rent).
    'end':   hotels everywhere.
    Railroads include the extra payment from the two 'advance to nearest
    railroad, pay double rent' Chance cards; the landing itself is already in
    the frequencies, the card adds one extra rent on top.
    """
    start, end = {}, {}
    for g, members in GROUPS.items():
        start[g] = sum(2 * STREET_BY_SQUARE[q].rents[0] * freq[q] for q in members)
        end[g] = sum(STREET_BY_SQUARE[q].rents[5] * freq[q] for q in members)
    rr = RAILROAD_RENT[4] * sum(freq[q] for q in RAILROADS) \
        + RAILROAD_RENT[4] * p_rr_double_card
    ut = UTILITY_MULT[2] * EXPECTED_ROLL * sum(freq[q] for q in UTILITIES)
    start["railroads"] = end["railroads"] = rr
    start["utilities"] = end["utilities"] = ut
    return start, end


def part2_table(freq, p_rr_double_card, betas=None, n_players=4,
                phi_start=PAPER_PHI_START, phi_end=PAPER_PHI_END):
    """Reproduce the paper's 'Monopoly valuations in some specific
    situations' table. Start: 1.6% interest, empty board, four players.
    End: 6% interest, fully developed board - the option to build is
    exhausted, so the end value is the plain rent annuity R_i / beta
    (this is what reproduces the published column)."""
    betas = betas or FITTED_BETAS
    start_r, end_r = group_rent_rolls(freq, p_rr_double_card)
    rows = []
    for g in list(GROUPS) + ["railroads", "utilities"]:
        rows.append({
            "group": g,
            "label": GROUP_LABELS[g],
            "beta_i": betas[g],
            "rent_start": start_r[g],
            "value_start": value(start_r[g], betas[g], START_INTEREST,
                                 phi_start, n_players),
            "rent_end": end_r[g],
            "value_end": end_r[g] / END_INTEREST,
        })
    return rows


def part1_table(naive_betas_by_group, phi, beta=0.04, n_players=4):
    """Reconstruct Part I's first-cut value table: uniform frequencies,
    beta = 4%, Phi = $30.40. Non-developable property is worth
    rent/40/0.04 = 0.625 * rent; color groups add the option term."""
    rows = []
    for g in GROUPS:
        r = group_base_rent(g, doubled=True) / 40.0
        b = naive_betas_by_group[g]
        rows.append({
            "group": g, "label": GROUP_LABELS[g], "beta_i": b, "rent": r,
            "value": value(r, b, beta, phi, n_players),
        })
    rr = RAILROAD_RENT[4] * len(RAILROADS) / 40.0
    ut = UTILITY_MULT[2] * EXPECTED_ROLL * len(UTILITIES) / 40.0
    rows.append({"group": "railroads", "label": GROUP_LABELS["railroads"],
                 "beta_i": 0.0, "rent": rr, "value": rr / beta})
    rows.append({"group": "utilities", "label": GROUP_LABELS["utilities"],
                 "beta_i": 0.0, "rent": ut, "value": ut / beta})
    return rows


# Published table values for validation (Wilmott March 2003, p.14).
PAPER_TABLE = {
    "brown":     {"rent_start": 0.24, "value_start": 435, "rent_end": 14.20, "value_end": 235},
    "lightblue": {"rent_start": 0.87, "value_start": 510, "rent_end": 36.81, "value_end": 610},
    "pink":      {"rent_start": 1.53, "value_start": 529, "rent_end": 57.34, "value_end": 950},
    "orange":    {"rent_start": 2.44, "value_start": 618, "rent_end": 80.35, "value_end": 1332},
    "red":       {"rent_start": 3.06, "value_start": 601, "rent_end": 87.36, "value_end": 1448},
    "yellow":    {"rent_start": 3.40, "value_start": 632, "rent_end": 87.45, "value_end": 1450},
    "green":     {"rent_start": 3.92, "value_start": 530, "rent_end": 96.78, "value_end": 1604},
    "darkblue":  {"rent_start": 3.93, "value_start": 694, "rent_end": 80.65, "value_end": 1337},
    "railroads": {"rent_start": 23.04, "value_start": 1429, "rent_end": 23.04, "value_end": 382},
    "utilities": {"rent_start": 3.69, "value_start": 229, "rent_end": 3.69, "value_end": 61},
}

PAPER_MAX_VALUES = {
    "brown": 1002, "lightblue": 1263, "pink": 1164, "orange": 1592,
    "red": 1575, "yellow": 1619, "green": 1662, "darkblue": 2606,
    "railroads": 1429, "utilities": 229,
}
