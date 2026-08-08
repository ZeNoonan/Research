"""The FPL six-factor player rating engine.

An additive binary-factor model for weekly Fantasy Premier League picks, in
the spirit of the factor systems in ``march_madness/`` (one star per factor
versus the seed-group median) and ``nfl_report/`` (five binary votes). Each
factor compares a player to their *position peers* (GK / DEF / MID / FWD)
and awards one star. A player's rating is the sum, 0-6 stars.

The six factors
---------------
1. Quality  – the model's expected points per 90 (rebuilt from FPL scoring
   rules and the player's underlying per-90 numbers) above the position
   median. Process stats, not outcomes.
2. Value    – expected points per 90 per million of price above the position
   median. Points per pound is the pick that funds the rest of the squad.
3. Form     – total FPL points over the last 5 matches the player actually
   played, above the position median. Momentum.
4. Minutes  – average minutes over the last 5 matches the player actually
   played, at or above the position median (at-or-above, not strictly
   above: keepers all average 90, and averaging the position's typical
   full-match load is what "nailed" means). The 90-minute starters.
5. Justice  – under-rewarded versus the underlying numbers over the last 6
   matches the player actually played: attackers whose expected goal
   involvements exceed their actual returns, defenders/keepers who conceded
   more than their expected goals conceded. Luck mean-reverts and the crowd
   over-reacts to outcomes, so the unlucky are cheap.

Every window counts the player's **own appearances**, not calendar
gameweeks, so a spell on the bench or in the treatment room shifts a
window back rather than filling it with zeros. The price of that is a
minimum sample: a player must have made at least as many appearances as
the window is long to be scored on it at all (5 for Form and Minutes, 6
for Justice). Players short of it take no star for that factor **and are
left out of its median**, so a thin sample neither earns a star nor moves
the bar for everyone else. Early in a season this means the appearance-
window factors are dormant for everybody until enough football has been
played - which is honest: there is no five-match form in gameweek three.
6. Crowd    – ownership percentile below quality percentile within the
   position: the field underweights the player (bet against beta - the
   differential pick that gains you rank when it comes off).

Eligibility gate (the analogue of the NFL system only betting at |#| >= 3):
a player must average 45+ minutes over the last 4 matches he actually
played (fewer if he hasn't played 4 yet). Absence never drops a player -
an injured starter keeps the average from his last appearances - but a
player used only for short cameos does not make the cut. No factor can
rescue a player who doesn't play real minutes when he plays.

Quality engine (expected points per 90, from season-to-date per-90 rates)
--------------------------------------------------------------------------
Appearance points are common to every eligible player and are left out; the
scoring values are the FPL 2025/26 rules (goals: GK 10 / DEF 6 / MID 5 /
FWD 4; assists 3; clean sheets GK+DEF 4, MID 1; -1 per 2 conceded for
GK/DEF; 1 per 3 saves; defensive contribution 2 points at 10 CBIT for DEF
and 12 CBIRT for MID/FWD). The clean-sheet chance while the player is on
the pitch is the Poisson zero of their expected goals conceded per 90,
``exp(-xGC90)``.

Data
----
One CSV per gameweek (``gw<N>.csv``) with one row per player, in the format
of the official FPL API / the public per-gameweek exports (see the sample in
``data/2025-26/``). ``load_season`` reads every ``gw*.csv`` in a directory;
ratings use all loaded gameweeks as "season to date", so the same code rates
gameweek 2 on one week of evidence and gameweek 38 on thirty-seven.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd

POSITIONS = ("GK", "DEF", "MID", "FWD")

# --- FPL 2025/26 scoring values used by the quality engine -------------------
GOAL_POINTS = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}
ASSIST_POINTS = 3
CLEAN_SHEET_POINTS = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}
CONCEDE_PENALTY_PER_GOAL = {"GK": 0.5, "DEF": 0.5, "MID": 0.0, "FWD": 0.0}
SAVE_POINTS_PER_SAVE = 1.0 / 3.0
DC_POINTS = 2
DC_THRESHOLD = {"DEF": 10, "MID": 12, "FWD": 12}  # GKs are not eligible

# --- window and gate parameters ----------------------------------------------
FORM_WINDOW = 5           # gameweeks of points behind the Form factor
JUSTICE_WINDOW = 6        # gameweeks of luck behind the Justice factor
MINUTES_WINDOW = 4        # played matches behind the eligibility gate
MINUTES_FACTOR_WINDOW = 5  # played matches behind the Minutes factor
MINUTES_PER_GW = 45.0
PRIOR_MINUTES = 450.0     # shrinkage prior for per-90 rates (5 full matches)

# --- pre-season-only parameters ----------------------------------------------
# The in-season model rates a live season, where the appearance-based gate and
# windows are what keep an injured regular visible. A pre-season board is a
# different problem: the whole of last season is in, nobody is "currently"
# anything, and the question is who actually played. These apply only when
# ``rate_players(..., preseason=True)`` and never touch the in-season path.
TEAM_MINUTES = 38 * 90        # a full season for one outfield place
PRESEASON_MIN_MINUTES = 600.0  # absolute participation gate (see README)
PRESEASON_CROWD_MARGIN = 5.0   # percentile points quality must beat ownership by

FACTORS = ("quality", "value", "form", "minutes_factor", "justice", "crowd")
FACTOR_LETTERS = {"quality": "Q", "value": "V", "form": "F",
                  "minutes_factor": "M", "justice": "J", "crowd": "C"}

# Columns the engine actually uses; everything else in a gw file is carried
# ("xP" and other extras are optional and ignored).
REQUIRED = ["name", "position", "team", "element", "round", "minutes",
            "total_points", "goals_scored", "assists", "saves",
            "goals_conceded", "defensive_contribution", "expected_goals",
            "expected_assists", "expected_goals_conceded", "value", "selected"]


def load_season(data_dir: str | Path) -> pd.DataFrame:
    """Read every ``gw*.csv`` in ``data_dir`` into one per-player-per-GW frame."""
    data_dir = Path(data_dir)
    files = sorted(data_dir.glob("gw*.csv"),
                   key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    if not files:
        raise FileNotFoundError(f"no gw*.csv files in {data_dir}")
    frames = [pd.read_csv(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    df["position"] = df["position"].replace({"GKP": "GK"})
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"gw files are missing columns: {missing}")
    return df


def _per90(total: float, minutes: float) -> float:
    return total / minutes * 90.0 if minutes > 0 else 0.0


def expected_points_per_90(pos: str, xg90: float, xa90: float, xgc90: float,
                           saves90: float, dc_rate: float) -> float:
    """The quality engine: FPL points per 90 implied by the process stats."""
    pts = xg90 * GOAL_POINTS[pos] + xa90 * ASSIST_POINTS
    pts += math.exp(-xgc90) * CLEAN_SHEET_POINTS[pos]
    pts -= xgc90 * CONCEDE_PENALTY_PER_GOAL[pos]
    if pos == "GK":
        pts += saves90 * SAVE_POINTS_PER_SAVE
    else:
        pts += dc_rate * DC_POINTS
    return pts


def player_table(gws: pd.DataFrame, through_gw: int | None = None) -> pd.DataFrame:
    """Aggregate the per-GW rows into one row per player, season-to-date.

    ``through_gw`` limits the evidence to rounds <= that gameweek (used by the
    backtest to rate players as of an earlier week); default is all rounds.
    """
    df = gws if through_gw is None else gws[gws["round"] <= through_gw]
    if df.empty:
        raise ValueError(f"no gameweek rows at or before round {through_gw}")
    latest = int(df["round"].max())
    rounds = sorted(df["round"].unique())

    def window(n: int) -> pd.DataFrame:
        return df[df["round"] > latest - n]

    # Every window below counts the player's own appearances (minutes > 0),
    # however long ago - absence shifts a window back rather than filling it
    # with zeros. ``groupby(...).tail(n)`` takes each player's last n
    # appearances.
    apps = df[df["minutes"] > 0].sort_values("round")

    def last_apps(n: int) -> pd.DataFrame:
        return apps.groupby("element").tail(n)

    gate = last_apps(MINUTES_WINDOW).groupby("element")["minutes"].mean()
    mins_avg = (last_apps(MINUTES_FACTOR_WINDOW)
                .groupby("element")["minutes"].mean())
    form = (last_apps(FORM_WINDOW)
            .groupby("element")["total_points"].sum())
    jw = last_apps(JUSTICE_WINDOW).groupby("element")[
        ["expected_goals", "expected_assists", "goals_scored", "assists",
         "goals_conceded", "expected_goals_conceded"]].sum()

    played = df[df["minutes"] >= 60].copy()
    played["dc_hit"] = [
        int(r.defensive_contribution >= DC_THRESHOLD.get(r.position, 99))
        for r in played.itertuples()]
    dc_rate = played.groupby("element")["dc_hit"].mean()

    season = df.groupby("element").agg(
        minutes=("minutes", "sum"), points=("total_points", "sum"),
        xg=("expected_goals", "sum"), xa=("expected_assists", "sum"),
        xgc=("expected_goals_conceded", "sum"), saves=("saves", "sum"),
        goals=("goals_scored", "sum"), assists=("assists", "sum"),
        appearances=("minutes", lambda m: int((m > 0).sum())))

    snap = (df.sort_values("round").groupby("element")
              [["name", "position", "team", "value", "selected"]].last())

    out = season.join(snap)
    out["price"] = out["value"] / 10.0
    out["form_points"] = form.reindex(out.index).fillna(0)
    out["gate_minutes"] = gate.reindex(out.index).fillna(0.0)
    out["eligible"] = out["gate_minutes"] >= MINUTES_PER_GW
    out["minutes_avg"] = mins_avg.reindex(out.index).fillna(0.0)
    out["dc_rate"] = dc_rate.reindex(out.index).fillna(0.0)

    # A window is only scored on a full sample: fewer appearances than the
    # window is long and the player is not considered for that factor - no
    # star, and no vote in its median either.
    out["form_ok"] = out["appearances"] >= FORM_WINDOW
    out["minutes_factor_ok"] = out["appearances"] >= MINUTES_FACTOR_WINDOW
    out["justice_ok"] = out["appearances"] >= JUSTICE_WINDOW

    # Because every window counts appearances, nothing above can tell a
    # player who featured last week from one absent since October - both
    # carry the same numbers. This is not a factor, it is the caveat: how
    # many gameweeks ago the record was actually set.
    last_seen = apps.groupby("element")["round"].max()
    out["last_app_round"] = last_seen.reindex(out.index)
    out["gws_since_app"] = latest - out["last_app_round"]

    out["xg90"] = [_per90(g, m) for g, m in zip(out["xg"], out["minutes"])]
    out["xa90"] = [_per90(a, m) for a, m in zip(out["xa"], out["minutes"])]
    out["xgc90"] = [_per90(c, m) for c, m in zip(out["xgc"], out["minutes"])]
    out["saves90"] = [_per90(s, m) for s, m in zip(out["saves"], out["minutes"])]
    out["xpts90_raw"] = [
        expected_points_per_90(r.position, r.xg90, r.xa90, r.xgc90,
                               r.saves90, r.dc_rate)
        for r in out.itertuples()]

    # Sample-size shrinkage. A per-90 rate off 135 minutes is noise: it puts
    # bit-part players at the top of any per-90 ranking. Shrink each rate
    # toward its position's minutes-weighted mean, with a prior worth
    # PRIOR_MINUTES of evidence - so 450 minutes is half own-record, half
    # prior, and a 3,000-minute regular is essentially untouched.
    out["xpts90"] = out["xpts90_raw"]
    for pos in POSITIONS:
        grp = out["position"] == pos
        block = out.loc[grp]
        total = block["minutes"].sum()
        if not total:
            continue
        prior = (block["xpts90_raw"] * block["minutes"]).sum() / total
        mins = block["minutes"]
        out.loc[grp, "xpts90"] = (
            (mins * block["xpts90_raw"] + PRIOR_MINUTES * prior)
            / (mins + PRIOR_MINUTES))

    # Justice margin, in goals of unearned/withheld reward over the window:
    # attackers bank xGI they haven't cashed; defensive players bank goals
    # conceded beyond the xGC they actually faced. Defenders straddle both.
    jw = jw.reindex(out.index).fillna(0)
    attack_luck = (jw["expected_goals"] + jw["expected_assists"]
                   - jw["goals_scored"] - jw["assists"])
    defence_luck = jw["goals_conceded"] - jw["expected_goals_conceded"]
    pos = out["position"]
    out["justice_margin"] = (
        attack_luck.where(pos.isin(("MID", "FWD")), 0.0)
        + defence_luck.where(pos.isin(("GK", "DEF")), 0.0)
        + attack_luck.where(pos == "DEF", 0.0))

    out["through_gw"] = latest
    out["gws_used"] = len(rounds)
    return out.reset_index()


def price_residual(xpts90: pd.Series, price: pd.Series) -> tuple:
    """OLS of expected points on price; return (residuals, slope, r2).

    Dividing points by price barely reorders a position, because price
    varies far less than production does (defenders: 2.0x against 6.3x), so
    points-per-pound is very nearly points again. Regressing on price and
    ranking the *residual* asks the question value is meant to ask - who
    beats what his price predicts - and is orthogonal to quality by
    construction.
    """
    x, y = price.astype(float), xpts90.astype(float)
    var = ((x - x.mean()) ** 2).sum()
    if var == 0:                      # one price in the whole position
        return y - y.mean(), 0.0, 0.0
    slope = ((x - x.mean()) * (y - y.mean())).sum() / var
    resid = y - (y.mean() + slope * (x - x.mean()))
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - (resid ** 2).sum() / ss_tot if ss_tot else 0.0
    return resid, slope, r2


def rate_players(players: pd.DataFrame, preseason: bool = False) -> pd.DataFrame:
    """Score the six factors and the star rating for every eligible player.

    ``preseason=True`` switches three factors onto yardsticks that suit a
    board built from a finished season (see the constants above); the
    in-season path is untouched by it.
    """
    out = players.copy()
    for f in FACTORS:
        out[f] = 0
    out["stars"] = 0
    if preseason:
        out["value_resid"] = float("nan")
        out["minutes_share"] = float("nan")
        out["crowd_margin"] = float("nan")
        fits = {}

    for pos in POSITIONS:
        grp = out["eligible"] & (out["position"] == pos)
        if not grp.any():
            continue
        g = out.loc[grp]

        out.loc[grp, "quality"] = (g["xpts90"] > g["xpts90"].median()).astype(int)

        if preseason:
            # Value: beat the price curve, not the field.
            resid, slope, r2 = price_residual(g["xpts90"], g["price"])
            fits[pos] = (slope, r2, len(g))
            out.loc[grp, "value_resid"] = resid
            out.loc[grp, "value"] = (resid > resid.median()).astype(int)
        else:
            ppm = g["xpts90"] / g["price"]
            out.loc[grp, "value"] = (ppm > ppm.median()).astype(int)

        # Appearance-window factors: only players with a full sample are
        # considered, and only they set the median.
        form = grp & out["form_ok"]
        if form.any():
            median = out.loc[form, "form_points"].median()
            out.loc[form, "form"] = (out.loc[form, "form_points"]
                                     > median).astype(int)

        if preseason:
            # Minutes: share of a full season's minutes. Averaging the
            # minutes of matches he played cannot tell a 5-game starter from
            # a 38-game one; a share of the season can.
            share = g["minutes"] / TEAM_MINUTES
            out.loc[grp, "minutes_share"] = share
            out.loc[grp, "minutes_factor"] = (share >= share.median()).astype(int)
        else:
            # At-or-above for this factor only: whole positions (keepers
            # above all) sit at exactly 90 minutes, and a player averaging
            # the position's typical full-match load is precisely what
            # "nailed" means - a strict rule would star no goalkeeper at all.
            mins = grp & out["minutes_factor_ok"]
            if mins.any():
                median = out.loc[mins, "minutes_avg"].median()
                out.loc[mins, "minutes_factor"] = (out.loc[mins, "minutes_avg"]
                                                   >= median).astype(int)

        # Justice is measured against zero, not a median, but still needs a
        # full window to mean anything.
        just = grp & out["justice_ok"]
        out.loc[just, "justice"] = (out.loc[just, "justice_margin"] > 0).astype(int)

        quality_pct = g["xpts90"].rank(pct=True)
        owned_pct = g["selected"].rank(pct=True)
        if preseason:
            # Pre-season ownership below a couple of percent is
            # undifferentiated - 0.0 against 0.2 says nothing about
            # conviction - so require a real margin rather than any gap, and
            # only from players who actually played last season.
            margin = (quality_pct - owned_pct) * 100
            out.loc[grp, "crowd_margin"] = margin
            played = out.loc[grp, "minutes"] >= PRESEASON_MIN_MINUTES
            out.loc[grp, "crowd"] = ((margin >= PRESEASON_CROWD_MARGIN)
                                     & played).astype(int)
        else:
            out.loc[grp, "crowd"] = (owned_pct < quality_pct).astype(int)

    out["stars"] = out[list(FACTORS)].sum(axis=1)
    out["factor_letters"] = [
        "".join(FACTOR_LETTERS[f] for f in FACTORS if r[f])
        for _, r in out.iterrows()]
    # How many factors could be scored at all: 6 for a player with a full
    # sample, fewer for one short of an appearance window. Lets a report say
    # "3 of 4 assessed" rather than implying two factors were failed.
    # Pre-season, Minutes is a share of the season and needs no appearance
    # window, so only Form and Justice can be unassessable.
    windowed = ["form_ok", "justice_ok"] if preseason else [
        "form_ok", "minutes_factor_ok", "justice_ok"]
    out["factors_assessed"] = (
        len(FACTORS) - len(windowed)
        + sum(out[c].astype(int) for c in windowed))
    if preseason:
        out.attrs["price_fits"] = fits
    return out


def rate_season(data_dir: str | Path, through_gw: int | None = None) -> pd.DataFrame:
    """Load a season directory and return the rated player table."""
    return rate_players(player_table(load_season(data_dir), through_gw))


def recommendations(rated: pd.DataFrame, min_stars: int = 5) -> pd.DataFrame:
    """The weekly pick list: eligible players at ``min_stars``+ stars, by
    position, strongest first (stars, then quality engine)."""
    picks = rated[rated["eligible"] & (rated["stars"] >= min_stars)].copy()
    picks["position"] = pd.Categorical(picks["position"], POSITIONS)
    return picks.sort_values(["position", "stars", "xpts90"],
                             ascending=[True, False, False])
