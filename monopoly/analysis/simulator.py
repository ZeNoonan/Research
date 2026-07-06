"""A Monte Carlo Monopoly engine.

This is an independent implementation of the game rules (tournament jail
rules, doubles, full card decks, even building, bank housing stock,
mortgages). It serves two purposes:

1. Cross-validation: empirical square frequencies and Bank flows from pure
   simulation should agree with the Markov chain's exact values.
2. Extension: experiments the papers describe but do not publish, e.g.
   head-to-head "monopoly duels" that make the growth-vs-value tradeoff
   between color groups visible.

The engine deliberately excludes trading and auctions; policies are simple
and symmetric so differences in outcomes are attributable to the properties
themselves.
"""

import random

from board import (
    STREET_BY_SQUARE, GROUPS, RAILROADS, RAILROAD_RENT, UTILITIES,
    UTILITY_MULT, CHANCE_CARDS, CHEST_CARDS, CHANCE_SQUARES, CHEST_SQUARES,
    NEAREST_RR, NEAREST_UTIL, REPAIRS, GO_SALARY, INCOME_TAX, LUXURY_TAX,
    INCOME_TAX_AMOUNT, LUXURY_TAX_AMOUNT, JAIL_FINE, GO_TO_JAIL,
    JAIL_VISITING,
)

PROPERTY_SQUARES = sorted([s for s in STREET_BY_SQUARE] + list(RAILROADS)
                          + list(UTILITIES))


class Player:
    def __init__(self, name, cash=1500):
        self.name = name
        self.cash = cash
        self.pos = 0
        self.owned = set()
        self.houses = {}          # square -> 0..5 (5 = hotel)
        self.mortgaged = set()
        self.in_jail = False
        self.jail_turns = 0
        self.gojf = 0
        self.alive = True

    def monopolies(self):
        return [g for g, m in GROUPS.items() if set(m) <= self.owned]

    def net_worth(self):
        v = self.cash
        for q in self.owned:
            s = STREET_BY_SQUARE.get(q)
            price = s.price if s else 200 if q in RAILROADS else 150
            v += price // 2 if q in self.mortgaged else price
            if s:
                v += self.houses.get(q, 0) * s.house_cost // 2
        return v


class Game:
    """No-trading Monopoly. `active_squares` limits which properties exist
    (used by duels); None means the whole board is purchasable."""

    def __init__(self, players, rng, active_squares=None, buy_reserve=0,
                 build_reserve=200, collect_stats=False):
        self.players = players
        self.rng = rng
        self.active = set(active_squares) if active_squares is not None \
            else set(PROPERTY_SQUARES)
        self.owner = {}
        for p in players:
            for q in p.owned:
                self.owner[q] = p
        self.buy_reserve = buy_reserve
        self.build_reserve = build_reserve
        self.bank_houses = 32
        self.bank_hotels = 12
        self.chance = list(range(16))
        self.chest = list(range(16))
        rng.shuffle(self.chance)
        rng.shuffle(self.chest)
        self.rolls = 0
        self.collect_stats = collect_stats
        # End-of-roll occupancy, comparable with the Markov chain's
        # stationary distribution: index 30 counts "In Jail".
        self.occupancy = [0] * 40 if collect_stats else None
        self.jail_rolls = 0
        self.bank_flow = 0.0      # net Bank -> players, for empirical Phi

    # -- money -------------------------------------------------------------

    def pay_bank(self, p, amount):
        self.raise_cash(p, amount)
        p.cash -= amount
        self.bank_flow -= amount
        if p.cash < 0:
            self.bankrupt(p, None)

    def bank_pays(self, p, amount):
        p.cash += amount
        self.bank_flow += amount

    def transfer(self, payer, payee, amount):
        self.raise_cash(payer, amount)
        actual = min(amount, max(payer.cash, 0)) if payer.cash < amount else amount
        payer.cash -= amount
        payee.cash += actual
        if payer.cash < 0:
            self.bankrupt(payer, payee)

    def raise_cash(self, p, needed):
        """Sell houses (half price) then mortgage until cash covers needed."""
        while p.cash < needed:
            sq = self._best_house_to_sell(p)
            if sq is None:
                break
            s = STREET_BY_SQUARE[sq]
            if p.houses[sq] == 5:
                if self.bank_houses >= 4:
                    p.houses[sq] = 4
                    self.bank_houses -= 4
                    self.bank_hotels += 1
                    p.cash += s.house_cost // 2
                else:            # no houses to break the hotel into: raze
                    p.houses[sq] = 0
                    self.bank_hotels += 1
                    p.cash += 5 * s.house_cost // 2
            else:
                p.houses[sq] -= 1
                self.bank_houses += 1
                p.cash += s.house_cost // 2
        while p.cash < needed:
            candidates = [q for q in p.owned if q not in p.mortgaged
                          and p.houses.get(q, 0) == 0]
            if not candidates:
                break
            q = min(candidates, key=lambda q: self._mortgage_value(q))
            p.mortgaged.add(q)
            p.cash += self._mortgage_value(q)

    def _mortgage_value(self, q):
        s = STREET_BY_SQUARE.get(q)
        price = s.price if s else (200 if q in RAILROADS else 150)
        return price // 2

    def _best_house_to_sell(self, p):
        built = [q for q in p.owned if p.houses.get(q, 0) > 0]
        if not built:
            return None
        # Sell from the tallest stack of the cheapest group (even selling).
        return min(built, key=lambda q: (STREET_BY_SQUARE[q].rents[5],
                                         -p.houses[q]))

    def bankrupt(self, p, creditor):
        p.alive = False
        for q in list(p.owned):
            s = STREET_BY_SQUARE.get(q)
            if s and p.houses.get(q, 0):
                refund = p.houses[q] * s.house_cost // 2
                if p.houses[q] == 5:
                    self.bank_hotels += 1
                else:
                    self.bank_houses += p.houses[q]
                p.houses[q] = 0
                if creditor:
                    creditor.cash += refund
            if creditor:
                creditor.owned.add(q)
                if q in p.mortgaged:
                    creditor.mortgaged.add(q)
                self.owner[q] = creditor
            else:
                self.owner.pop(q, None)
        if creditor:
            creditor.cash += max(p.cash, 0)
        p.owned.clear()

    # -- rent --------------------------------------------------------------

    def rent_due(self, q, roll, rr_double=False, util_10x=False):
        o = self.owner.get(q)
        if o is None or q in o.mortgaged:
            return None, 0
        s = STREET_BY_SQUARE.get(q)
        if s:
            h = o.houses.get(q, 0)
            if h:
                return o, s.rents[h]
            doubled = set(GROUPS[s.group]) <= o.owned
            return o, s.rents[0] * (2 if doubled else 1)
        if q in RAILROADS:
            k = len(o.owned & set(RAILROADS))
            r = RAILROAD_RENT[k]
            return o, 2 * r if rr_double else r
        k = len(o.owned & set(UTILITIES))
        mult = 10 if util_10x else UTILITY_MULT[k]
        return o, mult * roll

    # -- building ----------------------------------------------------------

    def build(self, p):
        for g in p.monopolies():
            members = GROUPS[g]
            if any(q in p.mortgaged for q in members):
                continue
            s0 = STREET_BY_SQUARE[members[0]]
            while p.cash - s0.house_cost >= self.build_reserve:
                q = min(members, key=lambda q: p.houses.get(q, 0))
                h = p.houses.get(q, 0)
                if h >= 5:
                    break
                if h == 4:
                    if self.bank_hotels < 1:
                        break
                    self.bank_hotels -= 1
                    self.bank_houses += 4
                else:
                    if self.bank_houses < 1:
                        break
                    self.bank_houses -= 1
                p.houses[q] = h + 1
                p.cash -= STREET_BY_SQUARE[q].house_cost

    # -- movement ----------------------------------------------------------

    def move_to(self, p, target, collect_go=True):
        if collect_go and target <= p.pos:
            self.bank_pays(p, GO_SALARY)
        p.pos = target

    def draw(self, deck_name, p, roll):
        deck = self.chance if deck_name == "chance" else self.chest
        cards = CHANCE_CARDS if deck_name == "chance" else CHEST_CARDS
        idx = deck.pop(0)
        deck.append(idx)
        label, move, cash, special = cards[idx]
        if special == "gojf":
            p.gojf += 1
            return
        if cash:
            if cash > 0:
                self.bank_pays(p, cash)
            else:
                self.pay_bank(p, -cash)
            return
        if special in REPAIRS:
            per_house, per_hotel = REPAIRS[special]
            n_h = sum(h for h in p.houses.values() if h < 5)
            n_hot = sum(1 for h in p.houses.values() if h == 5)
            self.pay_bank(p, per_house * n_h + per_hotel * n_hot)
            return
        if special == "per_player_pay":
            for q in self.players:
                if q is not p and q.alive:
                    self.transfer(p, q, 50)
                    if not p.alive:
                        return
            return
        if special == "per_player_collect":
            for q in self.players:
                if q is not p and q.alive:
                    self.transfer(q, p, 50)
            return
        if move == "jail":
            self.go_to_jail(p)
            return
        if move == "back3":
            p.pos -= 3
            self.land(p, roll)
            return
        if move is not None:
            tgt = NEAREST_RR[p.pos] if move == "nearest_rr" else (
                NEAREST_UTIL[p.pos] if move == "nearest_util" else move)
            self.move_to(p, tgt)
            self.land(p, roll, rr_double=(special == "rr_double"),
                      util_10x=(special == "util_10x"))

    def go_to_jail(self, p):
        p.pos = JAIL_VISITING
        p.in_jail = True
        p.jail_turns = 0

    def land(self, p, roll, rr_double=False, util_10x=False):
        q = p.pos
        if q == GO_TO_JAIL:
            self.go_to_jail(p)
            return
        if q == INCOME_TAX:
            self.pay_bank(p, INCOME_TAX_AMOUNT)
            return
        if q == LUXURY_TAX:
            self.pay_bank(p, LUXURY_TAX_AMOUNT)
            return
        if q in CHANCE_SQUARES:
            self.draw("chance", p, roll)
            return
        if q in CHEST_SQUARES:
            self.draw("chest", p, roll)
            return
        if q in self.active and q in PROPERTY_SQUARES:
            owner, rent = self.rent_due(
                q, self.rng.randint(1, 6) + self.rng.randint(1, 6)
                if util_10x else roll, rr_double, util_10x)
            if owner is None and q not in self.owner:
                s = STREET_BY_SQUARE.get(q)
                price = s.price if s else (200 if q in RAILROADS else 150)
                if p.cash - price >= self.buy_reserve:
                    p.cash -= price
                    p.owned.add(q)
                    self.owner[q] = p
            elif owner is not None and owner is not p and rent:
                self.transfer(p, owner, rent)

    def _record(self, p):
        if self.collect_stats:
            self.occupancy[30 if p.in_jail else p.pos] += 1

    def take_turn(self, p, stay_in_jail_late=True):
        doubles = 0
        while True:
            d1, d2 = self.rng.randint(1, 6), self.rng.randint(1, 6)
            self.rolls += 1
            roll = d1 + d2
            if p.in_jail:
                self.jail_rolls += 1
                unowned_left = any(q not in self.owner for q in self.active)
                prefer_out = unowned_left or not stay_in_jail_late
                if p.gojf and prefer_out:
                    p.gojf -= 1
                    p.in_jail = False
                elif prefer_out and p.cash > 300:
                    self.pay_bank(p, JAIL_FINE)
                    if not p.alive:
                        return
                    p.in_jail = False
                elif d1 == d2:
                    p.in_jail = False
                    p.pos = JAIL_VISITING + roll
                    self.land(p, roll)
                    self._record(p)
                    break
                elif p.jail_turns >= 2:
                    self.pay_bank(p, JAIL_FINE)
                    if not p.alive:
                        return
                    p.in_jail = False
                    p.pos = JAIL_VISITING + roll
                    self.land(p, roll)
                    self._record(p)
                    break
                else:
                    p.jail_turns += 1
                    self._record(p)
                    break
                # got out by card or fine: move normally below
            if d1 == d2:
                doubles += 1
                if doubles == 3:
                    self.go_to_jail(p)
                    self._record(p)
                    break
            raw = p.pos + roll
            if raw >= 40:
                self.bank_pays(p, GO_SALARY)
            p.pos = raw % 40
            self.land(p, roll)
            self._record(p)
            if not p.alive or p.in_jail or d1 != d2:
                break
        if p.alive:
            self.build(p)

    def play(self, max_rolls=3000):
        while True:
            for p in self.players:
                if not p.alive:
                    continue
                self.take_turn(p)
                alive = [x for x in self.players if x.alive]
                if len(alive) == 1:
                    return alive[0]
                if self.rolls >= max_rolls:
                    return None


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------

def movement_frequencies(n_rolls=2_000_000, seed=11):
    """Empirical landing frequencies with everyone staying in jail as long
    as possible and no property activity - independent check of the chain."""
    rng = random.Random(seed)
    p = Player("walker", cash=10 ** 9)
    g = Game([p], rng, active_squares=[], collect_stats=True)
    while g.rolls < n_rolls:
        g.take_turn(p, stay_in_jail_late=True)
    return g


def empirical_phi(n_rolls=2_000_000, seed=13):
    """Bank flow per roll on an empty board (full Go crediting, real cards,
    tournament jail). Compare with Chain().phi()."""
    rng = random.Random(seed)
    p = Player("walker", cash=10 ** 9)
    g = Game([p], rng, active_squares=[])
    start = p.cash
    while g.rolls < n_rolls:
        g.take_turn(p, stay_in_jail_late=True)
    return (p.cash - start) / g.rolls


def duel(group_a, group_b, cash, rng, max_rolls=3000):
    """Two players, each owning one complete color group plus `cash`; the
    rest of the board is inert. Returns the winner's group or None (draw)."""
    pa, pb = Player("A", cash), Player("B", cash)
    pa.owned = set(GROUPS[group_a])
    pb.owned = set(GROUPS[group_b])
    active = list(GROUPS[group_a]) + list(GROUPS[group_b])
    g = Game([pa, pb], rng, active_squares=active, build_reserve=150)
    w = g.play(max_rolls=max_rolls)
    if w is pa:
        return group_a
    if w is pb:
        return group_b
    return None


def duel_matrix(cash_levels=(750, 1500, 3000), games=400, seed=17):
    """Win rates for every pair of color groups at several cash levels."""
    rng = random.Random(seed)
    groups = list(GROUPS)
    results = {}
    for cash in cash_levels:
        table = {ga: {} for ga in groups}
        for i, ga in enumerate(groups):
            for gb in groups[i + 1:]:
                wins_a = wins_b = draws = 0
                for k in range(games):
                    # alternate who is listed first to cancel turn-order edge
                    if k % 2 == 0:
                        w = duel(ga, gb, cash, rng)
                    else:
                        w = duel(gb, ga, cash, rng)
                    if w == ga:
                        wins_a += 1
                    elif w == gb:
                        wins_b += 1
                    else:
                        draws += 1
                table[ga][gb] = (wins_a, wins_b, draws)
        results[cash] = table
    return results


def full_game_stats(n_games=300, n_players=4, seed=23, max_rolls=4000):
    """Play full four-player games (no trading). Records game length and a
    sample of net-worth trajectories to illustrate the exponential."""
    rng = random.Random(seed)
    lengths, unfinished = [], 0
    sample_path = None
    for k in range(n_games):
        players = [Player(f"P{i+1}") for i in range(n_players)]
        g = Game(players, rng, buy_reserve=0, build_reserve=250)
        track = (k == 0)
        path = []
        while True:
            over = False
            for p in players:
                if not p.alive:
                    continue
                g.take_turn(p)
                alive = [x for x in players if x.alive]
                if len(alive) <= 1 or g.rolls >= max_rolls:
                    over = True
                    break
            if track:
                path.append([round(p.net_worth() if p.alive else 0)
                             for p in players])
            if over:
                break
        if g.rolls >= max_rolls and sum(p.alive for p in players) > 1:
            unfinished += 1
        else:
            lengths.append(g.rolls)
        if track:
            sample_path = path
    return {"lengths": lengths, "unfinished": unfinished,
            "n_games": n_games, "sample_path": sample_path}
