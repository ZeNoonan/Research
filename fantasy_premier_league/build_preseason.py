"""Generate the pre-season draft board for the new season.

Writes ``preseason.html``: the new season's price list rated on last
season's evidence — pick lists by position, the summer's price moves, the
best points-per-pound, per-factor leaderboards with the median cut line,
and the players with no Premier League history to rate.

    python build_preseason.py                       # 2026-27 vs 2025-26
    python build_preseason.py --listing data/2027-28/player_listing.csv \
                              --history data/2026-27
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import model
import preseason
from build_site import CSS, _leaderboard_table, esc
from weekly_report import POSITION_NAMES

HERE = Path(__file__).parent

# The squad places a manager typically fills himself: a bench keeper and a
# bench forward at the floor price. The page renders the model's answer for
# what to do with the rest of the budget.
FILL_SLOTS = [("GK", 4.0), ("FWD", 4.5)]

FACTOR_ROWS = [
    ("Q", "Quality", "Model expected points per 90 — rebuilt from the FPL "
     "scoring rules and last season's underlying per-90 numbers — above the "
     "position median. Rates are shrunk toward the position average by "
     "sample size, so a big number off a handful of substitute appearances "
     "last season doesn't outrank a full campaign."),
    ("V", "Value", "Expected points per 90 <b>above what his price "
     "predicts</b>. Within each position the model fits a straight line of "
     "expected points against price; Value ranks the residual, and stars the "
     "top half. Dividing points by price — the obvious move — barely "
     "reorders a position, because price varies about 2× while production "
     "varies about 6×, so it just re-states Quality. The residual asks the "
     "question Value is for: who beats his price tag. Each player is scored "
     "against a line fitted <b>without him</b> (leave-one-out), so an "
     "isolated price cannot drag the line through itself and erase its own "
     "residual — without that, Haaland at £15.5m sets the forwards' slope "
     "almost single-handedly and grades himself down to nothing."),
    ("F", "Form", "Points over the <b>last 5 matches he actually played</b> "
     "last season (needs 5 appearances). The weakest signal here — three "
     "months stale, and a summer of transfers in between."),
    ("M", "Minutes", "Minutes played last season as a <b>share of the full "
     "3,420</b> available, at or above the position median — who was on the "
     "pitch, not who happened to play 90 minutes on the days he was picked. "
     "(Averaging the minutes of matches he played cannot tell a five-game "
     "starter from a thirty-eight-game one.)"),
    ("N", "Nailed", "The same share, at or above "
     f"<b>{model.NAILED_SHARE:.0%}</b> of the season — roughly 28 full "
     "matches. Minutes' second star, and an <b>absolute</b> bar rather than "
     "a position rank: three quarters of the minutes means the same thing "
     "for a keeper as for a forward, which is not true of a rate statistic. "
     "Minutes is worth two stars because season points are a per-90 rate "
     "<i>times</i> minutes played, and minutes are the more variable of the "
     "two — a single median cut cannot separate a player on 61% of the "
     "minutes from one on 97%."),
    ("J", "Justice", "<b>Expected goal involvements</b> (xG + xA) over the "
     "last 8 matches he actually played last season, above the position "
     "median (needs 8 appearances). Chances made and got on the end of are "
     "the process behind attacking returns, and they persist where the "
     "returns themselves bounce around."),
]

# Computed and displayed, but not counted toward the star rating.
DIAGNOSTIC_ROWS = [
    ("C", "Crowd", "Quality percentile exceeding ownership percentile <b>by "
     f"at least {model.PRESEASON_CROWD_MARGIN:.0f} points</b> — the field is "
     "materially underweight. <b>Unscored:</b> every other factor estimates "
     "expected points, this one estimates variance, and variance only pays a "
     "manager who is behind. Kept as a tie-breaker to apply by eye between "
     "players the board already rates alike."),
]


def picks_table(block, n_factors: int) -> str:
    """Every rated player in one position, strongest first, banded by stars."""
    rows, band = [], None
    for r in block.itertuples():
        if r.stars != band:
            band = r.stars
            if band == 0:
                label = "no factors — rated, but below every median"
            elif band == n_factors:
                label = f"{band}★ — all {n_factors} factors"
            else:
                label = f"{band}★ — {band} of {n_factors} factors"
            rows.append(f"<tr class='divider'><td colspan='7'>{label}</td></tr>")
        move = ""
        if abs(r.price_change) >= 0.05:
            cls = "up" if r.price_change > 0 else "down"
            move = f" <span class='{cls}'>{r.price_change:+.1f}</span>"
        note = (f"<br><span class='sub2'>from {esc(r.last_team)}</span>"
                if r.moved else "")
        if r.unavailable:
            note += (f"<br><span class='stale'>{esc(r.unavailable_status)} — "
                     "not selectable</span>")
        letters = (f"<span class='letters'>{esc(r.factor_letters)}</span>"
                   if r.factor_letters else "<span class='sub2'>—</span>")
        if r.diagnostic_letters:
            # Visually distinct so an unscored letter cannot be mistaken for
            # a star: hollow, muted, and separated by a middot.
            letters += (f" <span class='letters diag' title='diagnostic only "
                        f"— not counted in the star rating'>"
                        f"{esc(r.diagnostic_letters)}</span>")
        rows.append(
            f"<tr><td><span class='stars'>{'★' * r.stars}</span></td>"
            f"<td>{esc(r.name)}{note}</td><td>{esc(r.team)}</td>"
            f"<td class='num'>£{r.price:.1f}m{move}</td>"
            f"<td class='num'>{r.owned_pct:.1f}%</td>"
            f"<td>{letters}</td>"
            f"<td class='num'>{r.xpts90:.2f}</td></tr>")
    head = ("<tr><th>Stars</th><th>Player</th><th>Team</th>"
            "<th class='num'>Price</th><th class='num'>Owned</th>"
            "<th>Factors</th><th class='num'>xPts/90</th></tr>")
    return f"<div class='tablewrap'><table>{head}{''.join(rows)}</table></div>"


def squads_html(listing_path, history_dir, n_factors: int,
                n_rated: int) -> str:
    """Two optimal 15-man squads: the board's, and the crowd's."""
    import squad
    factor, crowd = squad.build(listing_path, history_dir)

    def table(sq, by, captain_by, cols):
        rows = []
        xi = sq[sq["xi"]]
        cap = xi.nlargest(2, captain_by)
        cap_names = {cap.iloc[0]["name"]: "C", cap.iloc[-1]["name"]: "V"}
        started = False
        for r in squad._order(sq, by).itertuples():
            if not r.xi and not started:
                started = True
                rows.append("<tr class='divider'><td colspan='6'>bench</td></tr>")
            band = cap_names.get(r.name, "")
            badge = (f" <span class='letters'>{band}</span>") if band else ""
            rows.append(
                f"<tr><td>{esc(r.position)}</td>"
                f"<td>{esc(r.name)}{badge}</td><td>{esc(r.team)}</td>"
                f"<td class='num'>£{r.price:.1f}m</td>"
                + "".join(f"<td class='num'>{fn(r)}</td>" for _, fn in cols)
                + "</tr>")
        head = ("<tr><th>Pos</th><th>Player</th><th>Team</th>"
                "<th class='num'>Price</th>"
                + "".join(f"<th class='num'>{h}</th>" for h, _ in cols)
                + "</tr>")
        return f"<div class='tablewrap'><table>{head}{''.join(rows)}</table></div>"

    def shape(sq):
        xi = sq[sq["xi"]]
        return "-".join(str(int((xi["position"] == p).sum()))
                        for p in ("DEF", "MID", "FWD"))

    # A third squad: the manager fills the two cheap dead slots himself and
    # the model spends what is left. Rendered for the configuration in
    # FILL_SLOTS so the page shows the same thing `squad.py --fill` prints.
    fill = squad.build_fill(listing_path, history_dir, FILL_SLOTS)
    fill_holders = fill.attrs["placeholders"]
    fill_mine = fill[~fill.index.isin(fill_holders)]
    fill_xi = fill[fill["xi"]]
    fill_capt = fill_xi.nlargest(1, "xpts90").iloc[0]

    f_tbl = table(factor, "stars", "xpts90",
                  [("Stars", lambda r: "★" * int(r.stars)),
                   ("Factors", lambda r: f"<span class='letters'>{esc(r.factor_letters)}</span>"),
                   ("xPts/90", lambda r: f"{r.xpts90:.2f}"),
                   ("Owned", lambda r: f"{r.owned_pct:.1f}%")])
    c_tbl = table(crowd, "owned_pct", "owned_pct",
                  [("Owned", lambda r: f"{r.owned_pct:.1f}%")])
    overlap = sorted(set(factor["name"]) & set(crowd["name"]))

    # Whether the star objective still discriminates. At the ceiling it does
    # not, and the tie-break is choosing the team - which the reader should
    # be told, since it changes what the squad is evidence of.
    sat = factor.attrs.get("saturation") or {}
    ceiling = sat.get("ceiling", len(factor) * n_factors)
    if sat.get("saturated"):
        breakdown = "; ".join(
            f"{pos} {'+'.join(str(int(v)) for v in vals)}"
            for pos, vals in sat["per_position"].items())
        sat_note = f"""
<p class='note' style='border-left:3px solid var(--star);padding-left:10px'>
<b>The star objective is saturated.</b> {ceiling} is the most any legal
2/5/5/3 could score given who is available ({breakdown}) — and the squad
reaches it, so neither the budget nor the 3-per-club cap is what stopped
it. Every legal fifteen at {ceiling} ties on stars, which means the
<b>tie-break is picking the team</b>: projected season points
(<code>xPts/90 × minutes share × 38</code>). Read the fifteen as "the
highest-projecting squad among those tied at the star ceiling", not as a
uniquely optimal one. Note there is no six-star goalkeeper on the whole
board, which is where two of the six missing stars go.</p>"""
    else:
        sat_note = ""

    out_list = preseason.load_unavailable(Path(listing_path).parent
                                          / "unavailable.csv")
    if len(out_list):
        had, _ = squad.build(listing_path, history_dir,
                                 respect_availability=False)
        dropped = sorted(set(had["name"]) - set(factor["name"]))
        gained = sorted(set(factor["name"]) - set(had["name"]))
        names = ", ".join(f"<b>{esc(n)}</b> ({esc(s)})" for n, s
                          in zip(out_list["name"], out_list["status"]))
        unavail = f"""
<p class='note' style='border-left:3px solid #b3372f;padding-left:10px'>
<b>Ruled out and excluded from both squads:</b> {names}. They are still
rated on the board above — an injury does not change what a player is
worth — but they cannot be picked, and both squads below are built
without them. It costs the factor squad
{int(had['stars'].sum()) - int(factor['stars'].sum())}
star{'' if int(had['stars'].sum()) - int(factor['stars'].sum()) == 1 else 's'}
({int(had['stars'].sum())} → {int(factor['stars'].sum())}): out go
{', '.join(esc(n) for n in dropped)}; in come
{', '.join(esc(n) for n in gained)}.</p>"""
    else:
        unavail = ""

    return f"""<section id="squads"><h2>Two squads</h2>
<p class='note'>Both are legal and <b>solved exactly</b> (integer program,
not a greedy pick): £100.0m, 2 GK / 5 DEF / 5 MID / 3 FWD, at most 3 from
one club, and a starting XI in a legal formation. <b>C</b> and <b>V</b> mark
captain and vice — on expected points, since captaincy doubles a score.</p>
{unavail}

<h3 style='font-size:16px;margin:16px 0 4px'>The factor squad — the board's
own answer</h3>
<p class='note'>Maximises total stars ({int(factor['stars'].sum())} of a
reachable {ceiling}), ties broken on projected season points.
Drawn from the {n_rated} rated players, plus — for a benched forward only —
the unrated ones at £{squad.BENCH_FWD_MAX_PRICE:.1f}m or less. Three
forwards are compulsory but only one has to start, so the third is a dead
spot; a forward dearer than that cap must be in the eleven if he is bought
at all, which stops the squad paying for a player it has already decided
not to field. Formation {shape(factor)}, spending
£{factor['price'].sum():.1f}m.</p>
{sat_note}
{f_tbl}

<h3 style='font-size:16px;margin:16px 0 4px'>The crowd squad — what the
field is holding</h3>
<p class='note'>Maximises total ownership
({crowd['owned_pct'].sum():.0f} percentage points across 15 players).
Drawn from <b>every</b> listed player, not just the rated ones: about 240
points of ownership sit with players this board cannot rate — promoted-club
squads, new signings, and regulars who fell under the minutes gate — and
leaving them out would misrepresent the crowd. Formation {shape(crowd)},
spending £{crowd['price'].sum():.1f}m.</p>
{c_tbl}

<h3 style='font-size:16px;margin:16px 0 4px'>The fill squad — you pick the
cheap slots, the model spends the rest</h3>
<p class='note'>Most managers fill the two dead places themselves — a
bench keeper and a bench forward at the floor price — and want the model to
spend what is left. Here that is
{", ".join(f"a <b>{p} at £{pr:.1f}m</b>" for p, pr in FILL_SLOTS)},
reserving £{sum(pr for _, pr in FILL_SLOTS):.1f}m and leaving
<b>£{100.0 - sum(pr for _, pr in FILL_SLOTS):.1f}m</b> for the other
{len(fill_mine)}. Chosen on <b>projected points</b>, not stars, and solved
as the whole fifteen rather than as a detached thirteen — the budget, the
2/5/5/3 shape, the three-per-club cap and the eleven/bench split are all
properties of the full squad. Your two slots enter as scoreless
placeholders, so they take a position and a price and are never started.
Formation {shape(fill)}, captain {esc(fill_capt['name'])}, projected
<b>{fill_xi['xpts_season'].sum() + fill_capt['xpts_season']:.0f}</b> points
with the captain doubled.</p>
{table(fill, "xpts_season", "xpts90",
       [("Stars", lambda r: "★" * int(r.stars) if r.rated else "—"),
        ("Factors", lambda r: f"<span class='letters'>{esc(r.factor_letters)}</span>"
                              if r.factor_letters else "<span class='sub2'>you pick</span>"),
        ("xPts/90", lambda r: f"{r.xpts90:.2f}" if r.rated else "—"),
        ("Projected", lambda r: f"{r.xpts_season:.0f}" if r.rated else "—")])}
<p class='note'>Reproduce with
<code>python squad.py --fill "{','.join(f'{p}:{pr:.1f}' for p, pr in FILL_SLOTS)}"</code>,
or pass your own slots.</p>

<p class='note'><b>They share {len(overlap)} of 15 players</b>
({', '.join(esc(n) for n in overlap)}). That is the point of the exercise:
the board and the field agree on almost nobody. The factor squad is built
on last season's underlying numbers and buys minutes and chance creation
cheaply — seven of its fifteen are owned by under 2% of managers, five of
them starters. The crowd
squad is concentrated in the expensive, well-known end. Whether that gap is
edge or blind spot is exactly what a season settles.</p>
</section>"""


def leaderboards_html(rated) -> str:
    """Per-factor sorted leaderboards with the cut line, pre-season factors."""
    elig = rated[rated["eligible"]].copy()
    elig["ppm"] = elig["xpts90"] / elig["price"]
    # The two percentiles behind crowd_margin, for display. (Their difference
    # reproduces the margin the model scored; asserted in build().)
    for pos in model.POSITIONS:
        grp = elig["position"] == pos
        elig.loc[grp, "xpts90_pct"] = elig.loc[grp, "xpts90"].rank(pct=True) * 100
        elig.loc[grp, "selected_pct"] = elig.loc[grp, "selected"].rank(pct=True) * 100

    def med(block, col, fmt):
        return format(block[col].median(), fmt)

    specs = [
        ("quality", "Q", "Quality — sorted by model xPts/90", "xpts90",
         [("xPts/90", lambda r: f"{r.xpts90:.2f}")],
         lambda b: f"median xPts/90 = {med(b, 'xpts90', '.2f')} — "
                   "star above this line"),
        ("value", "V",
         "Value — sorted by expected points above what the price predicts "
         "(leave-one-out)",
         "value_resid",
         [("Price", lambda r: f"£{r.price:.1f}m"),
          ("xPts/90", lambda r: f"{r.xpts90:.2f}"),
          ("Price predicts", lambda r: f"{r.xpts90 - r.value_resid_raw:.2f}"),
          ("Leverage", lambda r: f"{r.price_leverage:.3f}"),
          ("Residual (LOO)", lambda r: f"{r.value_resid:+.3f}")],
         lambda b: f"median residual = {med(b, 'value_resid', '+.3f')} — "
                   "star above this line"),
        ("form", "F", "Form — sorted by points over the last 5 matches played",
         "form_points",
         [("Last-5 pts", lambda r: f"{r.form_points:.0f}")],
         lambda b: f"median = {med(b, 'form_points', '.0f')} points — "
                   "star above this line"),
        ("minutes_factor", "M",
         "Minutes — sorted by share of the season's 3,420 minutes played",
         "minutes_share",
         [("Minutes", lambda r: f"{r.minutes:.0f}"),
          ("Share of season", lambda r: f"{r.minutes_share * 100:.0f}%")],
         lambda b: f"median = {b['minutes_share'].median() * 100:.0f}% of the "
                   "season — star at or above this line"),
        ("minutes_nailed", "N",
         "Nailed — the same share, against an absolute three-quarter bar",
         "minutes_share",
         [("Share of season", lambda r: f"{r.minutes_share * 100:.0f}%")],
         lambda b: f"{model.NAILED_SHARE:.0%} of the season — star at or "
                   "above this line, the same bar for every position"),
        ("justice", "J",
         "Justice — sorted by xGI over the last 8 matches played",
         "justice_xgi",
         [("xGI (last 8)", lambda r: f"{r.justice_xgi:.2f}")],
         lambda b: f"median xGI = {med(b, 'justice_xgi', '.2f')} — "
                   "star above this line"),
        ("crowd", "C",
         "Crowd — <b>diagnostic only, not counted in the star rating</b> "
         "(demoted: it estimates variance, not expected points, and it has "
         "no quality floor) — sorted by quality minus ownership percentile",
         "crowd_margin",
         [("Owned", lambda r: f"{r.owned_pct:.1f}%"),
          ("Quality pct", lambda r: f"{r.xpts90_pct:.0f}"),
          ("Owned pct", lambda r: f"{r.selected_pct:.0f}"),
          ("Margin", lambda r: f"{r.crowd_margin:+.0f}")],
         lambda b: f"margin of {model.PRESEASON_CROWD_MARGIN:.0f} points — "
                   "star at or above this line"),
    ]

    out = ["<section id='leaderboards'><h2>Factor leaderboards — "
           "who is above the line</h2>",
           "<p class='note'>Every rated player, sorted highest to lowest on "
           "each factor's yardstick, position by position. The purple line is "
           "the cut: tinted rows above it earn that factor's star. Tap a "
           "position to open it. The three appearance-window factors list "
           "only players with a full sample last season — the others are not "
           "considered, so they are not ranked here either.</p>"]
    for factor, letter, title, sort_col, cols, divider_fn in specs:
        out.append(f"<h3 style='font-size:16px;margin:16px 0 4px'>"
                   f"<span class='letters'>{letter}</span> {title}</h3>")
        for pos in model.POSITIONS:
            block = elig[elig["position"] == pos].copy()
            ok_col = f"{factor}_ok"
            if ok_col in block.columns:
                block = block[block[ok_col]]
            if block.empty:
                continue
            block = block.sort_values([factor, sort_col],
                                      ascending=[False, False])
            n_star = int(block[factor].sum())
            out.append(
                f"<details><summary>{POSITION_NAMES[pos]} "
                f"({n_star} of {len(block)} starred)</summary>"
                f"{_leaderboard_table(block, factor, cols, divider_fn(block))}"
                f"</details>")
    out.append("</section>")
    return "".join(out)


def build(listing_path: Path, history_dir: Path, out: Path,
          season: str, history_season: str) -> None:
    rated, unrated = preseason.rate_preseason(listing_path, history_dir)
    factors = rated.attrs["factors"]
    n_factors = len(factors)
    top_band = n_factors - 1  # "4★ or better" of 5; "5★ or better" of 6
    elig = rated[rated["eligible"]]
    board = elig.sort_values(["stars", "xpts90"], ascending=[False, False])

    sections = []
    for pos in model.POSITIONS:
        block = board[board["position"] == pos]
        n_top = int((block["stars"] >= top_band).sum())
        body = (picks_table(block, n_factors) if not block.empty
                else "<p class='note'>No rated players in this position.</p>")
        sections.append(
            f"<section><h2>{POSITION_NAMES[pos]}</h2>"
            f"<p class='note'>All <b>{len(block)}</b> rated "
            f"{POSITION_NAMES[pos].lower()}, strongest first — "
            f"{n_top} at {top_band}★ or better.</p>{body}</section>")

    value = elig.copy()
    value["ppm"] = value["xpts90"] / value["price"]
    best_value = value.nlargest(12, "ppm")
    value_rows = "".join(
        f"<tr><td>{esc(r.name)}</td><td>{esc(r.position)}</td>"
        f"<td>{esc(r.team)}</td><td class='num'>£{r.price:.1f}m</td>"
        f"<td class='num'>{r.owned_pct:.1f}%</td>"
        f"<td class='num'>{r.xpts90:.2f}</td>"
        f"<td class='num'><b>{r.ppm:.3f}</b></td>"
        f"<td><span class='stars'>{'★' * r.stars}</span></td></tr>"
        for r in best_value.itertuples())

    by_team = unrated.groupby("team").size().sort_values(ascending=False)
    unrated_rows = "".join(
        f"<tr><td>{esc(team)}</td><td class='num'>{n}</td></tr>"
        for team, n in by_team.items())

    # Matched to a record, cleared the recency check, but under the absolute
    # minutes bar. These are the players the new gate specifically costs, so
    # name them rather than letting them vanish.
    gated = rated[~rated["eligible"]
                  & (rated["gate_minutes"] >= model.MINUTES_PER_GW)].copy()
    gated = gated.sort_values("minutes", ascending=False)
    gated_rows = "".join(
        f"<tr><td>{esc(r.name)}</td><td>{esc(r.position)}</td>"
        f"<td>{esc(r.team)}</td><td class='num'>{r.minutes:.0f}</td>"
        f"<td class='num'>{r.appearances:.0f}</td>"
        f"<td class='num'>{r.owned_pct:.1f}%</td></tr>"
        for r in gated.itertuples())

    factor_rows = "".join(
        f"<tr><td><span class='letters'>{l}</span></td><td><b>{n}</b></td>"
        f"<td style='white-space:normal'>{d}</td></tr>"
        for l, n, d in FACTOR_ROWS)
    factor_rows += "".join(
        f"<tr class='diagrow'><td><span class='letters diag'>{l}</span></td>"
        f"<td><b>{n}</b> <span class='sub2'>— not scored</span></td>"
        f"<td style='white-space:normal'>{d}</td></tr>"
        for l, n, d in DIAGNOSTIC_ROWS)

    n_matched = len(rated)
    n_total = n_matched + len(unrated)

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FPL {esc(season)} pre-season draft board</title>
<style>{CSS}
.up {{ color: #b3372f; font-weight: 600; }}
.down {{ color: #1e7d46; font-weight: 600; }}
.sub2 {{ color: var(--muted); font-size: 12px; }}
.letters.diag {{ background: transparent; border: 1px dashed var(--border);
  color: var(--muted); font-style: italic; }}
tr.diagrow td {{ background: rgba(128,128,128,.07); }}
.two {{ display: grid; grid-template-columns: 1fr; gap: 12px; }}
@media (min-width: 720px) {{ .two {{ grid-template-columns: 1fr 1fr; }} }}
@media (prefers-color-scheme: dark) {{
  .up {{ color: #ef7a72; }} .down {{ color: #4cc38a; }}
}}
</style></head><body><div class="wrap">
<header><h1>FPL {esc(season)} — pre-season draft board</h1>
<p class="sub">The new season's price list rated on last season's evidence.
Same additive binary-factor model as the in-season app, one star per factor
(two for Minutes), judged against position peers.</p></header>
<div class="banner">Prices: <b>{esc(season)}</b> · Evidence:
<b>{esc(history_season)}</b>. {n_matched} of {n_total} listed players matched
to a {esc(history_season)} record, <b>{len(elig)}</b> of them with enough
minutes to rate — all shown below, by position. Ratings are out of
<b>{n_factors} stars</b> — Quality, Value, Form, Minutes, Nailed and
Justice, all of them estimators of expected points. Minutes is asked twice
(above the position median, then above an absolute three-quarter bar)
because it is the term season points vary most with. Crowd is computed and
shown as a diagnostic but no longer scored.
<a href="index.html" style="color:var(--accent2)">In-season app →</a></div>

<section><h2>Read this first</h2>
<p class="note">Every number here comes from <b>{esc(history_season)}</b>.
That is the only evidence available before a ball is kicked, and it is
genuinely weaker than in-season data: it cannot see pre-season friendlies,
new signings settling, managerial changes or injuries. Two things it does
do well — it prices last season's underlying performance against
<b>this season's money</b>, and it says who was actually playing.</p>
<p class="note"><b>Ownership is no longer scored.</b> Crowd — how far the
field underweights a player relative to his quality — used to be a scoring
star. It has been demoted to a <b>diagnostic</b>: still computed, still
shown, but no longer counted. The other factors all estimate expected
points; Crowd estimates <i>variance</i>, and at equal weight it was pulling
against them. Variance only helps a manager who is behind, and for a
mini-league of about forty this board's user is not — so the factor's sign
was wrong for the objective. It also had no quality floor, starring 28
players who sat below their position's median quality. Where it still
earns its place is as a tie-breaker you apply by eye: among two players the
board rates alike, the less-owned one moves you further if he comes off.
Its leaderboard is at the foot of the page.</p>
<p class="note">This board rates the <b>{model.PRESEASON_MIN_MINUTES:.0f}+
minute</b> players of last season, which is a deliberately blunt
instrument: it keeps a squad's worth of real starters per club and drops
the deputies, but it also drops a genuine regular whose season was cut
short by injury. Anyone it drops appears in the unrated list at the foot of
the page rather than being hidden.</p>
<p class="note">The players it cannot rate at all are listed at the bottom:
promoted-club squads and signings from abroad have no Premier League record.
They are not bad picks — they are the ones you have to judge by eye.</p>
</section>

<section><h2>The {n_factors} scored factors, and one diagnostic</h2>
<div class="tablewrap"><table>{factor_rows}</table></div>
<p class="note"><b>Eligibility gate:</b> at least
<b>{model.PRESEASON_MIN_MINUTES:.0f} minutes</b> played in
{esc(history_season)} — about seven full matches — <i>and</i> 45+ minutes
averaged over the last {model.MINUTES_WINDOW} matches he played. The
absolute threshold is the one doing the work: a recency test alone
conditions on matches actually played, so a keeper who started five games
passed it exactly as one who started thirty-eight.
<a href="#leaderboards">Full sorted leaderboards ↓</a></p></section>

{''.join(sections)}

{squads_html(listing_path, history_dir, n_factors, len(elig))}

<section><h2>Best points per pound</h2>
<p class="note">Model expected points per 90 divided by the new price,
across all positions. A standalone lens, <b>not</b> the Value factor's
yardstick — Value ranks the residual against a fitted price curve within a
position, because raw points-per-pound mostly re-states Quality. This table
is the blunt version, useful when the squad budget is the binding
constraint.</p>
<div class="tablewrap"><table>
<tr><th>Player</th><th>Pos</th><th>Team</th><th class="num">Price</th>
<th class="num">Owned</th><th class="num">xPts/90</th>
<th class="num">per £m</th><th>Stars</th></tr>
{value_rows}</table></div></section>

{leaderboards_html(rated)}

<section><h2>Not rated — under the minutes bar</h2>
<p class="note">{len(gated)} players hold a {esc(history_season)} record and
play a full part when picked, but fall short of
{model.PRESEASON_MIN_MINUTES:.0f} minutes for the season. Most are
deputies. Some are not — a regular whose season ended early looks identical
here, so this list is worth reading rather than skipping.</p>
<div class="tablewrap"><table>
<tr><th>Player</th><th>Pos</th><th>Team</th><th class="num">Minutes</th>
<th class="num">Apps</th><th class="num">Owned</th></tr>
{gated_rows}</table></div></section>

<section><h2>Not rated — no Premier League record</h2>
<p class="note">{len(unrated)} listed players have no {esc(history_season)}
Premier League history to rate: promoted-club squads and signings from
abroad. The model is silent on them by construction, not dismissive.</p>
<div class="tablewrap"><table>
<tr><th>Team</th><th class="num">Players not rated</th></tr>
{unrated_rows}</table></div></section>

<footer>Generated {date.today().isoformat()} · fantasy_premier_league ·
pre-season board</footer>
</div></body></html>"""
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({len(board)} picks, {n_matched}/{n_total} matched)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--listing", default=HERE / "data" / "2026-27" / "player_listing.csv")
    ap.add_argument("--history", default=HERE / "data" / "2025-26")
    ap.add_argument("--out", default=HERE / "preseason.html")
    ap.add_argument("--season", default="2026/27")
    ap.add_argument("--history-season", default="2025/26")
    args = ap.parse_args()
    build(Path(args.listing), Path(args.history), Path(args.out),
          args.season, args.history_season)


if __name__ == "__main__":
    main()
