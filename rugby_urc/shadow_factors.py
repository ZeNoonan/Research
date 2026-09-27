"""Shadow factors: nine candidate factors, tracked alongside the five but not bet.

Each casts the same kind of vote as the five in ``model.py`` - **+1** backs the
home side, **-1** the away side, **0** neither - but none of them counts
towards the System # or the picks. They are here to be tested.

The protocol, because testing nine things on one season is the easiest way
there is to find an edge that is not there:

* **The rules are fixed before any results are looked at.** Every definition,
  threshold and sign below was written down and committed before the first
  run on 2025-26, and is not tuned afterwards.
* **2025-26 is the first look; 2026-27 is the test.** A factor that votes
  ~100 times has a 95% band of roughly 40-60% with no edge at all, so on nine
  factors one or two will look good by chance. Only one that holds up on a
  season it was not chosen on is a candidate for the system.
* **Every factor is reported**, not only the ones that look good.

Groups
------
**Luck** (1-4) - the turnover factor's logic: something swung a club's last
result that does not repeat, so the next line over-reacts to it. The theory
says which side to back, so the direction is fixed from the start.

**Situational** (5-8) - whether the market prices a situation correctly. The
theory does not say which way, so each vote is written in one direction by
convention, 2025-26 decides the direction (``DIRECTION``), and 2026-27 tests
it.

**Market** (9) - needs opening lines, which only 2026-27 has. Written as
fading the move, the over-reaction reading the power factor already takes;
2026-27 is its first look.

A factor **abstains** (no vote) when it cannot be computed: the club's first
match of a run of seasons, a previous match with no stats or no line.

Run: ``python shadow_factors.py`` -> a table per season, and
``data/shadow_<year>.csv`` with every match's votes as tracked (+1 backs home).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

import match_stats
import model
import season_report
import teams

KEY = ["date", "home", "away"]

BIG_MISS = 10.0        # 1: missed / beat last match's line by this many points
TOUR_GAP_DAYS = 8      # 6: previous match abroad at most this many days before
BIG_LINE = 14.0        # 8: a handicap of at least this many points
BIG_MOVE = 2.0         # 9: the close at least this far from the open


@dataclass(frozen=True)
class Factor:
    key: str
    label: str
    group: str
    rule: str          # what a +1 vote means, as written


FACTORS = [
    Factor("last_cover", "Last result v the line", "luck",
           f"backs a side that missed its last line by {BIG_MISS:g}+ points; "
           f"fades one that beat it by {BIG_MISS:g}+"),
    Factor("cards", "Cards", "luck",
           "backs the side that had more cards than its opponent last match "
           "(yellow 1, red 2)"),
    Factor("kicking", "Goal-kicking", "luck",
           "backs the side that left more points on the tee than its opponent "
           "last match (2 per missed conversion, 3 per missed penalty)"),
    Factor("red_zone", "Scoring from the 22", "luck",
           "backs the side that scored fewer points per visit to the 22 than "
           "its opponent last match"),
    Factor("long_haul", "Long-haul trip", "situational",
           "backs the home side when the away side crosses between Europe and "
           "South Africa"),
    Factor("tour_leg2", "Second match of a tour", "situational",
           f"backs the home side when the away side's previous match was also "
           f"abroad, within {TOUR_GAP_DAYS} days"),
    Factor("derby", "Derby", "situational",
           "backs the underdog when both clubs are from the same country"),
    Factor("big_line", "Big handicap", "situational",
           f"backs the underdog when the handicap is {BIG_LINE:g}+ points"),
    Factor("line_move", "Line move", "market",
           f"backs the side the line moved against, when the close is "
           f"{BIG_MOVE:g}+ points from the open"),
]
BY_KEY = {f.key: f for f in FACTORS}

# Which way each factor is tracked: +1 as its rule is written, -1 the reverse.
# Luck factors and the line move are fixed by theory. The situational ones were
# undecided (None) until 2025-26 had been run, and were then set from it, once,
# by the rule "whichever way won more often" - so 2025-26 flatters them by
# construction, and 2026-27 is their test. Do not change these again.
#   long_haul  as written 30-23 (56.6%) -> backs home
#   tour_leg2  as written 13-10 (56.5%) -> backs home
#   derby      as written 24-14 (63.2%) -> backs the underdog
#   big_line   as written 22-24 (47.8%) -> reversed: backs the favourite
DIRECTION: dict[str, int | None] = {
    "last_cover": 1, "cards": 1, "kicking": 1, "red_zone": 1,
    "long_haul": 1, "tour_leg2": 1, "derby": 1, "big_line": -1,
    "line_move": 1,
}

# The stat pairs the luck factors read, from data/stats_<year>.csv.
STATS = ["yellow_cards", "red_cards", "missed_conversion_goals",
         "missed_penalty_goals", "points_from_visits_to22", "num_visits_to22"]


# --- assembling the matches --------------------------------------------------

def matches() -> pd.DataFrame:
    """Every reported match, all seasons, in date order, with venue and stats."""
    reports = season_report.build_reports()
    frames = []
    for year, rep in reports.items():
        venue = season_report.load_season(year)[KEY + ["neutral"]]
        venue = venue.assign(date=venue["date"].dt.strftime("%Y-%m-%d"))
        stats = match_stats.load(year)
        wanted = [f"{side}_{s}" for s in STATS for side in ("home", "away")]
        for col in wanted:
            if col not in stats.columns:
                stats[col] = np.nan
        frames.append(rep.assign(season=year)
                      .merge(venue, on=KEY, how="left")
                      .merge(stats[KEY + wanted], on=KEY, how="left"))
    if not frames:
        return pd.DataFrame()
    g = pd.concat(frames, ignore_index=True).sort_values(["date", "round", "home"])
    present = sorted(g["season"].unique())
    block, b = {}, 0
    for i, s in enumerate(present):
        if i and s != present[i - 1] + 1:
            b += 1
        block[s] = b
    g["block"] = g["season"].map(block)
    g["neutral"] = g["neutral"].fillna(False).astype(bool)
    return g.reset_index(drop=True)


def _per_club(g: pd.DataFrame) -> pd.DataFrame:
    """One row per club per match: what that match says about the club.

    Each quantity is the club's own figure minus its opponent's, so the luck
    factors compare the two sides of one match, measured the same way.
    """
    cards = {s: g[f"{s}_yellow_cards"] + 2 * g[f"{s}_red_cards"] for s in ("home", "away")}
    missed = {s: 2 * g[f"{s}_missed_conversion_goals"] + 3 * g[f"{s}_missed_penalty_goals"]
              for s in ("home", "away")}
    ppv = {s: g[f"{s}_points_from_visits_to22"]
           / g[f"{s}_num_visits_to22"].where(g[f"{s}_num_visits_to22"] > 0)
           for s in ("home", "away")}
    home_cover = (g["home_score"] - g["away_score"] + g["line"]).astype(float)
    sa = {s: g[s].isin(teams.SOUTH_AFRICAN) for s in ("home", "away")}
    venue_sa = sa["home"].where(~g["neutral"])      # neutral: venue unknown

    rows = []
    for side, other, sign in (("home", "away", 1), ("away", "home", -1)):
        rows.append(pd.DataFrame({
            "order": g.index, "block": g["block"], "date": pd.to_datetime(g["date"]),
            "team": g[side],
            "cover": sign * home_cover,
            "cards": cards[side] - cards[other],
            "missed": missed[side] - missed[other],
            "ppv": ppv[side] - ppv[other],
            "abroad": (sa[side] != venue_sa).where(venue_sa.notna()),
        }))
    return pd.concat(rows).sort_values(["team", "order"])


# --- the votes ------------------------------------------------------------------

def _match_vote(home: pd.Series, away: pd.Series) -> pd.Series:
    """Back the side the club scores favour; abstain if either is unknown."""
    vote = np.sign(home - away)
    return vote.where(home.notna() & away.notna())


def votes(g: pd.DataFrame) -> pd.DataFrame:
    """Each factor's raw vote for every match, as its rule is written.

    ``g`` is ``matches()``: one row per match, indexed in date order, which is
    what "last match" is read from.
    """
    if not pd.to_datetime(g["date"]).is_monotonic_increasing or not g.index.is_monotonic_increasing:
        raise ValueError("matches must be in date order, indexed in that order")
    club = _per_club(g)
    prev = club.groupby(["team", "block"])
    for col in ("cover", "cards", "missed", "ppv", "abroad", "date"):
        club[f"prev_{col}"] = prev[col].shift()

    # A club's score per luck factor: +1 = back it, -1 = fade it.
    pc = club["prev_cover"]
    club["s_last_cover"] = np.select([pc <= -BIG_MISS, pc >= BIG_MISS], [1.0, -1.0], 0.0)
    club["s_last_cover"] = club["s_last_cover"].where(pc.notna())
    club["s_cards"] = np.sign(club["prev_cards"])
    club["s_kicking"] = np.sign(club["prev_missed"])
    club["s_red_zone"] = -np.sign(club["prev_ppv"])
    gap = (club["date"] - club["prev_date"]).dt.days
    club["leg2"] = (club["abroad"].eq(True) & club["prev_abroad"].eq(True)
                    & (gap <= TOUR_GAP_DAYS))

    keyed = club.set_index(["order", "team"])
    side = {s: keyed.loc[list(zip(g.index, g[s]))].set_axis(g.index)
            for s in ("home", "away")}

    out = pd.DataFrame(index=g.index)
    for f in ("last_cover", "cards", "kicking", "red_zone"):
        out[f] = _match_vote(side["home"][f"s_{f}"], side["away"][f"s_{f}"])

    line = g["line"]
    underdog = np.sign(line).where(line.notna())             # +1 = home is the dog
    long_haul = pd.Series([teams.is_long_haul(h, a) for h, a in zip(g["home"], g["away"])],
                          index=g.index)
    out["long_haul"] = (long_haul & ~g["neutral"]).astype(float)
    out["tour_leg2"] = (side["away"]["leg2"] & ~g["neutral"]).astype(float)
    same_country = pd.Series([teams.TEAMS[h] == teams.TEAMS[a]
                              for h, a in zip(g["home"], g["away"])], index=g.index)
    out["derby"] = underdog.where(same_country, 0.0)
    out["big_line"] = underdog.where(line.abs() >= BIG_LINE, 0.0)
    move = line - g["opening_line"]
    out["line_move"] = np.sign(move).where(move.abs() >= BIG_MOVE, 0.0)
    return out


# --- scoring --------------------------------------------------------------------

def _record(side_won: pd.Series) -> tuple[int, int]:
    return int((side_won == 1).sum()), int((side_won == -1).sum())


def evaluate(g: pd.DataFrame, v: pd.DataFrame, year: int) -> pd.DataFrame:
    """Per factor: its own record when it votes, and the system's with it added.

    ``standalone`` is every match the factor voted on and the line settled
    (no push). ``as a 6th vote`` adds the vote to the five-factor System # and
    bets at the same +/-3, only where the system itself could bet - a line,
    ratings, and turnovers known.
    """
    in_season = g["season"] == year
    cover = pd.Series([model.cover(r.home_score, r.away_score, r.line)
                       for r in g.itertuples()], index=g.index)
    eligible = g["line"].notna() & g["home_power"].notna() & ~g["lgt_unknown"]
    rows = []
    for f in FACTORS:
        d = DIRECTION[f.key] or 1
        vote = v[f.key] * d
        voted = in_season & vote.isin([1, -1])
        settled = voted & cover.ne(0)
        w, l = _record((vote[settled] == cover[settled]).map({True: 1, False: -1}))
        total = g["system_num"] + vote.fillna(0)
        pick = np.sign(total).where(total.abs() >= model.BET_THRESHOLD, 0)
        bet = in_season & eligible & pick.ne(0) & cover.ne(0)
        bw, bl = _record((pick[bet] == cover[bet]).map({True: 1, False: -1}))
        n = w + l
        rows.append({
            "factor": f.label, "key": f.key, "group": f.group,
            "direction": ("as written" if DIRECTION[f.key] == 1
                          else "reversed" if DIRECTION[f.key] == -1 else "undecided"),
            "votes": int(voted.sum()), "W": w, "L": l,
            "rate": w / n if n else math.nan,
            "band": 1.96 * math.sqrt(0.25 / n) if n else math.nan,
            "sys_W": bw, "sys_L": bl, "sys_units": bw - 1.1 * bl,
        })
    return pd.DataFrame(rows)


def build() -> dict[int, pd.DataFrame]:
    """Every season's table, and each match's votes written to data/."""
    g = matches()
    if g.empty:
        return {}
    v = votes(g)
    # The file holds the votes as tracked - each factor's DIRECTION applied -
    # so it agrees with the tables and the site.
    tracked = v * pd.Series({k: DIRECTION[k] or 1 for k in v.columns})
    tables = {}
    for year in sorted(g["season"].unique()):
        tables[int(year)] = evaluate(g, v, year)
        keep = g["season"] == year
        (pd.concat([g.loc[keep, KEY + ["line", "system_num", "system_bet", "result"]],
                    tracked[keep].astype("Int64")], axis=1)
         .to_csv(season_report.DATA_DIR / f"shadow_{year}.csv", index=False))
    return tables


def main() -> None:
    base = {y: r for y, r in season_report.build_reports().items()}
    for year, table in build().items():
        rep = base[year]
        w, l = int((rep["result"] == "W").sum()), int((rep["result"] == "L").sum())
        print(f"\n{season_report.season_label(year)} - the five alone: {w}-{l}, "
              f"{w - 1.1 * l:+.1f}u\n")
        print(f"  {'factor':<26}{'dir':<11}{'votes':>6}{'W-L':>9}{'rate':>8}"
              f"{'±95%':>7}   {'as a 6th vote':>14}")
        for r in table.itertuples():
            rate = "-" if math.isnan(r.rate) else f"{r.rate:.1%}"
            band = "" if math.isnan(r.band) else f"{r.band:.0%}"
            print(f"  {r.factor:<26}{r.direction:<11}{r.votes:>6}{f'{r.W}-{r.L}':>9}"
                  f"{rate:>8}{band:>7}   {f'{r.sys_W}-{r.sys_L}':>7} {r.sys_units:+6.1f}u")


if __name__ == "__main__":
    main()
