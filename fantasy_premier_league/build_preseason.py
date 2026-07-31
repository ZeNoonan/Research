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
PER_POSITION = 10
MOVERS = 8

FACTOR_ROWS = [
    ("Q", "Quality", "Model expected points per 90 — rebuilt from the FPL "
     "scoring rules and last season's underlying per-90 numbers — above the "
     "position median. Rates are shrunk toward the position average by "
     "sample size, so a big number off a handful of substitute appearances "
     "last season doesn't outrank a full campaign."),
    ("V", "Value", "Expected points per 90 per £million <b>at the new "
     "price</b>. This is the factor the new price list actually moves: a "
     "player repriced down whose numbers held is the pre-season bargain."),
    ("F", "Form", "Points over the <b>final 5 gameweeks of last season</b>. "
     "The weakest signal here — three months stale, and a summer of "
     "transfers in between."),
    ("M", "Minutes", "Average minutes over the last 5 matches he played last "
     "season, at or above the position median — the nailed-on starters."),
    ("J", "Justice", "Under-rewarded over the <b>final 6 gameweeks of last "
     "season</b>: attackers whose xGI beat their returns, defenders and "
     "keepers who conceded more than their xGC."),
]


def picks_table(block) -> str:
    rows = []
    for r in block.itertuples():
        move = ""
        if abs(r.price_change) >= 0.05:
            cls = "up" if r.price_change > 0 else "down"
            move = (f" <span class='{cls}'>{r.price_change:+.1f}</span>")
        note = f"<br><span class='sub2'>from {esc(r.last_team)}</span>" if r.moved else ""
        rows.append(
            f"<tr><td><span class='stars'>{'★' * r.stars}</span></td>"
            f"<td>{esc(r.name)}{note}</td><td>{esc(r.team)}</td>"
            f"<td class='num'>£{r.price:.1f}m{move}</td>"
            f"<td><span class='letters'>{esc(r.factor_letters)}</span></td>"
            f"<td class='num'>{r.xpts90:.2f}</td></tr>")
    head = ("<tr><th>Stars</th><th>Player</th><th>Team</th>"
            "<th class='num'>Price (change)</th><th>Factors</th>"
            "<th class='num'>xPts/90</th></tr>")
    return f"<div class='tablewrap'><table>{head}{''.join(rows)}</table></div>"


def movers_table(block, rising: bool) -> str:
    rows = []
    for r in block.itertuples():
        cls = "up" if r.price_change > 0 else "down"
        rows.append(
            f"<tr><td>{esc(r.name)}</td><td>{esc(r.team)}</td>"
            f"<td class='num'>£{r.last_price:.1f}m</td>"
            f"<td class='num'>£{r.price:.1f}m</td>"
            f"<td class='num {cls}'>{r.price_change:+.1f}</td>"
            f"<td class='num'>{r.xpts90:.2f}</td></tr>")
    head = ("<tr><th>Player</th><th>Team</th><th class='num'>Was</th>"
            "<th class='num'>Now</th><th class='num'>Change</th>"
            "<th class='num'>xPts/90</th></tr>")
    return f"<div class='tablewrap'><table>{head}{''.join(rows)}</table></div>"


def leaderboards_html(rated) -> str:
    """Per-factor sorted leaderboards with the cut line, pre-season factors."""
    elig = rated[rated["eligible"]].copy()
    elig["ppm"] = elig["xpts90"] / elig["price"]

    def med(block, col, fmt):
        return format(block[col].median(), fmt)

    specs = [
        ("quality", "Q", "Quality — sorted by model xPts/90", "xpts90",
         [("xPts/90", lambda r: f"{r.xpts90:.2f}")],
         lambda b: f"median xPts/90 = {med(b, 'xpts90', '.2f')} — "
                   "star above this line"),
        ("value", "V", "Value — sorted by xPts/90 per £million (new prices)",
         "ppm",
         [("Price", lambda r: f"£{r.price:.1f}m"),
          ("xPts/90 per £m", lambda r: f"{r.ppm:.3f}")],
         lambda b: f"median = {med(b, 'ppm', '.3f')} per £m — "
                   "star above this line"),
        ("form", "F", "Form — sorted by final-5-gameweek points", "form_points",
         [("Last-5 pts", lambda r: f"{r.form_points:.0f}")],
         lambda b: f"median = {med(b, 'form_points', '.0f')} points — "
                   "star above this line"),
        ("minutes_factor", "M",
         "Minutes — sorted by average minutes over the last 5 matches played",
         "minutes_avg",
         [("Avg mins", lambda r: f"{r.minutes_avg:.1f}")],
         lambda b: f"median = {med(b, 'minutes_avg', '.1f')} minutes — "
                   "star at or above this line"),
        ("justice", "J", "Justice — sorted by final-6-gameweek luck margin",
         "justice_margin",
         [("Margin", lambda r: f"{r.justice_margin:+.1f}")],
         lambda b: "zero — star above this line (positive margin = "
                   "under-rewarded)"),
    ]

    out = ["<section id='leaderboards'><h2>Factor leaderboards — "
           "who is above the line</h2>",
           "<p class='note'>Every rated player, sorted highest to lowest on "
           "each factor's yardstick, position by position. The purple line is "
           "the cut: tinted rows above it earn that factor's star. Tap a "
           "position to open it.</p>"]
    for factor, letter, title, sort_col, cols, divider_fn in specs:
        out.append(f"<h3 style='font-size:16px;margin:16px 0 4px'>"
                   f"<span class='letters'>{letter}</span> {title}</h3>")
        for pos in model.POSITIONS:
            block = elig[elig["position"] == pos].copy()
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
    board = preseason.picks(rated, min_stars=4)
    elig = rated[rated["eligible"]]

    sections = []
    for pos in model.POSITIONS:
        block = board[board["position"] == pos].head(PER_POSITION)
        body = (picks_table(block) if not block.empty
                else "<p class='note'>No players at 4+ stars.</p>")
        sections.append(f"<section><h2>{POSITION_NAMES[pos]}</h2>{body}</section>")

    risers = elig.nlargest(MOVERS, "price_change")
    fallers = elig.nsmallest(MOVERS, "price_change")

    value = elig.copy()
    value["ppm"] = value["xpts90"] / value["price"]
    best_value = value.nlargest(12, "ppm")
    value_rows = "".join(
        f"<tr><td>{esc(r.name)}</td><td>{esc(r.position)}</td>"
        f"<td>{esc(r.team)}</td><td class='num'>£{r.price:.1f}m</td>"
        f"<td class='num'>{r.xpts90:.2f}</td>"
        f"<td class='num'><b>{r.ppm:.3f}</b></td>"
        f"<td><span class='stars'>{'★' * r.stars}</span></td></tr>"
        for r in best_value.itertuples())

    by_team = unrated.groupby("team").size().sort_values(ascending=False)
    unrated_rows = "".join(
        f"<tr><td>{esc(team)}</td><td class='num'>{n}</td></tr>"
        for team, n in by_team.items())

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
to a {esc(history_season)} record, {int(elig["eligible"].count())} of them
with enough minutes to rate. Ratings are out of <b>5 stars</b>, not 6 —
the Crowd factor needs ownership data, which does not exist until the game
opens. <a href="index.html" style="color:var(--accent2)">In-season app →</a></div>

<section><h2>Read this first</h2>
<p class="note">Every number here comes from <b>{esc(history_season)}</b>.
That is the only evidence available before a ball is kicked, and it is
genuinely weaker than in-season data: it cannot see pre-season friendlies,
new signings settling, managerial changes or injuries. Two things it does
do well — it prices last season's underlying performance against
<b>this season's money</b>, and it says who was actually playing.</p>
<p class="note">The players it cannot rate at all are listed at the bottom:
promoted-club squads and signings from abroad have no Premier League record.
They are not bad picks — they are the ones you have to judge by eye.</p>
</section>

<section><h2>The five pre-season factors</h2>
<div class="tablewrap"><table>{factor_rows}</table></div>
<p class="note">Eligibility gate: 45+ minutes averaged over the last 4
matches he actually played last season.
<a href="#leaderboards">Full sorted leaderboards ↓</a></p></section>

{''.join(sections)}

<section><h2>Best points per pound</h2>
<p class="note">Model expected points per 90 divided by the new price —
the Value factor's raw yardstick, across all positions.</p>
<div class="tablewrap"><table>
<tr><th>Player</th><th>Pos</th><th>Team</th><th class="num">Price</th>
<th class="num">xPts/90</th><th class="num">per £m</th><th>Stars</th></tr>
{value_rows}</table></div></section>

<section><h2>The summer's price moves</h2>
<p class="note">New price against last season's closing price, for rated
players. A faller whose underlying numbers held is exactly what the Value
factor is built to catch.</p>
<div class="two">
<div><h3 style="font-size:15px;margin:6px 0">Biggest rises</h3>
{movers_table(risers, True)}</div>
<div><h3 style="font-size:15px;margin:6px 0">Biggest falls</h3>
{movers_table(fallers, False)}</div>
</div></section>

{leaderboards_html(rated)}

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
