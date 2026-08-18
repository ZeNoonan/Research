"""Build a legal 15-man FPL squad, exactly, by integer programming.

Two squads, from the same 2026/27 price list:

**The factor squad** maximises total stars over the players the pre-season
board can rate, breaking ties on the quality engine. This is the board's
own answer to "who would you actually pick".

**The crowd squad** maximises total ownership — the most-owned *legal* 15,
which is as close as one can get to the squad the field is collectively
holding. It draws from **every** listed player, not just the rated ones:
about 240 percentage points of ownership sit with players the board cannot
rate (promoted-club squads, new signings, and regulars who fell under the
minutes gate), and excluding them would misrepresent the crowd.

Both obey the real rules: £100.0m budget, 2 GK / 5 DEF / 5 MID / 3 FWD, and
at most 3 players from one club. The starting XI is then chosen from the 15
under FPL's formation rules (1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD).

Solved exactly with CBC rather than greedily - a greedy pick is easy to get
wrong when the club cap and the budget interact.

``--objective points`` swaps the factor squad's objective from stars to
projected points, under identical constraints, so the cost of the binary
summary can be measured rather than argued about. Stars remain the default;
every run prints the two side by side.

``--eleven`` builds a bench-free starting XI instead: a fixed formation and
its own budget, no bench and therefore no bench-forward cap. Different
problem, not a slice of the 15-man one.

    python squad.py
    python squad.py --objective points
    python squad.py --eleven 4-5-1 --xi-budget 86.5
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pulp

import model
import preseason

HERE = Path(__file__).parent

BUDGET = 100.0
SQUAD = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
MAX_PER_CLUB = 3
# FPL formation rules for the starting XI.
XI_MIN = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}
XI_MAX = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}
XI_SIZE = 11
SEASON_GWS = 38
# What a bench place is worth relative to a starting one, when the squad is
# chosen on projected points. A bench player only scores through
# autosubs, so he is worth a fraction of a starter - not the same, which is
# what maximising total stars implicitly assumes.
BENCH_WEIGHT = 0.1

# A benched forward is a dead spot. Three forwards are compulsory but only
# one has to start, so the third is often a place you are buying purely to
# fill the slot - and every pound spent there is a pound not in the eleven.
# Cap what may sit on the bench at forward; anything dearer must start.
BENCH_FWD_MAX_PRICE = 4.5


def projected_points(df: pd.DataFrame) -> pd.Series:
    """Projected season points: xPts/90 x expected minutes / 90.

    Backward-looking - ``minutes_share`` is last season's - so it is a
    working proxy for comparing squads, not a forecast of 2026/27.
    """
    return df["xpts90"] * df["minutes_share"] * SEASON_GWS


def must_start(pool: pd.DataFrame,
               bench_fwd_max: float | None = BENCH_FWD_MAX_PRICE) -> set:
    """Row labels that may not be benched: forwards dearer than the cap.

    "No benched forward costs more than X" and "any forward costing more
    than X must be in the eleven" are the same constraint, and the second
    is the one an integer program can state in a single inequality.
    """
    if bench_fwd_max is None:
        return set()
    return set(pool.index[(pool["position"] == "FWD")
                          & (pool["price"] > bench_fwd_max)])


def _solve(pool: pd.DataFrame, objective: pd.Series, budget: float | None,
           shape: dict, total: int, min_shape: dict | None = None,
           max_per_club: int | None = MAX_PER_CLUB,
           equality: bool = True, forced: set | None = None,
           floor: tuple | None = None) -> list:
    """Maximise ``objective`` subject to the squad rules. Returns row labels.

    ``floor`` is an optional ``(series, value)`` pair constraining that
    series' selected total to at least ``value`` - the second leg of a
    lexicographic solve, where a tie-break may not cost anything on the
    primary objective.
    """
    prob = pulp.LpProblem("squad", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in pool.index}

    prob += pulp.lpSum(objective[i] * x[i] for i in pool.index)
    for i in forced or set():
        prob += x[i] == 1
    if floor is not None:
        series, value = floor
        prob += pulp.lpSum(series[i] * x[i] for i in pool.index) >= value
    prob += pulp.lpSum(x[i] for i in pool.index) == total
    if budget is not None:
        prob += pulp.lpSum(pool.at[i, "price"] * x[i]
                           for i in pool.index) <= budget

    for pos, n in shape.items():
        members = [i for i in pool.index if pool.at[i, "position"] == pos]
        if equality:
            prob += pulp.lpSum(x[i] for i in members) == n
        else:
            prob += pulp.lpSum(x[i] for i in members) <= n
            prob += pulp.lpSum(x[i] for i in members) >= min_shape[pos]

    if max_per_club:
        for club in pool["team"].unique():
            members = [i for i in pool.index if pool.at[i, "team"] == club]
            prob += pulp.lpSum(x[i] for i in members) <= max_per_club

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(f"no optimal squad found: {pulp.LpStatus[status]}")
    return [i for i in pool.index if x[i].value() > 0.5]


def star_ceiling(pool: pd.DataFrame, col: str = "stars",
                 shape: dict | None = None) -> tuple[int, dict]:
    """Highest ``col`` total any legal ``shape`` could reach, and the breakdown.

    Take the best ``n`` ratings in each position, where ``n`` is what the
    shape requires, and add them up. This ignores the budget and the club
    cap, so it is an upper bound rather than an achievable total - which is
    what makes it useful: if the squad *reaches* it, those constraints did
    not bind and the objective is exhausted.
    """
    per = {pos: sorted(pool.loc[pool["position"] == pos, col],
                       reverse=True)[:n]
           for pos, n in (shape or SQUAD).items()}
    return int(sum(sum(v) for v in per.values())), per


def saturation(squad: pd.DataFrame, pool: pd.DataFrame,
               col: str = "stars", shape: dict | None = None) -> dict:
    """Whether the primary objective has run out of discriminating power.

    A saturated objective is not a failure - it means the board rates
    enough players highly that the shape, not the ratings, is the binding
    constraint. It does need to be visible, because at the ceiling every
    candidate squad ties on the primary and the **tie-break is selecting
    the team**. A silent saturated objective is how a bad tie-break hides.
    """
    ceiling, per = star_ceiling(pool, col, shape)
    achieved = int(squad[col].sum())
    return {"achieved": achieved, "ceiling": ceiling,
            "saturated": achieved >= ceiling, "per_position": per,
            "noun": "eleven" if shape else "fifteen"}


def saturation_note(sat: dict, secondary: str | None) -> str:
    """One line describing the saturation state, for terminal and page."""
    shape = "  ".join(f"{pos} {'+'.join(str(int(s)) for s in v)}"
                      for pos, v in sat["per_position"].items())
    if not sat["saturated"]:
        return (f"{sat['achieved']} of a reachable {sat['ceiling']} stars "
                f"({shape}) — the budget or the 3-per-club cap is binding.")
    return (f"{sat['achieved']} stars, which is the ceiling for this shape "
            f"({shape}). The star objective is exhausted: every legal "
            f"{sat.get('noun', 'fifteen')} at {sat['ceiling']} ties on it, so "
            + (f"the tie-break ({secondary}) is selecting the team."
               if secondary else "the tie-break is selecting the team."))


def _squad_problem(pool: pd.DataFrame, budget: float, forced: set):
    """The 15-man problem, plus the eleven only when the bench cap needs it.

    ``forced`` names players who may not be benched. Honouring that while
    choosing the 15 needs the XI in the same program: a squad picked first
    and split afterwards can be one the cap makes unstartable. When nothing
    is forced the ``y`` variables are left out entirely, so the star path
    solves exactly the problem it always did.
    """
    prob = pulp.LpProblem("squad", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in pool.index}
    prob += pulp.lpSum(x[i] for i in pool.index) == sum(SQUAD.values())
    prob += pulp.lpSum(pool.at[i, "price"] * x[i] for i in pool.index) <= budget
    for pos, n in SQUAD.items():
        members = [i for i in pool.index if pool.at[i, "position"] == pos]
        prob += pulp.lpSum(x[i] for i in members) == n
    for club in pool["team"].unique():
        members = [i for i in pool.index if pool.at[i, "team"] == club]
        prob += pulp.lpSum(x[i] for i in members) <= MAX_PER_CLUB

    forced = forced & set(pool.index)
    if forced:
        y = {i: pulp.LpVariable(f"y_{i}", cat="Binary") for i in pool.index}
        prob += pulp.lpSum(y[i] for i in pool.index) == XI_SIZE
        for i in pool.index:
            prob += y[i] <= x[i]
        for pos in SQUAD:
            members = [i for i in pool.index if pool.at[i, "position"] == pos]
            prob += pulp.lpSum(y[i] for i in members) <= XI_MAX[pos]
            prob += pulp.lpSum(y[i] for i in members) >= XI_MIN[pos]
        for i in forced:
            prob += x[i] <= y[i]
    return prob, x


def pick_squad(pool: pd.DataFrame, primary: str, secondary: str | None = None,
               budget: float = BUDGET, forced: set | None = None) -> pd.DataFrame:
    """Best legal 15 on ``primary``; ties broken on ``secondary``.

    Solved lexicographically - the secondary objective is optimised only
    over squads that already achieve the best possible primary total, so a
    tie-break can never cost a star.

    ``forced`` names players who may not be benched (see ``must_start``).
    """
    forced = forced or set()
    prob, x = _squad_problem(pool, budget, forced)
    prob += pulp.lpSum(pool.at[i, primary] * x[i] for i in pool.index)
    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(f"no optimal squad found: {pulp.LpStatus[status]}")
    chosen = [i for i in pool.index if x[i].value() > 0.5]
    if secondary is None:
        return pool.loc[chosen]

    best = float(pool.loc[chosen, primary].sum())
    prob, x = _squad_problem(pool, budget, forced)
    prob += pulp.lpSum(pool.at[i, secondary] * x[i] for i in pool.index)
    prob += pulp.lpSum(pool.at[i, primary] * x[i] for i in pool.index) >= best
    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(f"no optimal squad found: {pulp.LpStatus[status]}")
    return pool.loc[[i for i in pool.index if x[i].value() > 0.5]]


def pick_squad_points(pool: pd.DataFrame, col: str = "xpts_season",
                      bench_weight: float = BENCH_WEIGHT,
                      captain: bool = True,
                      budget: float = BUDGET,
                      forced: set | None = None) -> pd.DataFrame:
    """Best legal 15 on projected points, choosing squad, XI and captain at once.

    Maximising total stars over the 15 treats a bench place as worth a
    starting one, which is how £23.5m of a £100m budget ended up on the
    bench. Here the three decisions are one problem: ``x`` picks the 15,
    ``y`` the XI with ``y <= x``, ``c`` the captain with ``c <= y``, and the
    objective is ``XI + bench_weight x bench + captain``. Solving them
    jointly matters - the best 15 under a bench discount is not the best 15
    picked first and then split.

    Note the captain conventions differ by design: ``c`` doubles season
    points, while ``report`` names the captain on ``xpts90`` because
    captaincy is a weekly decision made among players who are playing.
    They agree on the current data (Bruno Fernandes on both) but need not
    in general, so ``capt`` is returned rather than assumed.
    """
    prob = pulp.LpProblem("squad_points", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in pool.index}
    y = {i: pulp.LpVariable(f"y_{i}", cat="Binary") for i in pool.index}
    c = {i: pulp.LpVariable(f"c_{i}", cat="Binary") for i in pool.index}

    prob += pulp.lpSum(
        pool.at[i, col] * (y[i] + bench_weight * (x[i] - y[i])
                           + (c[i] if captain else 0))
        for i in pool.index)

    prob += pulp.lpSum(x[i] for i in pool.index) == sum(SQUAD.values())
    prob += pulp.lpSum(y[i] for i in pool.index) == XI_SIZE
    prob += pulp.lpSum(c[i] for i in pool.index) == (1 if captain else 0)
    prob += pulp.lpSum(pool.at[i, "price"] * x[i] for i in pool.index) <= budget
    for i in pool.index:
        prob += y[i] <= x[i]
        prob += c[i] <= y[i]
    for pos, n in SQUAD.items():
        members = [i for i in pool.index if pool.at[i, "position"] == pos]
        prob += pulp.lpSum(x[i] for i in members) == n
        prob += pulp.lpSum(y[i] for i in members) <= XI_MAX[pos]
        prob += pulp.lpSum(y[i] for i in members) >= XI_MIN[pos]
    for club in pool["team"].unique():
        members = [i for i in pool.index if pool.at[i, "team"] == club]
        prob += pulp.lpSum(x[i] for i in members) <= MAX_PER_CLUB
    # A forward over the bench cap has to start if he is bought at all.
    for i in (forced or set()) & set(pool.index):
        prob += x[i] <= y[i]

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(f"no optimal squad found: {pulp.LpStatus[status]}")
    chosen = [i for i in pool.index if x[i].value() > 0.5]
    out = pool.loc[chosen].copy()
    out["xi"] = [y[i].value() > 0.5 for i in chosen]
    out["capt"] = [c[i].value() > 0.5 for i in chosen]
    return out


def parse_formation(text: str) -> dict:
    """``"4-5-1"`` -> ``{"GK": 1, "DEF": 4, "MID": 5, "FWD": 1}``, validated."""
    try:
        d, m, f = (int(p) for p in text.split("-"))
    except ValueError:
        raise ValueError(f"formation must look like '4-5-1', got {text!r}")
    shape = {"GK": 1, "DEF": d, "MID": m, "FWD": f}
    if sum(shape.values()) != XI_SIZE:
        raise ValueError(f"{text} is {sum(shape.values())} players, not {XI_SIZE}")
    for pos, n in shape.items():
        if not XI_MIN[pos] <= n <= XI_MAX[pos]:
            raise ValueError(
                f"{text} is not a legal FPL formation: {n} {pos}, "
                f"allowed {XI_MIN[pos]}-{XI_MAX[pos]}")
    return shape


def pick_eleven(pool: pd.DataFrame, primary: str, secondary: str | None = None,
                budget: float = BUDGET, formation: str = "4-5-1") -> pd.DataFrame:
    """The best legal starting XI at a fixed formation and budget - no bench.

    A different problem from ``pick_squad``, not a slice of it. With no
    bench there is no dead spot to cap and no bench discount to argue
    about: every player picked is a player who scores, so the objective
    means exactly what it says. The 3-per-club cap still applies - it is an
    FPL squad rule, and an eleven is part of a squad.

    Solved lexicographically like ``pick_squad``: ``secondary`` is only
    optimised over elevens already achieving the best possible ``primary``.
    """
    shape = parse_formation(formation)
    chosen = _solve(pool, pool[primary], budget, shape, XI_SIZE)
    if secondary is None:
        return pool.loc[chosen]
    best = float(pool.loc[chosen, primary].sum())
    chosen = _solve(pool, pool[secondary], budget, shape, XI_SIZE,
                    floor=(pool[primary], best))
    return pool.loc[chosen]


def pick_xi(squad: pd.DataFrame, objective: str,
            forced: set | None = None) -> pd.DataFrame:
    """The best legal starting XI out of the 15.

    ``forced`` names players who may not be benched. The squad picker has
    already guaranteed such an eleven exists; this repeats the constraint so
    the eleven it actually names obeys it too.
    """
    # The 15 are already paid for, so the XI has no budget of its own.
    chosen = _solve(squad, squad[objective], budget=None,
                    shape=XI_MAX, total=XI_SIZE, min_shape=XI_MIN,
                    max_per_club=None, equality=False,
                    forced=(forced or set()) & set(squad.index))
    return squad.loc[chosen]


def bench_fodder(unrated: pd.DataFrame, cap: float,
                 respect_availability: bool = True) -> pd.DataFrame:
    """Unrated forwards at or under the bench cap, as scoreless squad filler.

    The board cannot rate these players - no Premier League minutes - and
    ordinarily that keeps them out of the factor squad entirely. A capped
    bench forward is the one slot where that does not matter: it is bought
    to be a legal body and nothing else, so the absence of a rating is not
    a reason to exclude, it is the reason the slot is cheap. They enter at
    **zero** on every objective, so the optimiser never prefers one to a
    rated player it could otherwise start.
    """
    f = unrated[(unrated["position"] == "FWD") & (unrated["price"] <= cap)].copy()
    if respect_availability:
        f = f[~f["unavailable"]]
    if f.empty:
        return f
    f["rated"] = False
    for col, val in (("stars", 0), ("xpts90", 0.0), ("xpts_season", 0.0),
                     ("minutes_share", 0.0), ("factor_letters", ""),
                     ("diagnostic_letters", ""), ("factors_assessed", 0)):
        f[col] = val
    return f


def build(listing: str | Path, history: str | Path,
          respect_availability: bool = True, objective: str = "stars",
          bench_weight: float = BENCH_WEIGHT,
          bench_fwd_max: float | None = BENCH_FWD_MAX_PRICE):
    """Return (factor_squad, crowd_squad), each with an ``xi`` flag.

    ``objective`` picks how the factor squad is chosen:

    * ``"stars"`` (default) - most total stars over the 15, ties broken on
      the quality engine. This is the board's own answer, and the one every
      argument in the README is built on.
    * ``"points"`` - most projected points, bench discounted by
      ``bench_weight`` and the captain doubled, all solved jointly.

    ``bench_fwd_max`` caps what a **benched** forward may cost. Three
    forwards are compulsory but only one has to start, so the third is a
    dead spot; capping it stops the objective spending on a player it has
    already decided not to field. Because no *rated* forward is that cheap,
    the pool gains the unrated forwards at or under the cap - see
    ``bench_fodder``. Pass ``None`` to drop the cap.

    The crowd squad is unaffected by any of this: it is chosen on
    ownership, and it is a model of what the field holds rather than a team
    anyone is picking.

    Players flagged in ``unavailable.csv`` are barred from both squads. The
    board still rates them - an injury does not change what a player is
    worth - but you cannot field one, so neither squad may pick one. Pass
    ``respect_availability=False`` to see what the squads would have been.
    """
    if objective not in ("stars", "points"):
        raise ValueError(f"objective must be 'stars' or 'points', got {objective!r}")
    rated, unrated = preseason.rate_preseason(listing, history)
    board = rated[rated["eligible"]].copy()

    # The crowd's pool is everyone listed: ownership is known for all of
    # them, and a sixth of it sits off the rated board.
    cols = ["name", "position", "team", "price", "owned_pct", "unavailable"]
    everyone = pd.concat([rated[cols], unrated[cols]], ignore_index=True)

    if respect_availability:
        board = board[~board["unavailable"]]
        everyone = everyone[~everyone["unavailable"]]

    board = board.copy()
    board["xpts_season"] = projected_points(board)
    board["rated"] = True
    if bench_fwd_max is not None:
        board = pd.concat([board, bench_fodder(unrated, bench_fwd_max,
                                               respect_availability)])
    forced = must_start(board, bench_fwd_max)

    if objective == "stars":
        # The tie-break is projected season points, not the raw per-90 rate.
        # The star total is saturated - it hits its positional ceiling, so
        # every legal fifteen at the ceiling ties on the primary and the
        # SECONDARY objective is what actually picks the team. A per-90 rate
        # ignores how often a player is on the pitch, which is the same
        # mistake pick_xi used to make one level down.
        factor = pick_squad(board, "stars", "xpts_season", forced=forced).copy()
        # Which eleven start is decided on projected points, not on stars.
        # Stars are a coarse ordinal, so they tie constantly and the
        # tie falls to index order, which is nobody's idea of a team
        # sheet. Same reasoning that already picks the captain on xpts90.
        factor["xi"] = factor.index.isin(
            pick_xi(factor, "xpts_season", forced=forced).index)
    else:
        factor = pick_squad_points(board, "xpts_season", bench_weight,
                                   forced=forced)

    # Is the star objective still discriminating, or has it run out? Only
    # meaningful for the star path; the points objective is continuous and
    # does not saturate.
    factor.attrs["saturation"] = (
        saturation(factor, board) if objective == "stars" else None)
    factor.attrs["secondary"] = "xpts_season" if objective == "stars" else None

    crowd = pick_squad(everyone, "owned_pct").copy()
    # The crowd pool deliberately has no ratings - unrated players have
    # none - so its XI stays on ownership.
    crowd["xi"] = crowd.index.isin(pick_xi(crowd, "owned_pct").index)
    return factor, crowd


def build_eleven(listing: str | Path, history: str | Path,
                 budget: float, formation: str = "4-5-1",
                 respect_availability: bool = True,
                 objective: str = "stars"):
    """Return (factor_eleven, crowd_eleven) at a fixed formation and budget.

    The same two-pool contrast as ``build``, for a bench-free eleven. The
    crowd side always maximises ownership; ``objective`` picks how the
    factor side is chosen:

    * ``"stars"`` (default) - most total stars, ties broken on projected
      season points.
    * ``"points"`` - most projected season points outright, stars ignored.
      With no bench this is a clean objective: every player picked is a
      player who scores, so there is no bench discount to argue about.

    No bench-forward filler here - filler exists to fill a dead bench spot,
    and there is no bench.
    """
    if objective not in ("stars", "points"):
        raise ValueError(
            f"objective must be 'stars' or 'points', got {objective!r}")
    rated, unrated = preseason.rate_preseason(listing, history)
    board = rated[rated["eligible"]].copy()
    cols = ["name", "position", "team", "price", "owned_pct", "unavailable"]
    everyone = pd.concat([rated[cols], unrated[cols]], ignore_index=True)
    if respect_availability:
        board = board[~board["unavailable"]]
        everyone = everyone[~everyone["unavailable"]]

    board["xpts_season"] = projected_points(board)
    if objective == "stars":
        factor = pick_eleven(board, "stars", "xpts_season",
                             budget, formation).copy()
    else:
        factor = pick_eleven(board, "xpts_season", None,
                             budget, formation).copy()
    crowd = pick_eleven(everyone, "owned_pct", None, budget, formation).copy()
    factor["xi"] = True
    crowd["xi"] = True
    # Saturation is a property of the star objective; the points objective
    # is continuous and cannot exhaust itself.
    factor.attrs["saturation"] = (
        saturation(factor, board, shape=parse_formation(formation))
        if objective == "stars" else None)
    factor.attrs["secondary"] = "xpts_season" if objective == "stars" else None
    return factor, crowd


def _order(df: pd.DataFrame, by: str) -> pd.DataFrame:
    df = df.copy()
    df["position"] = pd.Categorical(df["position"], model.POSITIONS)
    return df.sort_values(["xi", "position", by],
                          ascending=[False, True, False])


def report(squad: pd.DataFrame, title: str, by: str, extra: str | None,
           captain_by: str) -> None:
    print(f"\n{title}")
    print(f"  cost £{squad['price'].sum():.1f}m of £{BUDGET:.0f}m"
          f"   ({int(squad['xi'].sum())} starting, {len(squad) - int(squad['xi'].sum())} on the bench)")
    xi = squad[squad["xi"]]
    shape = "-".join(str(int((xi["position"] == p).sum()))
                     for p in ("DEF", "MID", "FWD"))
    print(f"  formation {shape}")
    # Captaincy doubles points, so it goes on expected return, not on the
    # star count - half the squad ties at 5 stars and nlargest would then
    # pick arbitrarily.
    order = xi.nlargest(2, captain_by)
    print(f"  captain {order.iloc[0]['name']}   vice {order.iloc[-1]['name']}")
    sat = squad.attrs.get("saturation")
    if sat:
        print("  " + saturation_note(sat, squad.attrs.get("secondary")))
    print()
    for _, r in _order(squad, by).iterrows():
        mark = " " if r["xi"] else "B"
        val = f"{r[extra]}" if extra else ""
        print(f"   {mark} {r['position']:4} {r['name'][:28]:29} "
              f"{r['team'][:14]:15} £{r['price']:>4.1f}m  {val}")


def compare(listing, history, bench_weight: float,
            bench_fwd_max: float | None) -> None:
    """Star objective against points objective, same constraints."""
    squads = {o: build(listing, history, objective=o,
                       bench_weight=bench_weight,
                       bench_fwd_max=bench_fwd_max)[0]
              for o in ("stars", "points")}

    def score(sq):
        xi = sq[sq["xi"]]
        capt = (xi[xi["capt"]]["xpts_season"].iloc[0] if "capt" in sq
                and sq["capt"].any()
                else xi.nlargest(1, "xpts90")["xpts_season"].iloc[0])
        return xi["xpts_season"].sum(), xi["xpts_season"].sum() + capt

    print(f"\nOBJECTIVE COMPARISON  (bench weighted {bench_weight}, "
          "captain doubled, identical constraints)")
    print(f"  {'objective':<10} {'XI pts':>8} {'+capt':>8} {'stars':>6} "
          f"{'bench £m':>9} {'spend':>7}")
    for name, sq in squads.items():
        xi_pts, total = score(sq)
        print(f"  {name:<10} {xi_pts:>8.1f} {total:>8.1f} "
              f"{int(sq['stars'].sum()):>6} "
              f"{sq[~sq['xi']]['price'].sum():>9.1f} "
              f"{sq['price'].sum():>6.1f}m")
    gap = score(squads["points"])[1] - score(squads["stars"])[1]
    shared = set(squads["stars"]["name"]) & set(squads["points"]["name"])
    print(f"\n  the points objective is worth {gap:+.1f} projected points "
          f"over a season")
    print(f"  the two squads share {len(shared)} of 15: "
          f"{', '.join(sorted(shared)) if shared else 'none'}")
    for name, sq in squads.items():
        bf = sq[(~sq["xi"]) & (sq["position"] == "FWD")]
        note = (", ".join(f"{r['name']} £{r['price']:.1f}m"
                          for _, r in bf.iterrows())
                if len(bf) else
                "none — all three start, so the cap frees nothing here")
        print(f"  {name:<7} benched forwards: {note}")


def report_eleven(listing, history, budget: float, formation: str,
                  objective: str = "stars") -> None:
    """Print the factor eleven and the crowd eleven at a fixed formation."""
    factor, crowd = build_eleven(listing, history, budget, formation,
                                 objective=objective)

    def block(sq, title, by, extra):
        print(f"\n{title}")
        print(f"  cost £{sq['price'].sum():.1f}m of £{budget:.1f}m"
              f"   (£{budget - sq['price'].sum():.1f}m unspent)")
        print(f"  formation {formation}")
        order = sq.nlargest(2, "xpts90" if "xpts90" in sq else "owned_pct")
        print(f"  captain {order.iloc[0]['name']}   "
              f"vice {order.iloc[-1]['name']}")
        sat = sq.attrs.get("saturation")
        if sat:
            print("  " + saturation_note(sat, sq.attrs.get("secondary")))
        proj = sq["xpts_season"].sum() if "xpts_season" in sq else None
        if proj is not None:
            capt = order.iloc[0]["xpts_season"]
            print(f"  projected {proj:.1f} over a season, {proj + capt:.1f} "
                  f"with the captain doubled")
        print()
        for _, r in _order(sq, by).iterrows():
            print(f"     {r['position']:4} {r['name'][:28]:29} "
                  f"{r['team'][:14]:15} £{r['price']:>4.1f}m  {extra(r)}")

    title = ("best total stars" if objective == "stars"
             else "most projected points")
    block(factor, f"THE FACTOR ELEVEN — {formation}, {title}",
          "stars" if objective == "stars" else "xpts_season",
          lambda r: f"{int(r['stars'])}★ {r['factor_letters']:<6} "
                    f"xP/90 {r['xpts90']:.2f}  proj {r['xpts_season']:>5.1f}  "
                    f"owned {r['owned_pct']:>5.1f}%")
    block(crowd, f"THE CROWD ELEVEN — {formation}, most owned",
          "owned_pct", lambda r: f"owned {r['owned_pct']:>5.1f}%")

    overlap = sorted(set(factor["name"]) & set(crowd["name"]))
    print(f"\nOverlap: {len(overlap)} of 11 — "
          + (", ".join(overlap) if overlap else "none"))

    # The same star-versus-points contrast the 15-man path prints. With no
    # bench it is a cleaner comparison: every player picked actually scores.
    rated, _ = preseason.rate_preseason(listing, history)
    board = rated[rated["eligible"] & ~rated["unavailable"]].copy()
    board["xpts_season"] = projected_points(board)
    alt = pick_eleven(board, "xpts_season", None, budget, formation)
    a_capt = alt.nlargest(1, "xpts90")["xpts_season"].iloc[0]
    f_capt = factor.nlargest(1, "xpts90")["xpts_season"].iloc[0]
    print(f"\nOBJECTIVE COMPARISON  ({formation}, £{budget:.1f}m, "
          "captain doubled)")
    print(f"  {'objective':<12} {'stars':>6} {'spend':>8} {'proj':>8} {'+capt':>8}")
    for lbl, xi, capt in (("stars", factor, f_capt), ("points", alt, a_capt)):
        print(f"  {lbl:<12} {int(xi['stars'].sum()):>6} "
              f"{xi['price'].sum():>7.1f}m {xi['xpts_season'].sum():>8.1f} "
              f"{xi['xpts_season'].sum() + capt:>8.1f}")
    shared = set(factor["name"]) & set(alt["name"])
    print(f"  the points objective is worth "
          f"{(alt['xpts_season'].sum() + a_capt) - (factor['xpts_season'].sum() + f_capt):+.1f} "
          f"projected points; the two share {len(shared)} of 11")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--listing", default=HERE / "data" / "2026-27" / "player_listing.csv")
    ap.add_argument("--history", default=HERE / "data" / "2025-26")
    ap.add_argument("--objective", choices=("stars", "points"), default="stars",
                    help="how to choose the factor squad (default: stars)")
    ap.add_argument("--bench-weight", type=float, default=BENCH_WEIGHT,
                    help="worth of a bench place vs a starting one, for "
                         "--objective points (default: %(default)s)")
    ap.add_argument("--bench-fwd-max", type=float, default=BENCH_FWD_MAX_PRICE,
                    help="most a BENCHED forward may cost; anything dearer "
                         "must start (default: %(default)s). Pass a large "
                         "number to drop the cap.")
    ap.add_argument("--no-compare", action="store_true",
                    help="skip the star-vs-points comparison")
    ap.add_argument("--eleven", metavar="FORMATION", nargs="?", const="4-5-1",
                    help="build a bench-free starting XI at this formation "
                         "(e.g. 4-5-1) instead of a 15-man squad")
    ap.add_argument("--xi-budget", type=float, default=86.5,
                    help="budget for --eleven (default: %(default)s)")
    args = ap.parse_args()

    if args.eleven:
        report_eleven(args.listing, args.history, args.xi_budget,
                      args.eleven, objective=args.objective)
        return

    factor, crowd = build(args.listing, args.history,
                          objective=args.objective,
                          bench_weight=args.bench_weight,
                          bench_fwd_max=args.bench_fwd_max)
    f = factor.copy()
    f["show"] = [f"{int(s)}★ {l:<6} xP/90 {x:.2f}  owned {o:>5.1f}%"
                 for s, l, x, o in zip(f["stars"], f["factor_letters"],
                                       f["xpts90"], f["owned_pct"])]
    title = ("THE FACTOR SQUAD — best total stars the rules allow"
             if args.objective == "stars" else
             "THE FACTOR SQUAD — most projected points the rules allow")
    report(f, title, "stars", "show", captain_by="xpts90")
    c = crowd.copy()
    c["show"] = [f"owned {o:>5.1f}%" for o in c["owned_pct"]]
    report(c, "THE CROWD SQUAD — the most-owned legal 15",
           "owned_pct", "show", captain_by="owned_pct")

    overlap = set(factor["name"]) & set(crowd["name"])
    print(f"\nOverlap: {len(overlap)} of 15 — "
          + (", ".join(sorted(overlap)) if overlap else "none"))

    # What the availability list cost, spelled out.
    out_list = preseason.load_unavailable(
        Path(args.listing).parent / "unavailable.csv")
    if len(out_list):
        names = ", ".join(out_list["name"])
        print(f"\nUnavailable and therefore not selectable: {names}")
        had, _ = build(args.listing, args.history,
                       respect_availability=False,
                       objective=args.objective,
                       bench_weight=args.bench_weight,
                       bench_fwd_max=args.bench_fwd_max)
        dropped = sorted(set(had["name"]) - set(factor["name"]))
        added = sorted(set(factor["name"]) - set(had["name"]))
        print(f"  without the flag the factor squad scored "
              f"{int(had['stars'].sum())} stars; with it, {int(factor['stars'].sum())}")
        if dropped:
            print(f"  out: {', '.join(dropped)}")
            print(f"  in:  {', '.join(added)}")

    if not args.no_compare:
        compare(args.listing, args.history, args.bench_weight,
                args.bench_fwd_max)


if __name__ == "__main__":
    main()
