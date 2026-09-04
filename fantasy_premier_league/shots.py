"""Shots, expected goals and expected assists, gameweek by gameweek.

Neither source has all three numbers, so the board is built from both:

* **fbref** (``data/2026-27/fbref_shots.xlsx``) has **shots** and
  **penalties attempted**. One sheet per gameweek — ``GW1``, ``GW2``, … —
  and each sheet is **cumulative to the end of that gameweek**. A single
  gameweek is therefore the sheet *minus* its predecessor; GW1 is itself.
  Add a sheet as the season goes on and it is picked up automatically.
* **FPL** (``data/2026-27/all_gws.csv``, written by ``scraper_fpl.py``) has
  **expected goals**, **expected assists** and **minutes**, already one row
  per player per gameweek.

Penalties
---------
FPL's expected goals include the penalty itself, at roughly 0.79 xG a
kick. A penalty says something about the taker's job, not much about his
shooting, and it swamps the week's open-play number: one spot kick outranks
four good chances. So every attempt fbref records costs the taker
**0.75 xG** in the week he took it, and the board ranks on what is left.
The subtraction is done on the **weekly** attempt count, so a penalty is
charged once, in its own gameweek. See ``PENALTY_XG``.

The join
--------
fbref writes display names (``Bruno Fernandes``); FPL writes
``first_second`` lowercased (``bruno_borges fernandes``). ``match_rows``
normalises both, then assigns **one-to-one**, best-scoring pair first:
exact token match, one name a subset of the other, shared surname. A club
agreeing adds to the score but is not required — FPL reports a player's
**current** club, so a deadline-day move disagrees with the club he
actually played for.

What is left over is settled on **minutes**: fbref's ``90s`` times 90
against FPL's minutes, at the same club, accepted only when exactly one
unclaimed candidate is within ``MINUTES_TOL``. That is what catches the
nicknames no amount of string matching will — fbref's *Beto* is FPL's
*norberto bercique gomes betuncal*, its *Costinha* is *joão pedro loureiro
da costa*.

Minutes then **audit** every pair, nickname or not: two independent
sources agreeing to the minute on 360 of 364 players is what says the join
is right, and ``report_join`` prints any pair they disagree on.

Ranking
-------
Within a gameweek, over the players who **actually played**, each of shots,
adjusted xG and xA is ranked with 1 best and ties sharing the mean rank.
The three ranks are summed, and the sum re-ranked 1..N: that integer is the
player's gameweek rank, and it is what the board shows.

A player who did not play is **blank** — not last, and not zero. But a
column of blanks cannot be summed honestly, because missing a gameweek
would then *improve* a player's total. So the season total charges a missed
gameweek that week's **last place**, and the average beside it is taken
over the gameweeks he played. The two columns answer different questions:
the total asks who has been most useful so far, the average asks who is
best when he plays.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from preseason import display_name, normalise

HERE = Path(__file__).parent

# One penalty kick is worth this much expected goal. Subtracted from the
# taker's weekly xG, once per attempt. The user's number, and close to the
# ~0.79 conversion rate the xG models themselves use for a spot kick.
PENALTY_XG = 0.75

# How far fbref's minutes (90s x 90, so quantised to 9-minute steps) may sit
# from FPL's before a pair is called a disagreement. Nine covers the
# rounding; the two sources also differ on whether stoppage time counts.
MINUTES_TOL = 10

# fbref's club names against FPL's. Only the ones that differ.
SQUAD_ALIASES = {
    "Leeds United": "Leeds",
    "Manchester City": "Man City",
    "Manchester Utd": "Man Utd",
    "Nottingham": "Nott'm Forest",
    "Tottenham": "Spurs",
}

CATEGORIES = ("shots", "xg", "xa")
# The defcon board's four: the same attacking three, plus the defensive
# work, over defenders and midfielders only.
DEFCON_CATEGORIES = ("shots", "xg", "xa", "dc")
DEFCON_POSITIONS = ("DF", "MD")
CATEGORY_NAMES = {"shots": "Shots", "xg": "xG (pen-adj)", "xa": "xA",
                  "dc": "Defensive contributions"}

# Qualifying defensive actions needed for FPL's 2-point defensive
# contribution award. A defender's tally is clearances + blocks +
# interceptions + tackles; a midfielder's adds recoveries and needs two
# more of them. Verified against the dump: every DF row equals CBI +
# tackles, every MD and FW row equals that plus recoveries, every GK is 0.
DC_THRESHOLD = {"DF": 10, "MD": 12, "FW": 12}


# --- loading -----------------------------------------------------------------

def gameweek_sheets(path: str | Path) -> list[tuple[int, str]]:
    """Return the workbook's ``GW<n>`` sheets as (gameweek, sheet name).

    Sorted by gameweek, so adding ``GW3`` next week needs no code change.
    Any other sheet is ignored rather than guessed at.
    """
    sheets = pd.ExcelFile(path).sheet_names
    out = []
    for name in sheets:
        m = re.fullmatch(r"\s*GW\s*(\d+)\s*", str(name), re.I)
        if m:
            out.append((int(m.group(1)), name))
    if not out:
        raise ValueError(f"{path} has no GW<n> sheets, only {sheets}")
    return sorted(out)


def load_fbref(path: str | Path) -> pd.DataFrame:
    """Read the cumulative sheets and difference them into weekly rows.

    Returns one row per (player, gameweek) with ``shots``, ``pkatt``,
    ``goals`` and ``fb_minutes`` for **that gameweek alone**. Players are
    keyed on (Player, Squad); the sheet's own ``Week`` column is ignored —
    it holds a row rank, not a gameweek.
    """
    frames = {}
    for gw, sheet in gameweek_sheets(path):
        d = pd.read_excel(path, sheet_name=sheet)
        d = d[["Player", "Squad", "90s", "Sh", "PKatt", "Gls"]].copy()
        d["Squad"] = d["Squad"].map(lambda s: SQUAD_ALIASES.get(s, s))
        dup = d.duplicated(["Player", "Squad"])
        if dup.any():
            raise ValueError(
                f"{sheet} names the same player twice: "
                + ", ".join(d.loc[dup, "Player"]))
        frames[gw] = d.set_index(["Player", "Squad"])

    rows = []
    prev = None
    for gw in sorted(frames):
        cur = frames[gw]
        if prev is None:
            weekly = cur.copy()
        else:
            # Everyone in either sheet; absent from the earlier one means he
            # had not played yet, which is a zero, not a gap.
            weekly = cur.reindex(cur.index.union(prev.index)).fillna(0.0) \
                - prev.reindex(cur.index.union(prev.index)).fillna(0.0)
            shrank = weekly[weekly["Sh"] < 0]
            if len(shrank):
                raise ValueError(
                    f"GW{gw} has fewer cumulative shots than GW{gw - 1} for: "
                    + ", ".join(n for n, _ in shrank.index[:5])
                    + " — the sheets are not cumulative")
        weekly = weekly.reset_index()
        weekly["round"] = gw
        rows.append(weekly)
        prev = cur

    out = pd.concat(rows, ignore_index=True)
    out = out.rename(columns={"Sh": "shots", "PKatt": "pkatt", "Gls": "goals"})
    out["fb_minutes"] = out["90s"] * 90
    return out[["Player", "Squad", "round", "shots", "pkatt", "goals",
                "fb_minutes"]]


def load_fpl(path: str | Path) -> pd.DataFrame:
    """Read the scraper's dump: one row per player per gameweek.

    Keeps the columns the board needs and nothing else. ``team`` is the
    player's **current** club, which is not always the club he played the
    gameweek for.
    """
    d = pd.read_csv(path)
    need = {"element", "full_name", "team", "Position", "round", "minutes",
            "expected_goals", "expected_assists", "defensive_contribution"}
    missing = need - set(d.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    d = d[sorted(need)].copy()
    d["name"] = d["full_name"].str.replace("_", " ", regex=False).map(
        display_name)
    return d


# --- joining -----------------------------------------------------------------

def _tokens(name: str) -> set[str]:
    return set(normalise(name).split())


def _name_pairs(fb: pd.DataFrame, fpl: pd.DataFrame):
    """Yield (score, fbref position, element, how) for every plausible pair.

    Scored by how much of the name agrees, with a bonus for the club. The
    club is only a bonus: a player who moved on deadline day is at his new
    club in FPL and his old one in fbref, and he is still the same player.
    """
    for i, f in enumerate(fb.itertuples()):
        ft = _tokens(f.Player)
        if not ft:
            continue
        f_surname = normalise(f.Player).split()[-1]
        for p in fpl.itertuples():
            pt = _tokens(p.name)
            if not ft & pt:
                continue
            if ft == pt:
                how, score = "exact", 10
            elif ft <= pt or pt <= ft:
                # 'Bruno Fernandes' inside 'Bruno Borges Fernandes', or
                # 'Abdul Fatawu' inside 'Abdul Fatawu Issahaku'.
                how, score = "partial", 8
            elif normalise(p.name).split()[-1] == f_surname:
                how, score = "surname", 5
            else:
                how, score = "token", 3
            yield score + 4 * (p.team == f.Squad), i, p.element, how


def _minutes_pairs(fb: pd.DataFrame, fpl: pd.DataFrame,
                   left: set[int], free: set[int]):
    """Settle the leftovers on minutes: same club, and only one candidate.

    fbref's nicknames — Beto, Costinha — share no token with the full name
    FPL carries, so nothing string-based will find them. What does find them
    is that both sources counted the same man's minutes. Accepted only when
    the club agrees and exactly one unclaimed player is close enough, so a
    guess is never made between two.
    """
    by_element = fpl.set_index("element")
    for i in sorted(left):
        f = fb.iloc[i]
        cand = [e for e in free
                if by_element.at[e, "team"] == f["Squad"]
                and abs(by_element.at[e, "minutes"] - f["fb_minutes"])
                <= MINUTES_TOL]
        if len(cand) == 1:
            yield i, cand[0]


def match_rows(fb: pd.DataFrame, fpl: pd.DataFrame) -> pd.DataFrame:
    """Attach an FPL ``element`` to each fbref player. One row per player.

    ``fb`` and ``fpl`` are the season-to-date totals per player, not the
    weekly rows: a player is matched once, and every gameweek follows.
    Assignment is one-to-one and best-first, so the regular of a shared
    surname is claimed before the reserve.

    Adds ``element``, ``how`` (exact / partial / surname / token / minutes /
    none), the ``fpl_name`` and ``fpl_minutes`` it landed on, and
    ``minutes_gap`` — how far the two sources' minutes sit apart, which is
    the audit on the whole join.
    """
    pairs = sorted(_name_pairs(fb, fpl), reverse=True)
    taken_fb: dict[int, tuple[int, str]] = {}
    taken_fpl: set[int] = set()
    for _, i, element, how in pairs:
        if i in taken_fb or element in taken_fpl:
            continue
        taken_fb[i] = (element, how)
        taken_fpl.add(element)

    left = set(range(len(fb))) - set(taken_fb)
    free = set(fpl["element"]) - taken_fpl
    for i, element in _minutes_pairs(fb, fpl, left, free):
        if element in taken_fpl:      # claimed by an earlier leftover
            continue
        taken_fb[i] = (element, "minutes")
        taken_fpl.add(element)

    out = fb.copy()
    out["element"] = [taken_fb.get(i, (pd.NA, None))[0] for i in range(len(fb))]
    out["how"] = [taken_fb.get(i, (None, "none"))[1] for i in range(len(fb))]

    by_element = fpl.set_index("element")
    out["fpl_name"] = [by_element.at[e, "name"] if pd.notna(e) else ""
                       for e in out["element"]]
    out["fpl_team"] = [by_element.at[e, "team"] if pd.notna(e) else ""
                       for e in out["element"]]
    out["fpl_minutes"] = [by_element.at[e, "minutes"] if pd.notna(e) else pd.NA
                          for e in out["element"]]
    out["minutes_gap"] = (out["fpl_minutes"] - out["fb_minutes"]).abs()
    return out


# --- the board ---------------------------------------------------------------

def weekly(data_dir: str | Path = HERE / "data" / "2026-27") -> pd.DataFrame:
    """Return one row per (player, gameweek) with all three quantities.

    Columns: ``element, name, team, position, round, minutes, played,
    shots, pkatt, xg_raw, xg, xa``. ``xg`` is the penalty-adjusted number
    the board ranks on; ``xg_raw`` is what FPL reported.

    The frame carries ``attrs["join"]`` — the per-player match table — and
    ``attrs["gameweeks"]``, the gameweeks fbref covers.
    """
    data_dir = Path(data_dir)
    fb_weekly = load_fbref(data_dir / "fbref_shots.xlsx")
    fpl_weekly = load_fpl(data_dir / "all_gws.csv")

    # Rank only the gameweeks **both** sources cover. A round FPL has but
    # fbref does not would show nobody shooting; a sheet FPL has not caught
    # up with would show nobody creating. Either way the board would be
    # wrong rather than incomplete, so the odd one out is dropped and named.
    fb_gws = set(fb_weekly["round"])
    fpl_gws = set(fpl_weekly["round"])
    gameweeks = sorted(fb_gws & fpl_gws)
    if not gameweeks:
        raise ValueError(
            f"no gameweek is in both sources: fbref has {sorted(fb_gws)}, "
            f"the FPL dump has {sorted(fpl_gws)}")
    fb_weekly = fb_weekly[fb_weekly["round"].isin(gameweeks)]
    fpl_weekly = fpl_weekly[fpl_weekly["round"].isin(gameweeks)]

    fb_totals = (fb_weekly.groupby(["Player", "Squad"], as_index=False)
                 .agg({"fb_minutes": "sum"}))
    fpl_totals = (fpl_weekly.groupby("element", as_index=False)
                  .agg(name=("name", "first"), team=("team", "first"),
                       position=("Position", "first"), minutes=("minutes", "sum")))
    join = match_rows(fb_totals, fpl_totals)

    key = join.set_index(["Player", "Squad"])["element"]
    fb_weekly = fb_weekly.copy()
    fb_weekly["element"] = pd.MultiIndex.from_frame(
        fb_weekly[["Player", "Squad"]]).map(key)

    out = fpl_weekly.merge(
        fb_weekly.loc[fb_weekly["element"].notna(),
                      ["element", "round", "shots", "pkatt"]],
        on=["element", "round"], how="left")
    out[["shots", "pkatt"]] = out[["shots", "pkatt"]].fillna(0.0)

    out["played"] = out["minutes"] > 0
    out["xg_raw"] = out["expected_goals"]
    out["xg"] = out["xg_raw"] - PENALTY_XG * out["pkatt"]
    out["xa"] = out["expected_assists"]
    out = out.rename(columns={"Position": "position"})

    # FPL already counts the position-appropriate defensive actions, so the
    # column is used as it stands. What it does not say is whether the
    # count was enough for the 2 points, since the bar differs by position.
    out["dc"] = out["defensive_contribution"]
    bar = out["position"].map(DC_THRESHOLD)
    out["dc_hit"] = out["dc"] >= bar          # NaN bar (a keeper) is False
    out["dc_bar"] = bar

    out = out[["element", "name", "team", "position", "round", "minutes",
               "played", "shots", "pkatt", "xg_raw", "xg", "xa",
               "dc", "dc_hit", "dc_bar"]]
    out = out.sort_values(["element", "round"]).reset_index(drop=True)
    out.attrs["join"] = join
    out.attrs["gameweeks"] = gameweeks
    out.attrs["fbref_only"] = sorted(fb_gws - fpl_gws)
    out.attrs["fpl_only"] = sorted(fpl_gws - fb_gws)
    return out


def restrict(week: pd.DataFrame, positions=None) -> pd.DataFrame:
    """Cut the frame down to a set of positions, keeping the ``attrs``.

    Ranking happens **after** this, so a board of defenders and midfielders
    ranks its players against each other rather than against forwards. A
    defender's three shots mean something next to other defenders and
    midfielders; next to Haaland they mean very little.
    """
    if positions is None:
        return week
    out = week[week["position"].isin(positions)].copy()
    out.attrs = dict(week.attrs)
    out.attrs["positions"] = tuple(positions)
    return out


def rank_gameweeks(week: pd.DataFrame, categories=CATEGORIES) -> pd.DataFrame:
    """Rank each gameweek's players on each category, and on the aggregate.

    Only players who played are ranked, and only against the players in the
    frame — so pass it through ``restrict`` first if the board is a subset.
    Within a category the rank is 1 for the best and ties share the mean
    rank, so nobody gains by sitting in a crowd of zeros. The aggregate is
    the sum of the category ranks, re-ranked from 1 with ties sharing the
    best available place — an ordinary joint 12th.

    Adds ``rank_<cat>`` for each category, plus ``rank_sum``, ``rank`` and
    ``field`` (how many played that gameweek). Rows for players who did not
    play keep NA ranks. ``attrs["categories"]`` records which were used.
    """
    cols = [f"rank_{c}" for c in categories] + ["rank_sum", "rank"]
    out = week.copy()
    for col in cols:
        out[col] = pd.NA
    out["field"] = out.groupby("round")["played"].transform("sum")

    played = out["played"]
    for cat in categories:
        out.loc[played, f"rank_{cat}"] = (
            out.loc[played].groupby("round")[cat]
            .rank(ascending=False, method="average"))

    out.loc[played, "rank_sum"] = sum(
        out.loc[played, f"rank_{cat}"] for cat in categories)
    out.loc[played, "rank"] = (
        out.loc[played].groupby("round")["rank_sum"]
        .rank(ascending=True, method="min").astype(int))
    # The columns were seeded with NA to be object-typed while partially
    # filled; make them numeric again so the pivots downstream are numbers.
    for col in cols:
        out[col] = pd.to_numeric(out[col])
    out.attrs = dict(week.attrs)
    out.attrs["categories"] = tuple(categories)
    return out


def board(ranked: pd.DataFrame, categories=None) -> pd.DataFrame:
    """Pivot to the table the page shows: a player a row, a gameweek a column.

    ``gw<n>`` holds the aggregate rank, or NA for a gameweek he did not
    play. Each category also gets its raw value and **its own rank** that
    week — ``shots_gw<n>`` and ``shots_rank_gw<n>`` — so the shots table can
    show where a shots count placed without borrowing the aggregate, which
    is two thirds about something else. Beside them:

    * ``played`` — gameweeks he played, out of those covered;
    * ``total``  — the ranks summed, a **missed gameweek charged that
      week's last place**, so that missing one cannot flatter the total;
    * ``average``— the mean rank over the gameweeks he played;
    * ``dc_weeks``— gameweeks he cleared FPL's defensive-contribution bar,
      with ``dc_hit_gw<n>`` saying which.

    Both are ascending: 1 is the best. Players who have not played at all
    are dropped — a row of blanks says nothing.
    """
    categories = categories or ranked.attrs.get("categories", CATEGORIES)
    gameweeks = sorted(ranked["round"].unique())
    field = ranked.groupby("round")["field"].first()

    who = (ranked.groupby("element", as_index=False)
           .agg(name=("name", "first"), team=("team", "first"),
                position=("position", "first"),
                minutes=("minutes", "sum"), played=("played", "sum"),
                dc_weeks=("dc_hit", "sum")))
    who = who[who["played"] > 0]

    ranks = ranked.pivot_table(index="element", columns="round", values="rank",
                               aggfunc="first")
    ranks = ranks.reindex(index=who["element"], columns=gameweeks)

    out = who.set_index("element")
    for gw in gameweeks:
        out[f"gw{gw}"] = ranks[gw]
    # A blank week costs last place. Without it the sort rewards absence:
    # a man who played once and came 40th would beat a man who played twice
    # and came 5th and 10th.
    charged = ranks.copy()
    for gw in gameweeks:
        charged[gw] = charged[gw].fillna(field[gw])
    out["total"] = charged.sum(axis=1)
    out["average"] = ranks.mean(axis=1)

    for cat in categories:
        totals = ranked.pivot_table(index="element", columns="round",
                                    values=cat, aggfunc="first")
        totals = totals.reindex(index=who["element"], columns=gameweeks)
        # The category's own rank that gameweek — the one that belongs beside
        # a shots number, as against the aggregate over all of them.
        cat_ranks = ranked.pivot_table(index="element", columns="round",
                                       values=f"rank_{cat}", aggfunc="first")
        cat_ranks = cat_ranks.reindex(index=who["element"], columns=gameweeks)
        for gw in gameweeks:
            # A rank exists exactly when he played, so it doubles as the mask
            # that keeps a blank week blank rather than showing it as zero.
            out[f"{cat}_gw{gw}"] = totals[gw].where(ranks[gw].notna())
            out[f"{cat}_rank_gw{gw}"] = cat_ranks[gw]
        out[f"{cat}_total"] = totals.sum(axis=1)

    # Which weeks cleared the 2-point defensive bar, for the marker on the
    # defcon board's cells. Kept whatever the categories, since it costs one
    # pivot and the column is meaningless where it is not shown.
    hits = ranked.pivot_table(index="element", columns="round",
                              values="dc_hit", aggfunc="first")
    hits = hits.reindex(index=who["element"], columns=gameweeks).fillna(False)
    for gw in gameweeks:
        out[f"dc_hit_gw{gw}"] = hits[gw].astype(bool)

    out.attrs["categories"] = tuple(categories)
    return out.sort_values(["total", "average"]).reset_index()


MAX_NAMED = 20   # how many problem rows the audit spells out before summarising


def _named(lines: list[str], items: list[str], what: str) -> None:
    """Append at most ``MAX_NAMED`` problem rows, then say how many are left."""
    lines.extend(items[:MAX_NAMED])
    if len(items) > MAX_NAMED:
        lines.append(f"  … and {len(items) - MAX_NAMED} more {what}")


def report_join(week: pd.DataFrame) -> str:
    """A plain-text audit of the join, for the terminal and the page.

    Says how each fbref player was matched, and — the part that matters —
    how far the two sources' minutes disagree. Anything unmatched, or
    matched but disagreeing on minutes by more than ``MINUTES_TOL``, is
    named worst-first: those are the rows where the board could be wrong
    about who took the shots.

    The verdict on the first line is ``clean`` only when every fbref player
    matched, every pair agrees on minutes, and nobody FPL says played is
    missing from fbref. Anything else says ``needs a look`` — it is not
    fatal, since a half-updated workbook looks exactly like this, but it
    should never pass unnoticed.
    """
    join = week.attrs["join"]
    gaps = join[join["element"].notna()]
    bad = gaps[gaps["minutes_gap"] > MINUTES_TOL].sort_values(
        "minutes_gap", ascending=False)
    unmatched = join[join["element"].isna()]

    # The other direction: a player FPL says was on the pitch but fbref never
    # lists has no shots at all, and would be ranked as if he took none.
    seen = set(join.loc[join["element"].notna(), "element"])
    missing = sorted(set(week.loc[week["played"], "element"]) - seen)

    trouble = len(bad) + len(unmatched) + len(missing)
    lines = [f"verdict: {'clean' if not trouble else 'NEEDS A LOOK'} "
             f"({trouble} row{'' if trouble == 1 else 's'} to check)",
             "gameweeks ranked: "
             + ", ".join(f"GW{g}" for g in week.attrs["gameweeks"])]
    for label, gws in (("fbref sheet but no FPL round", week.attrs["fbref_only"]),
                       ("FPL round but no fbref sheet", week.attrs["fpl_only"])):
        if gws:
            lines.append(f"  not ranked, {label}: "
                         + ", ".join(f"GW{g}" for g in gws))
    lines += [f"fbref players: {len(join)}",
              "matched: " + ", ".join(
                  f"{k} {v}" for k, v in join["how"].value_counts().items()),
              f"minutes agree within {MINUTES_TOL}: "
              f"{len(gaps) - len(bad)} of {len(gaps)}"]

    _named(lines, [f"  ? {r.Player} ({r.Squad}) — fbref {r.fb_minutes:.0f} min, "
                   f"FPL {r.fpl_minutes:.0f} min for {r.fpl_name}, "
                   f"gap {r.minutes_gap:.0f}"
                   for r in bad.itertuples()], "disagreeing on minutes")
    _named(lines, [f"  UNMATCHED {r.Player} ({r.Squad}) — no shots for him"
                   for r in unmatched.itertuples()], "unmatched")

    lines.append(f"played but absent from fbref: {len(missing)}")
    if missing:
        names = week.set_index("element")["name"].groupby(level=0).first()
        _named(lines, [f"  MISSING {names[e]} — ranked as if he took no shot"
                       for e in missing], "absent from fbref")
    return "\n".join(lines)


def main() -> None:
    week = weekly()
    print(report_join(week), "\n")
    gws = week.attrs["gameweeks"]

    for label, positions, cats in (
            ("all players, 3 categories", None, CATEGORIES),
            ("defcon (DF/MD), 4 categories", DEFCON_POSITIONS,
             DEFCON_CATEGORIES)):
        ranked = rank_gameweeks(restrict(week, positions), cats)
        table = board(ranked)
        cols = ["name", "team", "position"] + [f"gw{g}" for g in gws] + \
            ["played", "total", "average"]
        if "dc" in cats:
            cols.append("dc_weeks")
        print(f"\n=== {label}: gameweeks {gws}, {len(table)} players")
        print(table[cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
