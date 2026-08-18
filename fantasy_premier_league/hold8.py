"""An eight-gameweek hold squad: fifteen chosen to be kept, not traded.

A different problem from ``squad.py``, deliberately kept separate.

**Stars play no part here.** They saturate - 84 of a reachable 84 - so they
cannot discriminate between squads, and they carry no fixture information
at all. Over a fixed eight-week window with no transfers the quantity that
matters is points.

**Only eleven play each week, and the eleven rotates.** Projecting each
player over eight gameweeks, summing, and taking the best fifteen is the
obvious approach and it is wrong: it prices a player by his own total
rather than by what he adds to the eleven that actually starts. So squad
membership, the starting eleven in each of the eight weeks, and the captain
in each week are solved as ONE integer program:

    x[i]     player i is in the fifteen           (15 of these)
    s[i,w]   player i starts in gameweek w        (11 per week)
    c[i,w]   player i is captain in gameweek w    (1 per week)

    maximise  sum over w, i of pts[i,w] * (s[i,w] + c[i,w])
    subject to  s[i,w] <= x[i],  c[i,w] <= s[i,w],  + the squad rules

The consequence worth understanding: **fixture diversity becomes
valuable**. Two squads with identical eight-week per-player sums are not
equally good - the one whose good fixtures are spread across the eight
weeks beats the one whose good fixtures pile into the same three, because
only eleven can start in any week. A per-player sum cannot see that; the
joint solve can.

**Two of the three forwards are dead slots** at or under
``DEAD_FWD_MAX_PRICE`` and are barred from starting in every week, so
exactly one forward is ever fielded. With ten DEF/MID in the squad filling
nine outfield places that leaves 5-4-1 and 4-5-1 as the only legal shapes -
which falls out of the constraints rather than being hard-coded, because
the eleven is a free per-gameweek decision and different weeks want
different shapes.

    python hold8.py --demo
    python hold8.py --fixtures data/2026-27/fixtures.csv
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pulp

import model
import preseason

HERE = Path(__file__).parent

HOLD_GWS = 8
BUDGET = 100.0
SQUAD = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
MAX_PER_CLUB = 3
XI_SIZE = 11
XI_MIN = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}
XI_MAX = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}

# Dead forward slots: bought to be legal bodies, never started.
DEAD_FWD_MAX_PRICE = 4.5
N_DEAD_FWD = 2

# Points for turning up. The rating engine leaves these out on purpose -
# they are common to every eligible player, so they cannot separate anyone -
# but this script projects ACTUAL points over a window, where they are a
# large part of a defender's floor. They do not scale with the opponent.
APPEARANCE_POINTS = 2.0

# A ratio of ratios off a partial season will occasionally produce
# something absurd - a club with two good games against weak opposition can
# post an attack ratio near 2. Clamped so no single fixture can dominate an
# eight-week total. Set once on that reasoning; not tuned to the output.
CLAMP = (0.75, 1.30)


# --- team strength ----------------------------------------------------

def team_matches(gws: pd.DataFrame) -> pd.DataFrame:
    """One row per team per fixture: xG created, xG conceded, venue, opponent.

    xG conceded is taken as **the other side's xG in the same fixture**,
    which is what it means, rather than summing the per-player
    ``expected_goals_conceded`` column (that would count the team's figure
    once per player). Keyed on fixture id, not (team, round), because a
    double gameweek gives a team two matches in one round.
    """
    tx = (gws.groupby(["fixture", "round", "team", "was_home"])["expected_goals"]
          .sum().rename("xg").reset_index())
    sides = tx.groupby("fixture").size()
    if not (sides == 2).all():
        raise ValueError(f"{int((sides != 2).sum())} fixtures are not two-sided")
    other = tx[["fixture", "team", "xg"]].rename(
        columns={"team": "opponent", "xg": "xgc"})
    tx = tx.merge(other, on="fixture")
    tx = tx[tx["team"] != tx["opponent"]].reset_index(drop=True)
    return tx


def strengths(tm: pd.DataFrame, through_gw: int | None = None) -> dict:
    """Venue-split attack and defence ratios, each against the league mean.

    ``through_gw`` limits the evidence, so a backtest can estimate strength
    without seeing the window it is about to be scored on.
    """
    d = tm if through_gw is None else tm[tm["round"] <= through_gw]
    out = {}
    for venue in (True, False):
        v = d[d["was_home"] == venue]
        out[venue] = {
            "att": (v.groupby("team")["xg"].mean() / v["xg"].mean()).to_dict(),
            "def": (v.groupby("team")["xgc"].mean() / v["xgc"].mean()).to_dict(),
        }
    return out


def apply_promoted_prior(st: dict, history_teams: set, listing_teams: set) -> dict:
    """Give promoted clubs the mean of last season's relegated clubs.

    Leaving them absent means ``.get(team, 1.0)`` silently rates a promoted
    side exactly league-average, which is the one thing they reliably are
    not. The relegated three are the closest thing to an observed prior for
    "a club at this level" that this data contains.
    """
    promoted = sorted(listing_teams - history_teams)
    relegated = sorted(history_teams - listing_teams)
    if not promoted:
        return st, promoted, relegated
    for venue in st:
        for kind in ("att", "def"):
            vals = [st[venue][kind][t] for t in relegated
                    if t in st[venue][kind]]
            if not vals:
                continue
            prior = float(np.mean(vals))
            for t in promoted:
                st[venue][kind][t] = prior
    return st, promoted, relegated


# --- projection -------------------------------------------------------

def _clamp(x: float) -> float:
    return min(max(x, CLAMP[0]), CLAMP[1])


def base_components(rated: pd.DataFrame) -> pd.DataFrame:
    """Split each player's per-90 rate into the parts a fixture can move.

    ``xpts90`` is a shrunk estimate and does not decompose; ``xpts90_raw``
    does, exactly, into the terms below plus a remainder. The remainder is
    the goalkeeping saves term, and for the handful of players FPL has
    reclassified between seasons it also absorbs a defensive-contribution
    threshold measured under their old position. Either way it is left
    **unscaled**, which is the conservative choice.
    """
    out = rated.copy()
    attack, defence = [], []
    for r in out.itertuples():
        attack.append(r.xg90 * model.GOAL_POINTS[r.position]
                      + r.xa90 * model.ASSIST_POINTS)
        d = (math.exp(-r.xgc90) * model.CLEAN_SHEET_POINTS[r.position]
             - r.xgc90 * model.CONCEDE_PENALTY_PER_GOAL[r.position])
        defence.append(d)
    out["base_attack"] = attack
    out["base_defence"] = defence
    # whatever is left of the raw rate: saves, defensive contributions, and
    # for a reclassified player the DC threshold measured under his old
    # position. None of it scales with the opponent.
    out["base_flat"] = (out["xpts90_raw"] - out["base_attack"]
                        - out["base_defence"])
    # shrinkage is a level effect on the whole rate; carry it as a delta so
    # the fixture adjustment can be applied without dividing by a raw value
    # that may be near zero
    out["shrink_delta"] = out["xpts90"] - out["xpts90_raw"]
    return out


def project_gameweeks(rated: pd.DataFrame, fixtures: pd.DataFrame,
                      st: dict, adjust: bool = True) -> pd.DataFrame:
    """Projected points per player per gameweek: a (players x weeks) frame.

    Component-wise, as the fixture layer only touches some of it:

    * appearance points do not scale - a player is paid for turning up
      whatever the opponent is;
    * attacking output scales with how much the opponent concedes;
    * clean sheet and goals-conceded scale with how much the opponent
      creates, applied to ``xgc90`` before the Poisson zero rather than to
      the clean-sheet points afterwards, so the two stay consistent;
    * saves and defensive contributions do not scale.

    A blank gameweek is zero points, a double is two fixtures added.
    """
    b = base_components(rated)
    weeks = sorted(fixtures["round"].unique())
    by_team = {t: g for t, g in fixtures.groupby("team")}
    out = pd.DataFrame(0.0, index=b.index, columns=weeks)

    for r in b.itertuples():
        games = by_team.get(r.team)
        if games is None:
            continue
        for f in games.itertuples():
            if adjust:
                opp_venue = not f.was_home
                m_att = _clamp(st[opp_venue]["def"].get(f.opponent, 1.0))
                m_def = _clamp(st[opp_venue]["att"].get(f.opponent, 1.0))
            else:
                m_att = m_def = 1.0
            xgc = r.xgc90 * m_def
            defence = (math.exp(-xgc) * model.CLEAN_SHEET_POINTS[r.position]
                       - xgc * model.CONCEDE_PENALTY_PER_GOAL[r.position])
            raw = r.base_attack * m_att + defence + r.base_flat
            per90 = raw + r.shrink_delta
            out.at[r.Index, f.round] += (
                per90 * r.minutes_share
                + APPEARANCE_POINTS * r.minutes_share)
    return out


def dead_forwards(candidates: pd.DataFrame, cap: float = DEAD_FWD_MAX_PRICE,
                  n_needed: int = N_DEAD_FWD) -> pd.DataFrame:
    """Cheap forwards to fill the compulsory slots that never start.

    Same idea as ``squad.bench_fodder``, extended from one such forward to
    two, and applied here to whichever pool the caller could not rate: the
    board has almost no rateable forward this cheap, because being that
    cheap and being a regular are close to mutually exclusive. They enter
    at **zero** on every scoring column, which is honest - the projection
    knows nothing about them - and harmless, because they are barred from
    starting in every week.
    """
    f = candidates[(candidates["position"] == "FWD")
                   & (candidates["price"] <= cap)].copy()
    if "unavailable" in f:
        f = f[~f["unavailable"].fillna(False)]
    if len(f) < n_needed:
        raise ValueError(
            f"only {len(f)} forwards at £{cap:.1f}m or less; need {n_needed}")
    for col in ("xg90", "xa90", "xgc90", "dc_rate", "minutes_share",
                "xpts90", "xpts90_raw", "stars"):
        f[col] = 0.0
    f["dead"] = True
    return f


def load_fixtures(path: str | Path, first_gw: int, n_gws: int) -> pd.DataFrame:
    """Read a cached fixture list into team/round/opponent/was_home rows.

    Expects the columns ``fetch_data.fetch_fixtures`` writes: ``event``,
    ``team_h``, ``team_a``. One source row becomes two, one per side. Blank
    and double gameweeks need no special handling - a club with no fixture
    in a round simply has no row, and one with two has two.
    """
    fx = pd.read_csv(path)
    missing = {"event", "team_h", "team_a"} - set(fx.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    fx = fx[fx["event"].between(first_gw, first_gw + n_gws - 1)]
    home = fx.rename(columns={"event": "round", "team_h": "team",
                              "team_a": "opponent"})[["round", "team", "opponent"]]
    home["was_home"] = True
    away = fx.rename(columns={"event": "round", "team_a": "team",
                              "team_h": "opponent"})[["round", "team", "opponent"]]
    away["was_home"] = False
    return pd.concat([home, away], ignore_index=True)


# --- the joint hold problem -------------------------------------------

def dead_slots(pool: pd.DataFrame) -> set:
    """Every forward at or under the cap: a dead slot **by price**.

    Defining these by price rather than by which pool a player arrived in
    is the whole point. A cheap forward the board happens to rate is still
    a cheap forward; if he were allowed to start, two forwards could be
    fielded and the squad would quietly stop being the shape that was
    asked for.
    """
    return set(pool.index[(pool["position"] == "FWD")
                          & (pool["price"] <= DEAD_FWD_MAX_PRICE)])


def pick_hold(pool: pd.DataFrame, pts: pd.DataFrame,
              budget: float = BUDGET) -> tuple:
    """Solve squad, per-week eleven and per-week captain together.

    Forwards at or under ``DEAD_FWD_MAX_PRICE`` are bought (exactly
    ``N_DEAD_FWD`` of them) and barred from starting in every week, so
    exactly one forward is ever fielded.
    """
    dead = dead_slots(pool)
    weeks = list(pts.columns)
    prob = pulp.LpProblem("hold", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in pool.index}
    s = {(i, w): pulp.LpVariable(f"s_{i}_{w}", cat="Binary")
         for i in pool.index for w in weeks}
    # The captain is continuous on purpose: with sum(c)=1 and c <= s the
    # optimum sits on a vertex anyway, so this is exact and halves the
    # binaries.
    c = {(i, w): pulp.LpVariable(f"c_{i}_{w}", lowBound=0, upBound=1)
         for i in pool.index for w in weeks}

    prob += pulp.lpSum(pts.at[i, w] * (s[i, w] + c[i, w])
                       for i in pool.index for w in weeks)

    prob += pulp.lpSum(x[i] for i in pool.index) == sum(SQUAD.values())
    prob += pulp.lpSum(pool.at[i, "price"] * x[i] for i in pool.index) <= budget
    for pos, n in SQUAD.items():
        members = [i for i in pool.index if pool.at[i, "position"] == pos]
        prob += pulp.lpSum(x[i] for i in members) == n
    for club in pool["team"].unique():
        members = [i for i in pool.index if pool.at[i, "team"] == club]
        prob += pulp.lpSum(x[i] for i in members) <= MAX_PER_CLUB
    # exactly N_DEAD_FWD of the three forwards are cheap dead slots
    prob += pulp.lpSum(x[i] for i in dead) == N_DEAD_FWD

    for w in weeks:
        prob += pulp.lpSum(s[i, w] for i in pool.index) == XI_SIZE
        prob += pulp.lpSum(c[i, w] for i in pool.index) == 1
        for pos in SQUAD:
            members = [i for i in pool.index if pool.at[i, "position"] == pos]
            prob += pulp.lpSum(s[i, w] for i in members) <= XI_MAX[pos]
            prob += pulp.lpSum(s[i, w] for i in members) >= XI_MIN[pos]
        for i in pool.index:
            prob += s[i, w] <= x[i]
            prob += c[i, w] <= s[i, w]
            if i in dead:
                prob += s[i, w] == 0

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(f"no optimal hold squad: {pulp.LpStatus[status]}")

    chosen = [i for i in pool.index if x[i].value() > 0.5]
    squad = pool.loc[chosen].copy()
    starts = pd.DataFrame(
        {w: [s[i, w].value() > 0.5 for i in chosen] for w in weeks},
        index=chosen)
    capt = {w: max(chosen, key=lambda i: (c[i, w].value() or 0)) for w in weeks}
    started = set(starts.index[starts.any(axis=1)])
    assert not (started & dead), "a capped forward started a week"
    for w in weeks:
        on = starts.index[starts[w]]
        n_fwd = sum(1 for i in on if pool.at[i, "position"] == "FWD")
        assert n_fwd == 1, f"GW{w} fielded {n_fwd} forwards, expected 1"
    return squad, starts, capt


def hold_total(squad, starts, capt, pts) -> float:
    """Projected points over the window: the eleven each week, captain doubled."""
    total = 0.0
    for w in pts.columns:
        on = starts.index[starts[w]]
        total += pts.loc[on, w].sum() + pts.at[capt[w], w]
    return total


def best_total_without(pool, pts, dead, squad, missing) -> float:
    """Window total if ``missing`` sits out the whole hold, with no transfer.

    The dead forwards ARE allowed to start here, unlike in the optimisation.
    Being barred from the eleven is a strategy, not a rule - they are in the
    squad and can legally be fielded - and when the one real forward is the
    man missing, fielding a £4.2m body is exactly what actually happens.
    Barring them instead would make the eleven unfillable and report the
    damage as undefined, which hides the largest exposure in the squad
    behind a blank.
    """
    p = pts.copy()
    p.loc[missing] = 0.0
    kept = list(squad.index)
    avail = [i for i in kept if i != missing]
    return sum(_best_xi(pool.loc[kept], p[w], avail) for w in p.columns)


def _best_xi(squad: pd.DataFrame, week_pts: pd.Series, avail: list) -> float:
    """Best legal eleven (captain doubled) from ``avail`` within ``squad``."""
    prob = pulp.LpProblem("xi", pulp.LpMaximize)
    y = {i: pulp.LpVariable(f"y_{i}", cat="Binary") for i in avail}
    cc = {i: pulp.LpVariable(f"c_{i}", lowBound=0, upBound=1) for i in avail}
    prob += pulp.lpSum(week_pts[i] * (y[i] + cc[i]) for i in avail)
    prob += pulp.lpSum(y[i] for i in avail) == XI_SIZE
    prob += pulp.lpSum(cc[i] for i in avail) == 1
    for i in avail:
        prob += cc[i] <= y[i]
    for pos in SQUAD:
        members = [i for i in avail if squad.at[i, "position"] == pos]
        prob += pulp.lpSum(y[i] for i in members) <= XI_MAX[pos]
        prob += pulp.lpSum(y[i] for i in members) >= XI_MIN[pos]
    if pulp.LpStatus[prob.solve(pulp.PULP_CBC_CMD(msg=0))] != "Optimal":
        return float("nan")     # cannot field a legal eleven at all
    return pulp.value(prob.objective)


# --- reporting --------------------------------------------------------

def shape_of(squad: pd.DataFrame, on: list) -> str:
    return "-".join(str(sum(1 for i in on if squad.at[i, "position"] == p))
                    for p in ("DEF", "MID", "FWD"))


def report(pool, squad, starts, capt, pts, pts_plain, dead, notes) -> None:
    weeks = list(pts.columns)
    total = hold_total(squad, starts, capt, pts)
    plain = hold_total(squad, starts, capt, pts_plain)

    print("\n" + "=" * 72)
    print(f"EIGHT-GAMEWEEK HOLD SQUAD — GW{weeks[0]}–GW{weeks[-1]}, no transfers")
    print("=" * 72)
    for line in notes:
        print(f"  {line}")
    print(f"\n  spend £{squad['price'].sum():.1f}m of £{BUDGET:.0f}m"
          f"   ({len(squad)} players, one eleven per week)")
    print(f"  projected {total:.1f} points over the window "
          f"(captain doubled each week)")
    print(f"  of which the fixture adjustment moves {total - plain:+.1f} "
          f"({abs(total - plain) / plain:.1%} of the {plain:.1f} base-rate "
          f"projection)")

    print(f"\n  THE FIFTEEN")
    order = squad.assign(_p=pd.Categorical(squad["position"],
                                           ["GK", "DEF", "MID", "FWD"]))
    order = order.sort_values(["_p", "price"], ascending=[True, False])
    for i, r in order.iterrows():
        n_start = int(starts.loc[i].sum())
        tag = "DEAD SLOT — never starts" if i in dead else f"starts {n_start}/8"
        print(f"     {r['position']:4} {r['name'][:26]:27} {r['team'][:14]:15} "
              f"£{r['price']:>4.1f}m  {tag:<24} "
              f"mins {r['minutes_share']:.0%}")

    print(f"\n  1. THE ELEVEN, WEEK BY WEEK")
    print(f"     {'GW':>3} {'shape':>6} {'proj':>7}  captain")
    for w in weeks:
        on = list(starts.index[starts[w]])
        wk = pts.loc[on, w].sum() + pts.at[capt[w], w]
        print(f"     {w:>3} {shape_of(squad, on):>6} {wk:>7.1f}  "
              f"{squad.at[capt[w], 'name']}")

    print(f"\n  2. SHAPE AND ROTATION")
    shapes = pd.Series([shape_of(squad, list(starts.index[starts[w]]))
                        for w in weeks]).value_counts()
    print("     " + ", ".join(f"{k} in {v} of 8" for k, v in shapes.items()))
    rot = starts[starts.sum(axis=1).between(1, len(weeks) - 1)]
    if len(rot):
        print("     rotates:")
        for i, row in rot.iterrows():
            wks = ", ".join(str(w) for w in weeks if row[w])
            print(f"       {squad.at[i, 'name'][:26]:27} "
                  f"{int(row.sum())}/8  (GW {wks})")
    else:
        print("     nobody rotates — the same eleven starts all eight weeks")

    print(f"\n  3. DROP-ONE ROBUSTNESS "
          f"(player misses the whole window, no replacement)")
    regulars = [i for i in starts.index if starts.loc[i].sum() >= 1]
    dmg = []
    for i in regulars:
        t = best_total_without(pool, pts, dead, squad, i)
        dmg.append((squad.at[i, "name"], squad.at[i, "position"],
                    squad.at[i, "price"], total - t))
    dmg.sort(key=lambda t: -t[3])
    print(f"     {'player':<27}{'pos':<5}{'price':>7}{'damage':>9}")
    for name, pos, price, d in dmg:
        print(f"     {name[:26]:<27}{pos:<5}{price:>6.1f}m{d:>9.1f}")

    print(f"\n  4. REAL BENCH DEPTH")
    never = [i for i in squad.index if starts.loc[i].sum() == 0]
    print(f"     Four players sit out each week, but that is not four of "
          f"cover.")
    print(f"     {len(dead)} of the fifteen NEVER start — the capped "
          f"forwards, worth ~0 points")
    print(f"     and no autosub value. The other "
          f"{len(squad) - len(dead)} all start at least one week,")
    print(f"     so the remaining two bench places each week are filled by "
          f"rotation,")
    print(f"     not by dedicated cover. **Usable cover for an injury: "
          f"{len(never) - len(dead)}.**")
    if len(never) - len(dead) > 0:
        for i in never:
            if i not in dead:
                print(f"       {squad.at[i, 'position']:4} "
                      f"{squad.at[i, 'name'][:26]:27} "
                      f"£{squad.at[i, 'price']:.1f}m")

    print(f"\n  5. MINUTES FLOOR (a rotation risk cannot be traded out)")
    live = squad[~squad.index.isin(dead)]
    lo = live.nsmallest(3, "minutes_share")
    for _, r in lo.iterrows():
        print(f"     {r['name'][:26]:27} {r['position']:4} "
              f"minutes share {r['minutes_share']:.0%}")

    print(f"\n  TWO THINGS TO WEIGH, NOT FIXED HERE")
    fwd = [i for i in squad.index if squad.at[i, "position"] == "FWD"
           and i not in dead]
    if fwd:
        i = fwd[0]
        d = next((x[3] for x in dmg if x[0] == squad.at[i, "name"]), float("nan"))
        pc = squad.at[i, "price"] / BUDGET
        print(f"     * ALL forward output sits on {squad.at[i, 'name']} "
              f"(£{squad.at[i, 'price']:.1f}m, {pc:.0%} of the budget) for "
              f"eight weeks")
        print(f"       with no cover. Losing him costs {d:.1f} projected "
              f"points — the largest")
        print(f"       single-player exposure in the squad. That is the "
              f"requested shape, not a fault.")
    waste = sum(squad.at[i, "price"] for i in dead)
    print(f"     * £{waste:.1f}m is deliberate waste — {len(dead)} forwards "
          f"bought to be legal bodies.")
    print(f"       That buys a stronger eleven and costs all autosub value "
          f"from two of")
    print(f"       the four bench slots. £{squad['price'].sum() - waste:.1f}m "
          f"is doing actual work.")


# --- assembly ---------------------------------------------------------

def build_demo(history: str | Path, through_gw: int):
    """A real no-lookahead hold: rate on GW1..through, hold the next eight.

    The 2026/27 answer needs 2026/27 fixtures, which the FPL API has not
    given up in this environment. This exercises the whole machine on data
    the repo already has, with strengths estimated only from rounds at or
    before ``through_gw``.
    """
    gws = model.load_season(history)
    rated = model.rate_players(model.player_table(gws, through_gw=through_gw))
    live = rated[rated["eligible"]].copy()
    live["dead"] = False
    fodder = dead_forwards(rated[~rated["eligible"]])
    pool = pd.concat([live, fodder])
    pool = pool[~pool.index.duplicated()]

    tm = team_matches(gws)
    st = strengths(tm, through_gw=through_gw)
    window = range(through_gw + 1, through_gw + 1 + HOLD_GWS)
    fx = tm[tm["round"].isin(window)][["team", "round", "opponent", "was_home"]]
    notes = [
        f"demo mode: rated on GW1–{through_gw}, held over "
        f"GW{through_gw + 1}–{through_gw + HOLD_GWS} of the same season",
        "team strengths use only rounds at or before the rating cut-off, so "
        "nothing here peeks",
        "all twenty clubs have a record, so no promoted-club prior is needed",
    ]
    return pool, fx, st, notes


def build_preseason(listing, history, fixtures_path, first_gw: int):
    """The real thing: new-season prices, last season's rates, real fixtures."""
    rated, unrated = preseason.rate_preseason(listing, history)
    live = rated[rated["eligible"] & ~rated["unavailable"]].copy()
    live["dead"] = False
    fodder = dead_forwards(unrated)
    pool = pd.concat([live, fodder])
    pool = pool[~pool.index.duplicated()]

    gws = model.load_season(history)
    tm = team_matches(gws)
    st = strengths(tm)
    st, promoted, relegated = apply_promoted_prior(
        st, set(tm["team"].unique()), set(pool["team"].unique()))
    fx = load_fixtures(fixtures_path, first_gw, HOLD_GWS)
    notes = [
        f"rated on {Path(history).name}, priced from {Path(listing).name}",
        f"promoted clubs ({', '.join(promoted)}) carry the mean of the "
        f"relegated three ({', '.join(relegated)}) —",
        "  they are NOT left at the league mean, which would silently rate "
        "them average",
    ]
    return pool, fx, st, notes


def validate(history, first_origin: int = 10, last_origin: int = 30,
             seed: int = 0) -> None:
    """Does the fixture adjustment predict better than the plain rate?

    The gate this script had to pass before being worth writing. Uses
    ``project_gameweeks`` itself rather than a parallel implementation, so
    what is measured is what ships.

    Strictly out-of-sample where it matters: strengths come from rounds at
    or before the origin and are scored against actual points in the eight
    that follow. The FIXTURE LIST for those weeks is not lookahead - the
    schedule is published a season ahead - but the strengths would be.
    """
    gws = model.load_season(history)
    tm = team_matches(gws)
    rows = []
    for G in range(first_origin, last_origin + 1):
        rated = model.rate_players(model.player_table(gws, through_gw=G))
        rated = rated[rated["eligible"]].copy()
        window = range(G + 1, G + 1 + HOLD_GWS)
        fx = tm[tm["round"].isin(window)][
            ["team", "round", "opponent", "was_home"]]
        st = strengths(tm, through_gw=G)
        # join on the element COLUMN: rate_players is not indexed by
        # element, and its positional index overlaps element ids almost
        # perfectly, so an index join silently scores the wrong players
        actual = (gws[gws["round"].isin(window)]
                  .groupby("element")["total_points"].sum())
        truth = rated["element"].map(actual).fillna(0.0)

        adj = project_gameweeks(rated, fx, st, adjust=True).sum(axis=1)
        plain = project_gameweeks(rated, fx, st, adjust=False).sum(axis=1)
        rho = lambda a: a.rank().corr(truth.rank())
        rows.append({"G": G, "n": len(rated),
                     "plain": rho(plain), "adj": rho(adj)})

    r = pd.DataFrame(rows)
    r["diff"] = r["adj"] - r["plain"]
    print(f"FIXTURE-ADJUSTMENT VALIDATION — origins GW{first_origin}"
          f"-{last_origin}, {HOLD_GWS}-week windows")
    print(f"  target: actual points in the eight weeks after each origin\n")
    print(r.round(4).to_string(index=False))

    d = r["diff"].to_numpy()
    # Windows overlap - an origin at G shares seven of its eight weeks with
    # G+1 - so an iid interval is far too narrow. Moving-block bootstrap,
    # block length = the window, which is the standard fix.
    rng = np.random.default_rng(seed)
    n, L = len(d), HOLD_GWS
    starts_ = np.arange(n - L + 1)
    boot = np.array([
        np.concatenate([d[s:s + L] for s in
                        rng.choice(starts_, size=int(np.ceil(n / L)))])[:n].mean()
        for _ in range(10000)])
    lo, hi = np.percentile(boot, [2.5, 97.5])
    print(f"\n  mean spearman: plain {r['plain'].mean():.4f}   "
          f"adjusted {r['adj'].mean():.4f}")
    print(f"  paired difference {d.mean():+.4f}, wins {int((d > 0).sum())}"
          f"/{n} origins")
    print(f"  moving-block bootstrap 95% CI [{lo:+.4f}, {hi:+.4f}]  "
          f"P(>0) = {(boot > 0).mean():.3f}")
    early = r[r["G"] <= first_origin + 9]["diff"]
    late = r[r["G"] >= last_origin - 6]["diff"]
    print(f"\n  early origins {early.mean():+.4f} "
          f"({int((early > 0).sum())}/{len(early)} positive), "
          f"late origins {late.mean():+.4f} "
          f"({int((late > 0).sum())}/{len(late)} positive)")
    print(f"  => the adjustment helps most when the base rate is least "
          f"settled, which\n     is the regime a GW1-8 hold is in - though "
          f"more extremely than anything\n     testable here, since GW1 has "
          f"no current-season evidence at all.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--history", default=HERE / "data" / "2025-26")
    ap.add_argument("--listing",
                    default=HERE / "data" / "2026-27" / "player_listing.csv")
    ap.add_argument("--fixtures",
                    default=HERE / "data" / "2026-27" / "fixtures.csv")
    ap.add_argument("--first-gw", type=int, default=1)
    ap.add_argument("--demo", action="store_true",
                    help="rate on GW1-30 of the history season and hold "
                         "GW31-38 of it — a real no-lookahead window, for "
                         "when next season's fixtures are not available")
    ap.add_argument("--through-gw", type=int, default=30,
                    help="rating cut-off for --demo (default: %(default)s)")
    ap.add_argument("--validate", action="store_true",
                    help="run the fixture-adjustment backtest and stop")
    args = ap.parse_args()

    if args.validate:
        validate(args.history)
        return

    if args.demo:
        pool, fx, st, notes = build_demo(args.history, args.through_gw)
    else:
        if not Path(args.fixtures).exists():
            raise SystemExit(
                f"no fixture list at {args.fixtures}.\n"
                "Run `python fetch_data.py --fixtures` to cache it from the "
                "FPL API, or pass --demo to run the machine on a window of "
                "the history season instead.")
        pool, fx, st, notes = build_preseason(
            args.listing, args.history, args.fixtures, args.first_gw)

    pts = project_gameweeks(pool, fx, st, adjust=True)
    pts_plain = project_gameweeks(pool, fx, st, adjust=False)
    squad, starts, capt = pick_hold(pool, pts)
    dead = dead_slots(pool) & set(squad.index)
    report(pool, squad, starts, capt, pts, pts_plain, dead, notes)


if __name__ == "__main__":
    main()
