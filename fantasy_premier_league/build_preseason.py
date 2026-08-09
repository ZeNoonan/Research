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
    ("J", "Justice", "Under-rewarded over the <b>last 6 matches he actually "
     "played</b> last season (needs 6 appearances): attackers whose xGI beat "
     "their returns, defenders and keepers who conceded more than their "
     "xGC."),
    ("C", "Crowd", "Quality percentile exceeding ownership percentile <b>by "
     f"at least {model.PRESEASON_CROWD_MARGIN:.0f} points</b> — the field is "
     "materially underweight, not just fractionally. Pre-season ownership "
     "below about 2% is undifferentiated (0.0% against 0.2% says nothing "
     "about conviction), so a bare gap manufactures precision that isn't "
     "there. This is the one <b>current</b> input on the board: who managers "
     "are piling into right now, before a ball is kicked."),
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
        letters = (f"<span class='letters'>{esc(r.factor_letters)}</span>"
                   if r.factor_letters else "<span class='sub2'>—</span>")
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
        ("justice", "J",
         "Justice — sorted by luck margin over the last 6 matches played",
         "justice_margin",
         [("Margin", lambda r: f"{r.justice_margin:+.1f}")],
         lambda b: "zero — star above this line (positive margin = "
                   "under-rewarded)"),
        ("crowd", "C", "Crowd — sorted by quality minus ownership percentile",
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
.two {{ display: grid; grid-template-columns: 1fr; gap: 12px; }}
@media (min-width: 720px) {{ .two {{ grid-template-columns: 1fr 1fr; }} }}
@media (prefers-color-scheme: dark) {{
  .up {{ color: #ef7a72; }} .down {{ color: #4cc38a; }}
}}
</style></head><body><div class="wrap">
<header><h1>FPL {esc(season)} — pre-season draft board</h1>
<p class="sub">The new season's price list rated on last season's evidence.
Same additive binary-factor model as the in-season app, one star per factor,
judged against position peers.</p></header>
<div class="banner">Prices: <b>{esc(season)}</b> · Evidence:
<b>{esc(history_season)}</b>. {n_matched} of {n_total} listed players matched
to a {esc(history_season)} record, <b>{len(elig)}</b> of them with enough
minutes to rate — all shown below, by position. Ratings are out of
<b>{n_factors} stars</b>, the full set: pre-season ownership is in, so the
Crowd factor scores too.
<a href="index.html" style="color:var(--accent2)">In-season app →</a></div>

<section><h2>Read this first</h2>
<p class="note">Every number here comes from <b>{esc(history_season)}</b>.
That is the only evidence available before a ball is kicked, and it is
genuinely weaker than in-season data: it cannot see pre-season friendlies,
new signings settling, managerial changes or injuries. Two things it does
do well — it prices last season's underlying performance against
<b>this season's money</b>, and it says who was actually playing.</p>
<p class="note">One input <i>is</i> current: <b>ownership</b>. The Crowd
factor reads today's squads — who managers are piling into before a ball is
kicked — and stars players the field is materially underweight on relative
to their quality. It is the one factor here that knows what month it is,
and it cuts the other way too: low ownership often encodes what the crowd
knows and last season's data cannot see — who is second choice, who has
been signed over, who limped out of a friendly. That is why it demands a
<b>{model.PRESEASON_CROWD_MARGIN:.0f}-percentile-point</b> margin rather
than any gap, and why only players
who actually played last season can earn it.</p>
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

<section><h2>The {n_factors} pre-season factors</h2>
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
