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

    python squad.py
    python squad.py --objective points
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


def projected_points(df: pd.DataFrame) -> pd.Series:
    """Projected season points: xPts/90 x expected minutes / 90.

    Backward-looking - ``minutes_share`` is last season's - so it is a
    working proxy for comparing squads, not a forecast of 2026/27.
    """
    return df["xpts90"] * df["minutes_share"] * SEASON_GWS


def _solve(pool: pd.DataFrame, objective: pd.Series, budget: float | None,
           shape: dict, total: int, min_shape: dict | None = None,
           max_per_club: int | None = MAX_PER_CLUB,
           equality: bool = True) -> list:
    """Maximise ``objective`` subject to the squad rules. Returns row labels."""
    prob = pulp.LpProblem("squad", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in pool.index}

    prob += pulp.lpSum(objective[i] * x[i] for i in pool.index)
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


def pick_squad(pool: pd.DataFrame, primary: str, secondary: str | None = None,
               budget: float = BUDGET) -> pd.DataFrame:
    """Best legal 15 on ``primary``; ties broken on ``secondary``.

    Solved lexicographically - the secondary objective is optimised only
    over squads that already achieve the best possible primary total, so a
    tie-break can never cost a star.
    """
    chosen = _solve(pool, pool[primary], budget, SQUAD, sum(SQUAD.values()))
    if secondary is None:
        return pool.loc[chosen]

    best = float(pool.loc[chosen, primary].sum())
    prob = pulp.LpProblem("squad2", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in pool.index}
    prob += pulp.lpSum(pool.at[i, secondary] * x[i] for i in pool.index)
    prob += pulp.lpSum(x[i] for i in pool.index) == sum(SQUAD.values())
    prob += pulp.lpSum(pool.at[i, "price"] * x[i] for i in pool.index) <= budget
    prob += pulp.lpSum(pool.at[i, primary] * x[i] for i in pool.index) >= best
    for pos, n in SQUAD.items():
        members = [i for i in pool.index if pool.at[i, "position"] == pos]
        prob += pulp.lpSum(x[i] for i in members) == n
    for club in pool["team"].unique():
        members = [i for i in pool.index if pool.at[i, "team"] == club]
        prob += pulp.lpSum(x[i] for i in members) <= MAX_PER_CLUB
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    return pool.loc[[i for i in pool.index if x[i].value() > 0.5]]


def pick_squad_points(pool: pd.DataFrame, col: str = "xpts_season",
                      bench_weight: float = BENCH_WEIGHT,
                      captain: bool = True,
                      budget: float = BUDGET) -> pd.DataFrame:
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

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(f"no optimal squad found: {pulp.LpStatus[status]}")
    chosen = [i for i in pool.index if x[i].value() > 0.5]
    out = pool.loc[chosen].copy()
    out["xi"] = [y[i].value() > 0.5 for i in chosen]
    out["capt"] = [c[i].value() > 0.5 for i in chosen]
    return out


def pick_xi(squad: pd.DataFrame, objective: str) -> pd.DataFrame:
    """The best legal starting XI out of the 15."""
    # The 15 are already paid for, so the XI has no budget of its own.
    chosen = _solve(squad, squad[objective], budget=None,
                    shape=XI_MAX, total=XI_SIZE, min_shape=XI_MIN,
                    max_per_club=None, equality=False)
    return squad.loc[chosen]


def build(listing: str | Path, history: str | Path,
          respect_availability: bool = True, objective: str = "stars",
          bench_weight: float = BENCH_WEIGHT):
    """Return (factor_squad, crowd_squad), each with an ``xi`` flag.

    ``objective`` picks how the factor squad is chosen:

    * ``"stars"`` (default) - most total stars over the 15, ties broken on
      the quality engine. This is the board's own answer, and the one every
      argument in the README is built on.
    * ``"points"`` - most projected points, bench discounted by
      ``bench_weight`` and the captain doubled, all solved jointly.

    The crowd squad is unaffected either way: it is chosen on ownership.

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

    if objective == "stars":
        factor = pick_squad(board, "stars", "xpts90").copy()
        # Which eleven start is decided on projected points, not on stars.
        # Stars are a coarse ordinal, so they tie constantly and the
        # tie falls to index order, which is nobody's idea of a team
        # sheet. Same reasoning that already picks the captain on xpts90.
        factor["xi"] = factor.index.isin(
            pick_xi(factor, "xpts_season").index)
    else:
        factor = pick_squad_points(board, "xpts_season", bench_weight)

    crowd = pick_squad(everyone, "owned_pct").copy()
    # The crowd pool deliberately has no ratings - unrated players have
    # none - so its XI stays on ownership.
    crowd["xi"] = crowd.index.isin(pick_xi(crowd, "owned_pct").index)
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
    print(f"  captain {order.iloc[0]['name']}   vice {order.iloc[-1]['name']}\n")
    for _, r in _order(squad, by).iterrows():
        mark = " " if r["xi"] else "B"
        val = f"{r[extra]}" if extra else ""
        print(f"   {mark} {r['position']:4} {r['name'][:28]:29} "
              f"{r['team'][:14]:15} £{r['price']:>4.1f}m  {val}")


def compare(listing, history, bench_weight: float) -> None:
    """Star objective against points objective, same constraints."""
    squads = {o: build(listing, history, objective=o,
                       bench_weight=bench_weight)[0]
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--listing", default=HERE / "data" / "2026-27" / "player_listing.csv")
    ap.add_argument("--history", default=HERE / "data" / "2025-26")
    ap.add_argument("--objective", choices=("stars", "points"), default="stars",
                    help="how to choose the factor squad (default: stars)")
    ap.add_argument("--bench-weight", type=float, default=BENCH_WEIGHT,
                    help="worth of a bench place vs a starting one, for "
                         "--objective points (default: %(default)s)")
    ap.add_argument("--no-compare", action="store_true",
                    help="skip the star-vs-points comparison")
    args = ap.parse_args()

    factor, crowd = build(args.listing, args.history,
                          objective=args.objective,
                          bench_weight=args.bench_weight)
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
        had, _ = build(args.listing, args.history, respect_availability=False)
        dropped = sorted(set(had["name"]) - set(factor["name"]))
        added = sorted(set(factor["name"]) - set(had["name"]))
        print(f"  without the flag the factor squad scored "
              f"{int(had['stars'].sum())} stars; with it, {int(factor['stars'].sum())}")
        if dropped:
            print(f"  out: {', '.join(dropped)}")
            print(f"  in:  {', '.join(added)}")

    if not args.no_compare:
        compare(args.listing, args.history, args.bench_weight)


if __name__ == "__main__":
    main()
