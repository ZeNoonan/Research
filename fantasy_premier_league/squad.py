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

    python squad.py
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


def pick_xi(squad: pd.DataFrame, objective: str) -> pd.DataFrame:
    """The best legal starting XI out of the 15."""
    # The 15 are already paid for, so the XI has no budget of its own.
    chosen = _solve(squad, squad[objective], budget=None,
                    shape=XI_MAX, total=XI_SIZE, min_shape=XI_MIN,
                    max_per_club=None, equality=False)
    return squad.loc[chosen]


def build(listing: str | Path, history: str | Path):
    """Return (factor_squad, crowd_squad), each with an ``xi`` flag."""
    rated, unrated = preseason.rate_preseason(listing, history)
    board = rated[rated["eligible"]].copy()

    # The crowd's pool is everyone listed: ownership is known for all of
    # them, and a sixth of it sits off the rated board.
    everyone = pd.concat([
        rated[["name", "position", "team", "price", "owned_pct"]],
        unrated[["name", "position", "team", "price", "owned_pct"]],
    ], ignore_index=True)

    factor = pick_squad(board, "stars", "xpts90").copy()
    crowd = pick_squad(everyone, "owned_pct").copy()

    factor["xi"] = factor.index.isin(pick_xi(factor, "stars").index)
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--listing", default=HERE / "data" / "2026-27" / "player_listing.csv")
    ap.add_argument("--history", default=HERE / "data" / "2025-26")
    args = ap.parse_args()

    factor, crowd = build(args.listing, args.history)
    f = factor.copy()
    f["show"] = [f"{int(s)}★ {l:<5} xP/90 {x:.2f}  owned {o:>5.1f}%"
                 for s, l, x, o in zip(f["stars"], f["factor_letters"],
                                       f["xpts90"], f["owned_pct"])]
    report(f, "THE FACTOR SQUAD — best total stars the rules allow",
           "stars", "show", captain_by="xpts90")
    c = crowd.copy()
    c["show"] = [f"owned {o:>5.1f}%" for o in c["owned_pct"]]
    report(c, "THE CROWD SQUAD — the most-owned legal 15",
           "owned_pct", "show", captain_by="owned_pct")

    overlap = set(factor["name"]) & set(crowd["name"])
    print(f"\nOverlap: {len(overlap)} of 15 — "
          + (", ".join(sorted(overlap)) if overlap else "none"))


if __name__ == "__main__":
    main()
