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
2. Value    – in-season, expected points per 90 per million of price above
   the position median. Pre-season, the **leave-one-out residual** of
   expected points regressed on price: who beats what his price predicts,
   measured against a line fitted without him (see ``price_residual``).
3. Form     – total FPL points over the last 5 matches the player actually
   played, above the position median. Momentum.
4. Minutes  – average minutes over the last 5 matches the player actually
   played, at or above the position median (at-or-above, not strictly
   above: keepers all average 90, and averaging the position's typical
   full-match load is what "nailed" means). The 90-minute starters.
5. Justice  – expected goal involvements (xG + xA) over the last 8 matches
   the player actually played, above the position median. Chances created
   and taken up are the process behind attacking returns, and they persist
   where the returns themselves bounce around.

Every window counts the player's **own appearances**, not calendar
gameweeks, so a spell on the bench or in the treatment room shifts a
window back rather than filling it with zeros. The price of that is a
minimum sample: a player must have made at least as many appearances as
the window is long to be scored on it at all (5 for Form and Minutes, 8
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
JUSTICE_WINDOW = 8        # appearances of xGI behind the Justice factor
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
PRESEASON_CROWD_MARGIN = 5.0  # percentile points quality must beat ownership by
PRICE_BAND = 1.0              # width of a Crowd comparison group, in £m
MIN_BAND_N = 6                # merge a band holding fewer than this
CROWD_LAMBDA = 1.0            # points² of variance demanded per point of EV

# Which pre-season Crowd rule is live. "margin" is the percentile-gap test;
# "price_check" is the Aaron Brown Value structure in crowd_price_check.
# The price check is implemented and verified but does NOT pass its own
# acceptance list on 2025/26 data - see the README section "The Crowd price
# check, and why it is not live" before switching.
CROWD_MODE = "margin"

FACTORS = ("quality", "value", "form", "minutes_factor", "justice", "crowd")
FACTOR_LETTERS = {"quality": "Q", "value": "V", "form": "F",
                  "minutes_factor": "M", "justice": "J", "crowd": "C"}

# Crowd is scored in-season but **not pre-season**. Every other factor is an
# estimator of expected points; Crowd is a variance factor, and at equal
# weight on a pre-season board it pulls against the other five for an
# objective (win a ~40-person mini-league, or top 3) where the edge is
# already past the point at which variance helps. It stays fully computed -
# ``crowd``, ``crowd_marginrule``, ``crowd_pricecheck``, ``crowd_margin`` and
# their supporting columns are all still produced - and still renders as a
# diagnostic; it simply no longer feeds ``stars``. See the README section
# "Why Crowd is no longer scored pre-season".
PRESEASON_SCORING = ("quality", "value", "form", "minutes_factor", "justice")


def scoring_factors(preseason: bool = False) -> tuple:
    """The factors that feed the star count, which differs pre-season."""
    return PRESEASON_SCORING if preseason else FACTORS

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

    # Gameweek-to-gameweek spread of a player's points. Unused by the
    # in-season factors; it is the sigma in the pre-season Crowd price check.
    #
    # ``points_sd`` is measured over EVERY gameweek in the season, scoring a
    # non-appearance as 0, because the mu it is divided against
    # (xpts90 x minutes_share) is a season-basis per-gameweek figure. On the
    # appearance basis the two have different denominators and a deputy is
    # credited with a full-time player's volatility. ``points_sd_apps`` keeps
    # the appearance-basis figure for comparison; the two agree exactly for a
    # player who appeared in every gameweek.
    per_round = df.groupby(["element", "round"])["total_points"].sum()
    n_rounds = len(rounds)
    tot = per_round.groupby("element").sum()
    sumsq = (per_round ** 2).groupby("element").sum()
    mean_all = tot / n_rounds
    var_all = (sumsq - n_rounds * mean_all ** 2) / (n_rounds - 1)
    out["points_sd"] = (var_all.clip(lower=0) ** 0.5).reindex(out.index)
    out["points_sd_apps"] = (apps.groupby("element")["total_points"]
                             .std(ddof=1).reindex(out.index))

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

    # Justice: expected goal involvements over the last JUSTICE_WINDOW
    # appearances. xGI is summed from its components rather than read from
    # ``expected_goal_involvements``, which is rounded to 2dp per gameweek
    # and drifts from xG + xA by up to 0.01 over a window.
    jw = jw.reindex(out.index).fillna(0)
    out["justice_xgi"] = jw["expected_goals"] + jw["expected_assists"]

    # The previous "under-rewarded" formulation, kept as a diagnostic so the
    # two can be compared: attackers banked xGI they had not cashed,
    # defensive players banked goals conceded beyond the xGC they faced.
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


LEVERAGE_GUARD = 0.9   # above this h_ii, refuse to compute a LOO residual


def price_residual(xpts90: pd.Series, price: pd.Series) -> dict:
    """OLS of expected points on price, scored on leave-one-out residuals.

    Dividing points by price barely reorders a position, because price
    varies far less than production does (defenders: 2.0x against 6.3x), so
    points-per-pound is very nearly points again. Regressing on price and
    ranking the *residual* asks the question value is meant to ask - who
    beats what his price predicts - and is orthogonal to quality by
    construction.

    **Leave-one-out.** A high-leverage price point drags the fitted line
    through itself and so shrinks its own residual: the player grades his
    own line. Among 2026/27 forwards Haaland at £15.5m carries
    ``h_ii = 0.816`` against a mean of 0.100 and a next-highest of 0.094 -
    he sets the slope essentially alone, and his raw residual of +0.0063
    understates him badly. Fitted without him the same residual is +0.0342,
    which is all but exactly the other nineteen forwards' median of +0.0343.

    So each player is scored against a line fitted **without him**. For OLS
    that needs no refitting; the closed form is exact:

        e_loo_i = e_i / (1 - h_ii),   h_ii = 1/n + (x_i - x̄)² / Σ(x_j - x̄)²

    (verified against genuine refits for all 253 rated players, agreeing to
    3.5e-15).

    As ``h_ii -> 1`` the division diverges. Nothing currently comes close -
    0.816 is the maximum across all four positions - but a thin position in
    some future season could, so any player above ``LEVERAGE_GUARD`` is
    **flagged and left unscored** rather than divided: he takes no Value
    star and is excluded from the median, exactly as an unassessable player
    is treated elsewhere. Returns ``high_leverage`` so callers can surface
    it instead of failing silently.
    """
    x, y = price.astype(float), xpts90.astype(float)
    n = len(x)
    sxx = ((x - x.mean()) ** 2).sum()
    if sxx == 0 or n < 3:             # one price, or too few to leave one out
        zero = y - y.mean() if sxx == 0 else y * 0.0
        return {"loo": zero, "raw": zero, "leverage": pd.Series(1.0 / max(n, 1),
                index=x.index), "slope": 0.0, "r2": 0.0,
                "high_leverage": pd.Series(False, index=x.index)}

    slope = ((x - x.mean()) * (y - y.mean())).sum() / sxx
    raw = y - (y.mean() + slope * (x - x.mean()))
    h = 1.0 / n + (x - x.mean()) ** 2 / sxx
    flagged = h > LEVERAGE_GUARD
    loo = (raw / (1.0 - h)).where(~flagged)
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - (raw ** 2).sum() / ss_tot if ss_tot else 0.0
    return {"loo": loo, "raw": raw, "leverage": h, "slope": slope, "r2": r2,
            "high_leverage": flagged}


def merge_bands(prices: pd.Series, width: float = PRICE_BAND,
                min_n: int = MIN_BAND_N) -> pd.Series:
    """Assign each price to a band label, merging any band under ``min_n``.

    Bands are ``width``-wide price buckets. A thin band is merged **upward**
    into the next band above it; the top band has nothing above, so if it is
    still thin it merges downward. Repeats until every band is big enough or
    only one remains.
    """
    floors = sorted((prices // width * width).unique())
    groups = [[f] for f in floors]

    changed = True
    while changed and len(groups) > 1:
        changed = False
        sizes = [int(prices.isin([p for p in prices.unique()
                                  if (p // width * width) in g]).sum())
                 for g in groups]
        for k, n in enumerate(sizes):
            if n >= min_n:
                continue
            j = k + 1 if k + 1 < len(groups) else k - 1   # up, else down
            lo, hi = min(k, j), max(k, j)
            groups[lo] = groups[lo] + groups[hi]
            groups.pop(hi)
            changed = True
            break

    label = {}
    for g in groups:
        lo, hi = min(g), max(g)
        name = (f"£{lo:.1f}m+" if hi != lo and hi == max(floors)
                else f"£{lo:.1f}–{hi + width - 0.1:.1f}m" if hi != lo
                else f"£{lo:.1f}–{lo + width - 0.1:.1f}m")
        for f in g:
            label[f] = name
    return (prices // width * width).map(label)


def crowd_price_check(block: pd.DataFrame, lam: float = CROWD_LAMBDA) -> pd.DataFrame:
    """Aaron Brown's Value test, applied to one comparison group.

    Baseline is the **favourite**: the highest expected points in the group.
    Deviating from him costs expected points and buys variance against the
    field; the star fires only when the variance bought is worth at least
    ``lam`` points² per point of expected score given up.

    With ``Y = Z_i − Z_rival``, where a rival's squad holds each player j
    independently with probability ``f_j`` — his **raw** ownership, not a
    share of the group. The bracket normalises (Σf = 1) because every entry
    picks exactly one team per slot; FPL has no such constraint, since a
    manager may hold several players from one position-and-price band or
    none, and ownership already *is* the probability his squad contains a
    given player. Normalising would rescale it into a quantity the game
    does not have.

        Cov(Z_i, Z_rival) = f_i σ_i²    (the rival holds i with prob f_i)
        Var(Y_i) = σ_i²(1 − 2f_i) + K,  K = Σⱼ[fⱼ(σⱼ² + μⱼ²) − fⱼ²μⱼ²]

    ``K`` is a group constant, so it cancels in the difference:

        ΔEV  = μ_i − μ₀
        ΔVar = σ_i²(1 − 2f_i) − σ₀²(1 − 2f₀)

    ``−2f_i σ_i²`` is the engine, exactly as ``−2pf`` is in the bracket: a
    volatile player nobody owns creates spread, while a placid unowned one
    buys nothing and still costs expected points.

    Sign convention: ΔEV is **negative** for every non-favourite, so dividing
    flips the inequality and the test is ``ratio ≤ −lam``, never
    ``ratio ≥ lam``. (Testing the latter is the published workbook's second
    bug, which fires for picks that shed variance faster than they shed EV.)
    """
    out = block.copy()
    f = out["eo"] / 100.0        # raw ownership as a probability; see above
    out["f_raw"] = f

    # Variance the player generates WHEN HE PLAYS, prorated by how often he
    # played: var_eff = q·s², q = appearances/38, s = SD over appearances.
    #
    # The full-season SD also carries a q(1−q)m² term - the on/off swing of
    # being in and out of the side. That is minutes risk, which the Minutes
    # factor already punishes, and it peaks at q = ½, so it pays a
    # half-season deputy the most. A differential should be paid only for
    # the variance a player creates on the pitch. ``points_sd`` keeps the
    # full-season figure alongside for comparison.
    out["var_eff"] = out["q_play"] * out["points_sd_apps"] ** 2
    swing = out["var_eff"] * (1 - 2 * f)

    fav = out["mu"].idxmax()
    out["is_favourite"] = out.index == fav
    out["delta_ev"] = out["mu"] - out.at[fav, "mu"]
    out["delta_var"] = swing - swing.at[fav]
    # The favourite's ΔEV is 0; leave his ratio undefined rather than
    # dividing, and star him on the is_favourite flag instead.
    ratio = out["delta_var"] / out["delta_ev"].where(out["delta_ev"] != 0)
    out["ratio"] = ratio
    out["crowd"] = (out["is_favourite"] | (ratio <= -lam)).astype(int)
    return out


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
        out["value_resid_raw"] = float("nan")
        out["price_leverage"] = float("nan")
        out["value_high_leverage"] = False
        out["minutes_share"] = float("nan")
        for c in ("mu", "eo", "f_raw", "q_play", "var_eff", "delta_ev",
                  "delta_var", "ratio",
                  "crowd_margin", "crowd_pricecheck"):
            out[c] = float("nan")
        out["price_band"] = ""
        out["is_favourite"] = False
        fits = {}

    for pos in POSITIONS:
        grp = out["eligible"] & (out["position"] == pos)
        if not grp.any():
            continue
        g = out.loc[grp]

        out.loc[grp, "quality"] = (g["xpts90"] > g["xpts90"].median()).astype(int)

        if preseason:
            # Value: beat the price curve, not the field - and beat a line
            # fitted without you, so nobody grades his own line.
            fit = price_residual(g["xpts90"], g["price"])
            fits[pos] = (fit["slope"], fit["r2"], len(g),
                         float(fit["leverage"].max()),
                         int(fit["high_leverage"].sum()))
            out.loc[grp, "value_resid"] = fit["loo"]
            out.loc[grp, "value_resid_raw"] = fit["raw"]
            out.loc[grp, "price_leverage"] = fit["leverage"]
            out.loc[grp, "value_high_leverage"] = fit["high_leverage"]
            # A flagged player is unscored, not zero-scored: no star, and no
            # vote in the median either.
            scored = grp & ~out["value_high_leverage"].fillna(False)
            if scored.any():
                median = out.loc[scored, "value_resid"].median()
                out.loc[scored, "value"] = (out.loc[scored, "value_resid"]
                                            > median).astype(int)
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

        # Justice: expected goal involvements over the window, median cut
        # within position like Quality, Value and Form. Needs a full window
        # to be scored at all.
        just = grp & out["justice_ok"]
        if just.any():
            median = out.loc[just, "justice_xgi"].median()
            out.loc[just, "justice"] = (out.loc[just, "justice_xgi"]
                                        > median).astype(int)

        if not preseason:
            quality_pct = g["xpts90"].rank(pct=True)
            owned_pct = g["selected"].rank(pct=True)
            out.loc[grp, "crowd"] = (owned_pct < quality_pct).astype(int)

    if preseason:
        # Both pre-season Crowd rules are computed so the page and the
        # changelog can show either; CROWD_MODE picks which one scores.
        out["mu"] = out["xpts90"] * out["minutes_share"]
        out["eo"] = out["selected"]           # effective ownership (see docs)
        out["q_play"] = out["appearances"] / (TEAM_MINUTES / 90)
        bands = {}
        for pos in POSITIONS:
            grp = out["eligible"] & (out["position"] == pos)
            if not grp.any():
                continue
            g = out.loc[grp]
            margin = (g["xpts90"].rank(pct=True)
                      - g["selected"].rank(pct=True)) * 100
            out.loc[grp, "crowd_margin"] = margin

            out.loc[grp, "price_band"] = merge_bands(
                out.loc[grp, "price"], PRICE_BAND, MIN_BAND_N)
            for band, block in out.loc[grp].groupby("price_band"):
                scored = crowd_price_check(block, CROWD_LAMBDA)
                for col in ("f_raw", "var_eff", "is_favourite", "delta_ev", "delta_var",
                            "ratio"):
                    out.loc[scored.index, col] = scored[col]
                out.loc[scored.index, "crowd_pricecheck"] = scored["crowd"]
                bands[(pos, band)] = len(block)

        out["crowd_pricecheck"] = out["crowd_pricecheck"].fillna(0).astype(int)
        out["crowd_marginrule"] = (
            (out["crowd_margin"] >= PRESEASON_CROWD_MARGIN)
            & out["eligible"]).fillna(False).astype(int)
        out["crowd"] = (out["crowd_pricecheck"] if CROWD_MODE == "price_check"
                        else out["crowd_marginrule"])
        out.attrs["crowd_bands"] = bands
        out.attrs["crowd_mode"] = CROWD_MODE

    scored = scoring_factors(preseason)
    out["stars"] = out[list(scored)].sum(axis=1)
    # Letters cover the scored factors only; any factor that is computed but
    # unscored (pre-season Crowd) is exposed separately so the page can show
    # it as a diagnostic without implying it earned a star.
    out["factor_letters"] = [
        "".join(FACTOR_LETTERS[f] for f in scored if r[f])
        for _, r in out.iterrows()]
    unscored = [f for f in FACTORS if f not in scored]
    out["diagnostic_letters"] = [
        "".join(FACTOR_LETTERS[f] for f in unscored if r[f])
        for _, r in out.iterrows()]
    # How many factors could be scored at all: 6 for a player with a full
    # sample, fewer for one short of an appearance window. Lets a report say
    # "3 of 4 assessed" rather than implying two factors were failed.
    # Pre-season, Minutes is a share of the season and needs no appearance
    # window, so only Form and Justice can be unassessable.
    windowed = ["form_ok", "justice_ok"] if preseason else [
        "form_ok", "minutes_factor_ok", "justice_ok"]
    out["factors_assessed"] = (
        len(scored) - len(windowed)
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
