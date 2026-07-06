"""Board data for classic US Monopoly (1990s rules, as used in Brown's
"Monopoly 101", Wilmott 2003).

Squares are numbered 0 (Go) to 39 (Boardwalk). Rent schedules for streets are
[base, 1 house, 2 houses, 3 houses, 4 houses, hotel]. A street owned as part
of a complete color group collects double the base rent while unimproved.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Street:
    square: int
    name: str
    group: str
    price: int
    rents: tuple  # (base, h1, h2, h3, h4, hotel)
    house_cost: int


STREETS = [
    Street(1, "Mediterranean Avenue", "brown", 60, (2, 10, 30, 90, 160, 250), 50),
    Street(3, "Baltic Avenue", "brown", 60, (4, 20, 60, 180, 320, 450), 50),
    Street(6, "Oriental Avenue", "lightblue", 100, (6, 30, 90, 270, 400, 550), 50),
    Street(8, "Vermont Avenue", "lightblue", 100, (6, 30, 90, 270, 400, 550), 50),
    Street(9, "Connecticut Avenue", "lightblue", 120, (8, 40, 100, 300, 450, 600), 50),
    Street(11, "St. Charles Place", "pink", 140, (10, 50, 150, 450, 625, 750), 100),
    Street(13, "States Avenue", "pink", 140, (10, 50, 150, 450, 625, 750), 100),
    Street(14, "Virginia Avenue", "pink", 160, (12, 60, 180, 500, 700, 900), 100),
    Street(16, "St. James Place", "orange", 180, (14, 70, 200, 550, 750, 950), 100),
    Street(18, "Tennessee Avenue", "orange", 180, (14, 70, 200, 550, 750, 950), 100),
    Street(19, "New York Avenue", "orange", 200, (16, 80, 220, 600, 800, 1000), 100),
    Street(21, "Kentucky Avenue", "red", 220, (18, 90, 250, 700, 875, 1050), 150),
    Street(23, "Indiana Avenue", "red", 220, (18, 90, 250, 700, 875, 1050), 150),
    Street(24, "Illinois Avenue", "red", 240, (20, 100, 300, 750, 925, 1100), 150),
    Street(26, "Atlantic Avenue", "yellow", 260, (22, 110, 330, 800, 975, 1150), 150),
    Street(27, "Ventnor Avenue", "yellow", 260, (22, 110, 330, 800, 975, 1150), 150),
    Street(29, "Marvin Gardens", "yellow", 280, (24, 120, 360, 850, 1025, 1200), 150),
    Street(31, "Pacific Avenue", "green", 300, (26, 130, 390, 900, 1100, 1275), 200),
    Street(32, "North Carolina Avenue", "green", 300, (26, 130, 390, 900, 1100, 1275), 200),
    Street(34, "Pennsylvania Avenue", "green", 320, (28, 150, 450, 1000, 1200, 1400), 200),
    Street(37, "Park Place", "darkblue", 350, (35, 175, 500, 1100, 1300, 1500), 200),
    Street(39, "Boardwalk", "darkblue", 400, (50, 200, 600, 1400, 1700, 2000), 200),
]

STREET_BY_SQUARE = {s.square: s for s in STREETS}

GROUPS = {
    "brown": (1, 3),
    "lightblue": (6, 8, 9),
    "pink": (11, 13, 14),
    "orange": (16, 18, 19),
    "red": (21, 23, 24),
    "yellow": (26, 27, 29),
    "green": (31, 32, 34),
    "darkblue": (37, 39),
}

GROUP_LABELS = {
    "brown": "Mediterranean + Baltic",
    "lightblue": "Oriental + Vermont + Connecticut",
    "pink": "St. Charles + States + Virginia",
    "orange": "St. James + Tennessee + New York",
    "red": "Kentucky + Indiana + Illinois",
    "yellow": "Atlantic + Ventnor + Marvin Gardens",
    "green": "Pacific + North Carolina + Pennsylvania",
    "darkblue": "Park Place + Boardwalk",
    "railroads": "All four Railroads",
    "utilities": "Both Utilities",
}

RAILROADS = (5, 15, 25, 35)
RAILROAD_PRICE = 200
# Rent per railroad landing given the owner holds k railroads.
RAILROAD_RENT = {1: 25, 2: 50, 3: 100, 4: 200}

UTILITIES = (12, 28)
UTILITY_PRICE = 150
# Utility rent is a dice multiple: 4x if one owned, 10x if both. E[2d6] = 7.
UTILITY_MULT = {1: 4, 2: 10}
EXPECTED_ROLL = 7.0

GO, JAIL_VISITING, FREE_PARKING, GO_TO_JAIL = 0, 10, 20, 30
INCOME_TAX, LUXURY_TAX = 4, 38
CHANCE_SQUARES = (7, 22, 36)
CHEST_SQUARES = (2, 17, 33)

GO_SALARY = 200
INCOME_TAX_AMOUNT = 200  # flat option; Brown ignores the 10%-of-worth election
LUXURY_TAX_AMOUNT = 75   # 1990s edition value used in the papers
JAIL_FINE = 50

SQUARE_NAMES = {
    0: "Go", 2: "Community Chest", 4: "Income Tax", 5: "Reading Railroad",
    7: "Chance", 10: "Visiting Jail", 12: "Electric Company",
    15: "Pennsylvania Railroad", 17: "Community Chest", 20: "Free Parking",
    22: "Chance", 25: "B&O Railroad", 28: "Water Works", 30: "In Jail",
    33: "Community Chest", 35: "Short Line Railroad", 36: "Chance",
    38: "Luxury Tax",
}
SQUARE_NAMES.update({s.square: s.name for s in STREETS})

# ---------------------------------------------------------------------------
# Cards. Each card is (label, move, bank_cash, special)
#   move: None, an absolute square, "back3", "jail", "nearest_rr", "nearest_util"
#   bank_cash: net payment from the Bank to the player (negative = pay Bank)
#   special: "repairs_chance", "repairs_chest", "rr_double", "util_10x",
#            "gojf", "per_player_collect", "per_player_pay", or None
# Player-to-player transfers and rent effects carry zero bank_cash: they do not
# inject or destroy money at the table level, which is what Phi measures.
# ---------------------------------------------------------------------------

CHANCE_CARDS = [
    ("Advance to Go", 0, 0, None),
    ("Advance to Illinois Avenue", 24, 0, None),
    ("Advance to St. Charles Place", 11, 0, None),
    ("Advance to nearest Utility", "nearest_util", 0, "util_10x"),
    ("Advance to nearest Railroad (double rent)", "nearest_rr", 0, "rr_double"),
    ("Advance to nearest Railroad (double rent) #2", "nearest_rr", 0, "rr_double"),
    ("Bank pays you dividend of $50", None, 50, None),
    ("Get Out of Jail Free", None, 0, "gojf"),
    ("Go Back 3 Spaces", "back3", 0, None),
    ("Go to Jail", "jail", 0, None),
    ("General repairs: $25/house, $100/hotel", None, 0, "repairs_chance"),
    ("Pay poor tax of $15", None, -15, None),
    ("Take a trip on the Reading Railroad", 5, 0, None),
    ("Take a walk on the Boardwalk", 39, 0, None),
    ("Elected Chairman: pay each player $50", None, 0, "per_player_pay"),
    ("Building loan matures: collect $150", None, 150, None),
]

CHEST_CARDS = [
    ("Advance to Go", 0, 0, None),
    ("Bank error in your favor: collect $200", None, 200, None),
    ("Doctor's fee: pay $50", None, -50, None),
    ("From sale of stock you get $45", None, 45, None),
    ("Get Out of Jail Free", None, 0, "gojf"),
    ("Go to Jail", "jail", 0, None),
    ("Grand Opera opening: collect $50 from every player", None, 0, "per_player_collect"),
    ("Holiday fund matures: receive $100", None, 100, None),
    ("Income tax refund: collect $20", None, 20, None),
    ("Life insurance matures: collect $100", None, 100, None),
    ("Pay hospital: $100", None, -100, None),
    ("Pay school tax: $150", None, -150, None),
    ("Receive $25 for services", None, 25, None),
    ("Street repairs: $40/house, $115/hotel", None, 0, "repairs_chest"),
    ("Second prize in beauty contest: collect $10", None, 10, None),
    ("You inherit $100", None, 100, None),
]

REPAIRS = {"repairs_chance": (25, 100), "repairs_chest": (40, 115)}

NEAREST_RR = {7: 15, 22: 25, 36: 5}
NEAREST_UTIL = {7: 12, 22: 28, 36: 12}


def card_bank_total():
    """Net Bank payment summed over all 32 cards (Part I quotes +$485)."""
    return sum(c[2] for c in CHANCE_CARDS) + sum(c[2] for c in CHEST_CARDS)


def street_group_of(square):
    s = STREET_BY_SQUARE.get(square)
    return s.group if s else None


def group_hotel_rent(group):
    """Total rent of a color group fully developed to hotels."""
    return sum(STREET_BY_SQUARE[q].rents[5] for q in GROUPS[group])


def group_base_rent(group, doubled=False):
    """Total unimproved rent of a color group (doubled if held as a monopoly)."""
    mult = 2 if doubled else 1
    return mult * sum(STREET_BY_SQUARE[q].rents[0] for q in GROUPS[group])


def group_hotel_cost(group):
    """Cost of taking the whole group from zero houses to hotels (5 units each)."""
    return sum(5 * STREET_BY_SQUARE[q].house_cost for q in GROUPS[group])
