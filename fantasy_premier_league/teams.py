"""Team attack, defence and the difference between them, gameweek by gameweek.

The player boards (``shots.py``) ask which *players* are getting shots, chances
and defensive work. This asks the same of *clubs*, on three measures each way:

* **Attack**  — shots taken, penalty-adjusted xG, goals scored.
* **Defence** — shots conceded, penalty-adjusted xG conceded, goals conceded.
* **Net**     — attack minus defence: shot difference, xG difference and
  goal difference.

Each measure is ranked across the twenty clubs in each gameweek, the three
ranks are summed, and the sum re-ranked 1..20 — the same composite the player
boards use.

Three sources, one per measure
------------------------------
* **Shots** — the fbref workbook (``data/2026-27/fbref_shots.xlsx``), summed
  by club **within each cumulative sheet** and then differenced club by club.
  Summing by club before differencing keeps a mid-season mover's shots with
  the club he took them for: fbref splits his season into one row per club.
* **Expected goals** — the FPL dump (``data/2026-27/all_gws.csv``), summed
  by the club a player **played for in that fixture**. FPL's ``team`` column
  is his club *now*, which for the five players who have moved would credit
  their old club's chances to the new one. The fixture says which side he
  was on: a player at home was on the home team, and the home team is the
  opponent named by anyone who played away in the same fixture.
* **Goals** — the results file the handicap app already keeps
  (``premier_league_handicap/data/2026_2027/results.csv``). Not fbref's
  ``Gls``, which counts goals *by players* and so misses own goals — seven so
  far, each one the difference between fbref and the score in its match.

Penalties
---------
The same rule as the player boards: every penalty attempt fbref records
costs the attacking club 0.75 xG in the gameweek it was taken
(``shots.PENALTY_XG``). A club's xG conceded is its opponent's adjusted xG,
so the same penalty comes off the defending side too. Goals are left as
scored — a converted penalty counts, as it does on the table.

Conceding
---------
Everything a club concedes is what its opponent did in the same match. xG
and goals are per fixture, so that is exact. fbref's shots are only per
gameweek, so a club's shots conceded are its opponent's shots for the week —
exact when the opponent played once that week, and **not computable** when
the opponent had a double: its weekly total would include the other match.
Such cells are left blank and named in the audit rather than filled with a
wrong number. There have been no doubles or blanks so far.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import shots as S

HERE = Path(__file__).parent
DATA = HERE / "data" / "2026-27"
RESULTS = HERE.parent / "premier_league_handicap" / "data" / "2026_2027" / "results.csv"

# (key, name, direction). +1 means more is better and ranks first; -1 means
# less is better. Defence ranks the fewest conceded first.
SIDES = {
    "attack": [("shots_for", "Shots", +1),
               ("xg_for", "xG (pen-adj)", +1),
               ("goals_for", "Goals", +1)],
    "defence": [("shots_against", "Shots conceded", -1),
                ("xg_against", "xG conceded (pen-adj)", -1),
                ("goals_against", "Goals conceded", -1)],
    "net": [("shots_diff", "Shot difference", +1),
            ("xg_diff", "xG difference (pen-adj)", +1),
            ("goals_diff", "Goal difference", +1)],
}


def _club(name: str) -> str:
    """fbref's club spelling onto FPL's — the two the boards already join on."""
    return S.SQUAD_ALIASES.get(name, name)


# --- loading -----------------------------------------------------------------

def load_results(path: str | Path = RESULTS) -> pd.DataFrame:
    """One row per match played: ``gw, home, away, home_goals, away_goals``.

    The file is an fbref export with blank separator rows between gameweeks
    and future fixtures listed without a score; both drop out here.
    """
    r = pd.read_csv(path, encoding="utf-8-sig")
    r = r.dropna(subset=["Home", "Away", "Score"])
    goals = (r["Score"].astype(str)
             .str.replace(r"[‐-―−]", "-", regex=True)
             .str.extract(r"^\s*(\d+)\s*-\s*(\d+)\s*$"))
    r = r[goals[0].notna()].copy()
    out = pd.DataFrame({
        "gw": r["Wk"].astype(int).values,
        "home": r["Home"].map(_club).values,
        "away": r["Away"].map(_club).values,
        "home_goals": goals.loc[r.index, 0].astype(int).values,
        "away_goals": goals.loc[r.index, 1].astype(int).values,
    })
    return out


def fbref_team_weeks(path: str | Path = DATA / "fbref_shots.xlsx") -> pd.DataFrame:
    """Shots and penalty attempts per (club, gameweek), from the cumulative sheets.

    Summed by club **inside** each sheet, then differenced: a mover's rows
    stay with the club they were earned at.
    """
    cum = {}
    for gw, sheet in S.gameweek_sheets(path):
        d = pd.read_excel(path, sheet_name=sheet)
        d["Squad"] = d["Squad"].map(_club)
        cum[gw] = d.groupby("Squad")[["Sh", "PKatt"]].sum()
    rows, prev = [], None
    for gw in sorted(cum):
        cur = cum[gw]
        wk = cur if prev is None else cur.sub(prev, fill_value=0)
        if (wk < 0).any().any():
            raise ValueError(f"GW{gw}: a club's cumulative shots fell — "
                             "the sheets are not cumulative")
        rows.append(wk.assign(gw=gw))
        prev = cur
    out = pd.concat(rows).reset_index().rename(
        columns={"Squad": "team", "Sh": "shots", "PKatt": "pkatt"})
    return out[["team", "gw", "shots", "pkatt"]]


def fpl_team_fixtures(path: str | Path = DATA / "all_gws.csv") -> pd.DataFrame:
    """Expected goals per (fixture, club), credited to the side each player was on.

    Also returns FPL's own score for the fixture, which the audit checks
    against the results file.
    """
    f = pd.read_csv(path)
    home = f[~f["was_home"]].groupby("fixture")["opponent_team"].agg(set)
    away = f[f["was_home"]].groupby("fixture")["opponent_team"].agg(set)
    torn = sorted(set(home[home.map(len) > 1].index)
                  | set(away[away.map(len) > 1].index))
    if torn:
        raise ValueError(f"FPL fixtures naming two different opponents: {torn}")
    home, away = home.map(lambda s: next(iter(s))), away.map(lambda s: next(iter(s)))

    f["played_for"] = [home[fx] if wh else away[fx]
                       for fx, wh in zip(f["fixture"], f["was_home"])]
    xg = (f.groupby(["fixture", "played_for"], as_index=False)
          .agg(round=("round", "first"), xg_raw=("expected_goals", "sum")))
    score = f.groupby("fixture").agg(fpl_home_goals=("team_h_score", "first"),
                                     fpl_away_goals=("team_a_score", "first"))
    fixtures = pd.DataFrame({"home": home, "away": away}).join(score)
    moved = f[(f["played_for"] != f["team"]) & (f["minutes"] > 0)]
    fixtures.attrs["moved_rows"] = moved[["round", "full_name", "played_for",
                                          "team"]].reset_index(drop=True)
    fixtures.attrs["own_goals"] = f.groupby("round")["own_goals"].sum()
    return xg.rename(columns={"played_for": "team"}), fixtures


# --- the team-week table -----------------------------------------------------

def team_weeks(data_dir: str | Path = DATA,
               results_path: str | Path = RESULTS) -> pd.DataFrame:
    """One row per (club, gameweek) with everything for and against.

    Columns: ``team, gw, opponent, venue, shots_for, pkatt_for, xg_raw_for,
    xg_for, goals_for`` and the same ``*_against``, plus the three
    differences. ``attrs["audit"]`` carries the reconciliation lines.
    """
    data_dir = Path(data_dir)
    results = load_results(results_path)
    shots_wk = fbref_team_weeks(data_dir / "fbref_shots.xlsx")
    xg_fx, fixtures = fpl_team_fixtures(data_dir / "all_gws.csv")

    # The fixture a match is: home and away name it uniquely for a season.
    fx_key = {(h, a): fx for fx, h, a in zip(fixtures.index, fixtures["home"],
                                             fixtures["away"])}
    results["fixture"] = [fx_key.get((h, a)) for h, a in
                          zip(results["home"], results["away"])]

    # A gameweek covered by all three sources, or it is not ranked.
    gws = sorted(set(results["gw"]) & set(shots_wk["gw"])
                 & set(xg_fx["round"]))

    long = pd.concat([
        pd.DataFrame({"gw": results["gw"], "fixture": results["fixture"],
                      "team": results["home"], "opponent": results["away"],
                      "venue": "H", "goals_for": results["home_goals"],
                      "goals_against": results["away_goals"]}),
        pd.DataFrame({"gw": results["gw"], "fixture": results["fixture"],
                      "team": results["away"], "opponent": results["home"],
                      "venue": "A", "goals_for": results["away_goals"],
                      "goals_against": results["home_goals"]}),
    ], ignore_index=True)
    long = long[long["gw"].isin(gws)]

    # xG is per fixture, so for and against are both exact.
    xg = xg_fx.set_index(["fixture", "team"])["xg_raw"]
    long["xg_raw_for"] = [xg.get((fx, t), np.nan)
                          for fx, t in zip(long["fixture"], long["team"])]
    long["xg_raw_against"] = [xg.get((fx, o), np.nan)
                              for fx, o in zip(long["fixture"], long["opponent"])]

    # Matches per club per week: fbref's weekly shots are only splittable by
    # match when the club played once.
    games = long.groupby(["gw", "team"]).size()
    doubles = sorted((g, t) for (g, t), n in games.items() if n > 1)

    sw = shots_wk.set_index(["gw", "team"])
    wk = (long.groupby(["gw", "team"], as_index=False)
          .agg(opponent=("opponent", " & ".join), venue=("venue", "".join),
               goals_for=("goals_for", "sum"),
               goals_against=("goals_against", "sum"),
               xg_raw_for=("xg_raw_for", "sum"),
               xg_raw_against=("xg_raw_against", "sum")))
    wk["shots_for"] = [sw["shots"].get((g, t), 0.0) for g, t in zip(wk["gw"], wk["team"])]
    wk["pkatt_for"] = [sw["pkatt"].get((g, t), 0.0) for g, t in zip(wk["gw"], wk["team"])]

    opp_of = long.groupby(["gw", "team"])["opponent"].agg(list)
    shots_against, pkatt_against = [], []
    for g, t in zip(wk["gw"], wk["team"]):
        opps = opp_of[(g, t)]
        if any(games.get((g, o), 0) > 1 for o in opps):
            shots_against.append(np.nan)      # an opponent's week spans two matches
            pkatt_against.append(np.nan)
        else:
            shots_against.append(sum(sw["shots"].get((g, o), 0.0) for o in opps))
            pkatt_against.append(sum(sw["pkatt"].get((g, o), 0.0) for o in opps))
    wk["shots_against"], wk["pkatt_against"] = shots_against, pkatt_against

    # A penalty comes off the side that took it, which is the other side's
    # xG conceded too. In a double week the penalty count cannot be split by
    # match either, so the adjustment is applied to the week's sum.
    wk["xg_for"] = wk["xg_raw_for"] - S.PENALTY_XG * wk["pkatt_for"]
    wk["xg_against"] = wk["xg_raw_against"] - S.PENALTY_XG * wk["pkatt_against"]
    # Sums of 2-place numbers carry binary noise that would split genuine
    # ties in the ranks; see shots.XG_DECIMALS.
    xg_cols = ["xg_raw_for", "xg_raw_against", "xg_for", "xg_against"]
    wk[xg_cols] = wk[xg_cols].round(S.XG_DECIMALS)

    wk["shots_diff"] = wk["shots_for"] - wk["shots_against"]
    wk["xg_diff"] = (wk["xg_for"] - wk["xg_against"]).round(S.XG_DECIMALS)
    wk["goals_diff"] = wk["goals_for"] - wk["goals_against"]

    wk.attrs["audit"] = _audit(results, fixtures, shots_wk, xg_fx, wk, gws,
                               doubles)
    wk.attrs["gameweeks"] = gws
    og = fixtures.attrs["own_goals"]
    wk.attrs["own_goals"] = int(og[og.index.isin(gws)].sum())
    wk.attrs["moved_rows"] = len(fixtures.attrs["moved_rows"].query("round in @gws"))
    return wk.sort_values(["gw", "team"]).reset_index(drop=True)


def _audit(results, fixtures, shots_wk, xg_fx, wk, gws, doubles) -> str:
    """The reconciliation, verdict first — the same shape as the player join's."""
    lines, trouble = [], 0

    unmatched = results[results["fixture"].isna()]
    trouble += len(unmatched)
    fx = fixtures.loc[results["fixture"].dropna().astype(int)]
    fx = fx.assign(gw=results.loc[results["fixture"].notna(), "gw"].values,
                   hg=results.loc[results["fixture"].notna(), "home_goals"].values,
                   ag=results.loc[results["fixture"].notna(), "away_goals"].values)
    bad_score = fx[(fx["fpl_home_goals"] != fx["hg"]) | (fx["fpl_away_goals"] != fx["ag"])]
    trouble += len(bad_score)
    xg_rounds = xg_fx.groupby("fixture")["round"].first()
    bad_round = fx[[xg_rounds.get(i) != g for i, g in zip(fx.index, fx["gw"])]]
    trouble += len(bad_round)

    teams_per_gw = wk.groupby("gw")["team"].nunique()
    short = teams_per_gw[teams_per_gw != 20]
    fb_teams = set(shots_wk["team"])
    stray = sorted(fb_teams - set(wk["team"]))
    trouble += len(stray)

    # Shots: the clubs' weekly shots must add up to the league's.
    shots_gap = (shots_wk[shots_wk["gw"].isin(gws)].groupby("gw")["shots"].sum()
                 - wk.groupby("gw")["shots_for"].sum()).abs()
    trouble += int((shots_gap > 0).sum())

    lines.append(f"verdict: {'clean' if not trouble else 'NEEDS A LOOK'} "
                 f"({trouble} row{'' if trouble == 1 else 's'} to check)")
    lines.append("gameweeks ranked: " + ", ".join(f"GW{g}" for g in gws))
    lines.append(f"matches: {len(results)} in the results file, "
                 f"{len(results) - len(unmatched)} found in FPL's fixtures")
    lines.append(f"scores agree with FPL: {len(fx) - len(bad_score)} of {len(fx)}")
    lines.append(f"FPL round agrees with the results gameweek: "
                 f"{len(fx) - len(bad_round)} of {len(fx)}")
    lines.append("clubs per gameweek: " + ", ".join(
        f"GW{g} {n}" for g, n in teams_per_gw.items()))
    lines.append(f"club shots add up to the league's every week: "
                 f"{'yes' if not (shots_gap > 0).any() else 'NO'}")
    lines.append(f"doubles (shots conceded left blank): {len(doubles)}")
    moved = fixtures.attrs["moved_rows"]
    moved = moved[moved["round"].isin(gws)]
    lines.append(f"player-weeks whose xG goes to the club he played for, not "
                 f"FPL's current club: {len(moved)}")
    for r in moved.itertuples():
        lines.append(f"  GW{r.round} {r.full_name.replace('_', ' ')}: "
                     f"{r.played_for} (FPL now says {r.team})")
    og = fixtures.attrs["own_goals"]
    lines.append(f"own goals (in the results, missed by fbref's Gls): "
                 f"{int(og[og.index.isin(gws)].sum())}")
    for r in unmatched.itertuples():
        lines.append(f"  UNMATCHED GW{r.gw} {r.home} v {r.away} — not in FPL's fixtures")
    for i, r in bad_score.iterrows():
        lines.append(f"  ? {r.home} v {r.away}: results {r.hg}-{r.ag}, "
                     f"FPL {r.fpl_home_goals}-{r.fpl_away_goals}")
    for i, r in bad_round.iterrows():
        lines.append(f"  ? {r.home} v {r.away}: results GW{r.gw}, FPL round "
                     f"{xg_rounds.get(i)}")
    for t in stray:
        lines.append(f"  ? fbref club {t!r} matches no club in the results")
    for g, t in doubles:
        lines.append(f"  double: {t} in GW{g}")
    return "\n".join(lines)


# --- ranking -----------------------------------------------------------------

def rank_side(wk: pd.DataFrame, side: str) -> pd.DataFrame:
    """Rank one side's three measures within each gameweek, and the composite.

    Adds ``rank_<measure>`` for each, ``rank_sum`` and ``rank``. Ties share
    the mean rank on a measure and the best place on the composite, as on the
    player boards. A blank measure (a double's shots conceded) is not ranked,
    and a composite needs all three, so it is blank too.
    """
    out = wk.copy()
    cols = []
    for key, _, direction in SIDES[side]:
        out[f"rank_{key}"] = (out.groupby("gw")[key]
                              .rank(ascending=direction < 0, method="average"))
        cols.append(f"rank_{key}")
    out["rank_sum"] = out[cols].sum(axis=1, min_count=len(cols))
    out["rank"] = out.groupby("gw")["rank_sum"].rank(method="min")
    out["field"] = out.groupby("gw")["team"].transform("size")
    out.attrs = dict(wk.attrs)
    out.attrs["side"] = side
    return out


def board(ranked: pd.DataFrame) -> pd.DataFrame:
    """A club a row, a gameweek a column: the composite rank, and each measure.

    ``gw<n>`` is the composite rank; ``<measure>_gw<n>`` and
    ``<measure>_rank_gw<n>`` the value and its rank. ``total`` sums the
    composite ranks with a missed gameweek charged last place (only a blank
    gameweek can cause one); ``average`` is the mean over weeks played;
    ``<measure>_total`` is the season sum of the measure.
    """
    side = ranked.attrs["side"]
    gws = sorted(ranked["gw"].unique())
    field = ranked.groupby("gw")["field"].first()
    teams = sorted(ranked["team"].unique())

    out = pd.DataFrame(index=pd.Index(teams, name="team"))
    comp = ranked.pivot(index="team", columns="gw", values="rank").reindex(
        index=teams, columns=gws)
    for g in gws:
        out[f"gw{g}"] = comp[g]
    out["played"] = comp.notna().sum(axis=1)
    out["total"] = sum(comp[g].fillna(field[g]) for g in gws)
    out["average"] = comp.mean(axis=1)

    for key, _, _ in SIDES[side]:
        val = ranked.pivot(index="team", columns="gw", values=key).reindex(
            index=teams, columns=gws)
        rk = ranked.pivot(index="team", columns="gw", values=f"rank_{key}").reindex(
            index=teams, columns=gws)
        for g in gws:
            out[f"{key}_gw{g}"] = val[g]
            out[f"{key}_rank_gw{g}"] = rk[g]
        out[f"{key}_total"] = val.sum(axis=1).round(S.XG_DECIMALS)

    opp = ranked.pivot(index="team", columns="gw", values="opponent").reindex(
        index=teams, columns=gws)
    ven = ranked.pivot(index="team", columns="gw", values="venue").reindex(
        index=teams, columns=gws)
    for g in gws:
        out[f"opp_gw{g}"] = opp[g]
        out[f"venue_gw{g}"] = ven[g]

    out.attrs = dict(ranked.attrs)
    return out.sort_values(["average", "total"]).reset_index()


def main() -> None:
    wk = team_weeks()
    print(wk.attrs["audit"], "\n")
    for side in SIDES:
        b = board(rank_side(wk, side))
        gws = wk.attrs["gameweeks"]
        cols = ["team"] + [f"gw{g}" for g in gws] + ["total", "average"] + \
            [f"{k}_total" for k, _, _ in SIDES[side]]
        print(f"=== {side}")
        print(b[cols].to_string(index=False), "\n")


if __name__ == "__main__":
    main()
