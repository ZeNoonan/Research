"""Generate a self-contained, mobile-friendly HTML view of the weekly picks.

Rates the season in ``data/<season>/`` and writes ``index.html``: the factor
explainer, the 6/7-star pick lists by position and the captain shortlist.
No external assets (same treatment as ``nfl_report/``), so the page can be
served from GitHub Pages or opened as a file. Rerun after adding gameweek
files:

    python build_site.py [--data data/2026-27]
"""

from __future__ import annotations

import argparse
import html
from datetime import date
from pathlib import Path

import model
from weekly_report import POSITION_NAMES, fmt_selected

HERE = Path(__file__).parent
PER_POSITION = 12  # rows shown per position section

CSS = """
:root {
  --bg: #f4f6f8; --card: #ffffff; --ink: #1c2733; --muted: #5f6b76;
  --accent: #38003c; --accent2: #00ff85; --border: #dce3ea; --star: #b58900;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  -webkit-text-size-adjust: 100%; }
.wrap { max-width: 980px; margin: 0 auto; padding: 16px; }
header h1 { font-size: 24px; margin: 8px 0 4px; }
header p.sub { color: var(--muted); margin: 0 0 16px; font-size: 14px; }
.banner { background: var(--accent); color: #fff; border-radius: 10px;
  padding: 12px 14px; font-size: 14px; margin-bottom: 16px; }
.banner b { color: var(--accent2); }
section { background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px; margin-bottom: 16px; }
section h2 { font-size: 18px; margin: 0 0 10px; }
.tablewrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border);
  white-space: nowrap; }
th { color: var(--muted); font-weight: 600; font-size: 12px;
  text-transform: uppercase; letter-spacing: .04em; }
td.num, th.num { text-align: right; }
.stars { color: var(--star); letter-spacing: 1px; }
.letters { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: #eef4fb; border-radius: 6px; padding: 1px 6px; font-size: 12px; }
p.note, li { color: var(--muted); font-size: 14px; }
code { background: #eef1f4; border-radius: 4px; padding: 1px 5px; font-size: 13px; }
footer { color: var(--muted); font-size: 12px; margin: 20px 0; text-align: center; }
.ex { border-top: 1px solid var(--border); padding-top: 12px; margin-top: 14px; }
.ex h3 { font-size: 16px; margin: 0 0 6px; }
.ex p { font-size: 14px; margin: 8px 0; }
.ex table { margin: 8px 0; }
.yes { color: #1e7d46; font-weight: 700; }
.no { color: var(--muted); }
tr.starred td { background: rgba(181, 137, 0, .10); }
.calc { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px; }
details { border: 1px solid var(--border); border-radius: 8px;
  padding: 0 10px; margin: 8px 0; }
summary { cursor: pointer; font-weight: 600; font-size: 14px; padding: 9px 0;
  color: var(--accent); }
details[open] summary { border-bottom: 1px solid var(--border); }
tr.divider td { background: var(--accent); color: #fff; text-align: center;
  font-size: 12px; padding: 3px 8px; white-space: normal; }
.sub2 { color: var(--muted); font-size: 12px; }
.stale { color: #b3372f; font-size: 12px; font-weight: 600; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #14181c; --card: #1d232a; --ink: #e6ebf0; --muted: #98a4af;
    --border: #313a44; --star: #e0b64a; }
  .letters { background: #26303a; }
  code { background: #26303a; }
  .yes { color: #4cc38a; }
  tr.starred td { background: rgba(224, 182, 74, .12); }
  summary { color: #c9a0d8; }
  .stale { color: #ef7a72; }
}
"""

FACTOR_ROWS = [
    ("Q", "Quality", "Model expected points per 90 — rebuilt from the FPL "
     "scoring rules and the player's underlying per-90 numbers (xG, xA, xGC, "
     "defensive contributions, saves) — above the position median. Rates are "
     "shrunk toward the position average by sample size, so a dazzling "
     "number off 130 minutes doesn't outrank a season of evidence."),
    ("V", "Value", "Expected points per 90 per £million above the position "
     "median. Points per pound funds the rest of the squad."),
    ("F", "Form", "Points over the last 5 matches the player actually "
     "played, above the position median. Momentum."),
    ("M", "Minutes", "Share of the minutes actually available over the last "
     "5 gameweeks, at or above the position median. Available minutes are "
     "counted per club, so a blank gameweek costs nobody and a double "
     "counts twice. Unlike Form and Justice this window counts gameweeks, "
     "not appearances: a match missed has to count as a zero, or the factor "
     "cannot tell a starter from a man who plays 90 minutes whenever he is "
     "fit. (At-or-above, since whole positions sit on the same value.)"),
    ("N", "Nailed", "The same share, at or above 75% of the available "
     "minutes. This is Minutes' second star, and the bar is absolute rather "
     "than a position rank — three quarters of the minutes means the same "
     "thing for a keeper and a forward, which is not true of a rate stat. "
     "Minutes carries two stars because season points are a per-90 rate "
     "times minutes played, and minutes are the more variable term: one "
     "median cut cannot separate a player on 61% from one on 97%."),
    ("J", "Justice", "Expected goal involvements (xG + xA) over the last 8 "
     "matches the player actually played, above the position median. "
     "Chances made and got on the end of are the process behind attacking "
     "returns, and they persist where the returns themselves bounce "
     "around."),
    ("C", "Crowd", "Ownership percentile below quality percentile within the "
     "position — the field underweights the player (bet against beta)."),
]


def esc(x) -> str:
    return html.escape(str(x))


# --- worked examples ---------------------------------------------------------
# Five made-up midfielders, reused across the Quality/Value/Form/Minutes/
# Nailed/Crowd examples so the arithmetic stays easy to follow. (price £m,
# model xPts/90, points over the last 5 GWs, minutes in each of the last 5
# gameweeks, ownership in managers.) Every club here plays once a gameweek,
# so 5 x 90 = 450 minutes were available to all five.
TOY = [
    # name    price  xpts90  last5  minutes per GW            owned
    ("Player A", 8.0, 3.6, 24, (90, 90, 90, 85, 90), 5_000_000),
    ("Player B", 5.0, 2.6, 18, (90, 0, 0, 90, 90), 300_000),
    ("Player C", 14.0, 4.1, 28, (74, 80, 90, 68, 78), 1_200_000),
    ("Player D", 4.5, 1.8, 12, (45, 60, 90, 30, 55), 100_000),
    ("Player E", 5.5, 2.2, 15, (58, 65, 60, 67, 60), 900_000),
]
TOY_AVAILABLE = 5 * 90


def _ex_table(headers: list[str], rows: list[tuple], starred: set[str]) -> str:
    head = "".join(f"<th class='num'>{h}</th>" if i else f"<th>{h}</th>"
                   for i, h in enumerate(headers))
    body = []
    for row in rows:
        name = row[0]
        cls = " class='starred'" if name in starred else ""
        cells = f"<td>{esc(name)}</td>" + "".join(
            f"<td class='num'>{c}</td>" for c in row[1:-1])
        mark = ("<td class='num yes'>★ yes</td>" if row[-1]
                else "<td class='num no'>no</td>")
        body.append(f"<tr{cls}>{cells}{mark}</tr>")
    return (f"<div class='tablewrap'><table><tr>{head}</tr>"
            f"{''.join(body)}</table></div>")


def examples_html() -> str:
    import statistics
    med_q = statistics.median(p[2] for p in TOY)
    ppm = {p[0]: p[2] / p[1] for p in TOY}
    med_ppm = statistics.median(ppm.values())
    med_form = statistics.median(p[3] for p in TOY)
    share = {p[0]: sum(p[4]) / TOY_AVAILABLE for p in TOY}
    med_mins = statistics.median(share.values())
    q_rank = {n: r + 1 for r, (n, *_) in
              enumerate(sorted(TOY, key=lambda p: p[2]))}
    o_rank = {n: r + 1 for r, (n, *_) in
              enumerate(sorted(TOY, key=lambda p: p[5]))}

    quality_rows = [(n, f"{x:.1f}", x > med_q) for n, _, x, _, _, _ in TOY]
    value_rows = [(n, f"£{pr:.1f}m", f"{x:.1f}", f"{ppm[n]:.2f}",
                   ppm[n] > med_ppm) for n, pr, x, _, _, _ in TOY]
    form_rows = [(n, f5, f5 > med_form) for n, _, _, f5, _, _ in TOY]
    minutes_rows = [(n, " + ".join(str(x) for x in m), sum(m),
                     f"{share[n]:.0%}", share[n] >= med_mins)
                    for n, _, _, _, m, _ in TOY]
    nailed_rows = [(n, f"{share[n]:.0%}", share[n] >= model.NAILED_SHARE)
                   for n, *_ in TOY]
    crowd_rows = [(n, f"{o / 1e6:.1f}m", q_rank[n], o_rank[n],
                   o_rank[n] < q_rank[n]) for n, _, _, _, _, o in TOY]

    quality = f"""
<div class="ex"><h3><span class="letters">Q</span> Quality — worked example</h3>
<p>Take a made-up midfielder, <b>Player A</b>. Over the season his per-90
underlying numbers are: xG 0.40, xA 0.20, team xGC while he's on the pitch
1.20, and he hits the 12-action defensive-contribution threshold in 35% of
his starts. Apply the FPL scoring rules to those rates:</p>
<div class="tablewrap"><table>
<tr><th>Component</th><th class="num">Calculation</th><th class="num">Points/90</th></tr>
<tr><td>Goals</td><td class="num calc">0.40 × 5 (MID goal)</td><td class="num">2.00</td></tr>
<tr><td>Assists</td><td class="num calc">0.20 × 3</td><td class="num">0.60</td></tr>
<tr><td>Clean sheets</td><td class="num calc">e<sup>−1.20</sup> ≈ 0.30 × 1 (MID CS)</td><td class="num">0.30</td></tr>
<tr><td>Defensive contribution</td><td class="num calc">0.35 × 2</td><td class="num">0.70</td></tr>
<tr><td><b>Model xPts/90</b></td><td class="num"></td><td class="num"><b>3.60</b></td></tr>
</table></div>
<p>Do that for every eligible midfielder, then compare each to the position
median. Among our five made-up midfielders the median is
<b>{med_q:.1f}</b> — the star goes to everyone strictly above it:</p>
{_ex_table(["Player", "xPts/90", "Star?"], quality_rows,
           {n for n, _, s in quality_rows if s})}
<p class="note">Player B sits exactly on the median, so no star — "above the
median" is strict. Note the engine never looks at actual points scored:
goals in, luck out.</p>
<p class="note"><b>One more step, for small samples.</b> A rate built from
130 minutes is mostly noise, and left alone it puts bit-part players at the
top of every per-90 ranking. So each rate is pulled toward its position's
average by how much evidence stands behind it — a player with 450 minutes
lands halfway between his own number and the position average, while a
3,000-minute regular is left essentially untouched. Player A, on a full
season, keeps his 3.60; the same 3.60 off two substitute appearances would
be marked down to roughly the position average.</p></div>"""

    value = f"""
<div class="ex"><h3><span class="letters">V</span> Value — worked example</h3>
<p>Divide each player's xPts/90 by his price. Player A:
<span class="calc">3.6 ÷ £8.0m = 0.45</span> points per 90 per £million.</p>
{_ex_table(["Player", "Price", "xPts/90", "xPts/90 per £m", "Star?"],
           value_rows, {r[0] for r in value_rows if r[-1]})}
<p>The median is <b>{med_ppm:.2f}</b>, so Players A and B collect the star.
The teaching point is <b>Player C</b>: the best player on the list
(4.1 xPts/90) but at £14.0m he returns only 0.29 per £m — top of the
Quality table, yet no Value star. Players D and E sit exactly on the
median: no star.</p></div>"""

    form = f"""
<div class="ex"><h3><span class="letters">F</span> Form — worked example</h3>
<p>Add up each player's actual FPL points over the <b>last 5 gameweeks</b>.
Player A's last five scores were 2, 9, 3, 6 and 4 —
<span class="calc">2 + 9 + 3 + 6 + 4 = 24</span>.</p>
{_ex_table(["Player", "Last-5-GW points", "Star?"], form_rows,
           {r[0] for r in form_rows if r[-1]})}
<p>Median <b>{med_form:.0f}</b>; A and C are above it and take the momentum
star. This is the one factor built on actual points — it deliberately
rewards whatever is currently working, lucky or not.</p></div>"""

    minutes = f"""
<div class="ex"><h3><span class="letters">M</span> Minutes — worked example</h3>
<p>Add up each player's minutes over the <b>last 5 gameweeks</b> and divide
by the minutes his club actually had available. Every club here played once
a gameweek, so that is <span class="calc">5 × 90 = 450</span>. Unlike Form
and Justice, this window counts <b>gameweeks, not appearances</b>: a match
Player B missed counts as a zero rather than being skipped over, because
missing it is precisely what the factor is trying to measure.</p>
{_ex_table(["Player", "Minutes by gameweek", "Total", "Share", "Star?"],
           minutes_rows, {r[0] for r in minutes_rows if r[-1]})}
<p>The median share is <b>{med_mins:.0%}</b>, and for this factor the star
goes to everyone <b>at or above</b> it — not strictly above, unlike the
others. That's deliberate: whole positions sit level on 100% (nearly every
regular keeper, many centre-backs), and a strict rule would star none of
them.</p>
<p>Player B is the case the old version got wrong. He played 90 minutes in
every match he featured in, so averaging his appearances made him look as
nailed as Player A — but he only featured in three gameweeks of five, and
<span class="calc">270 ÷ 450 = 60%</span> says so.</p>
<p class="note">Available minutes are counted <b>per club</b>, not as a flat
450. A club with a blank gameweek had only 4 × 90 = 360 available, so its
players are not punished for a match that was never played; a club with a
double had 6 × 90 = 540.</p></div>"""

    nailed = f"""
<div class="ex"><h3><span class="letters">N</span> Nailed — worked example</h3>
<p>Same share, second question: is it at least
<b>{model.NAILED_SHARE:.0%}</b> of the available minutes? This bar is
<b>absolute</b> — no median, no position group. Three quarters of the
minutes means the same thing for a keeper as for a forward, which is not
true of a rate statistic like xG.</p>
{_ex_table(["Player", "Share", "Star?"], nailed_rows,
           {r[0] for r in nailed_rows if r[-1]})}
<p>Minutes is the only factor worth two stars, because season points are
roughly a per-90 rate <i>multiplied by</i> minutes played, and minutes are
the more variable of the two. One median cut cannot tell a player on 61% of
the minutes from one on 97%; these two together sort players into three
groups instead of two.</p>
<p>Player E is why the second cut earns its place: at
<span class="calc">310 ÷ 450 = 69%</span> he sits exactly on the median and
keeps the M star, but he is hooked around the hour every week and does not
clear the nailed bar. Player C, on 87%, takes both.</p></div>"""

    justice = """
<div class="ex"><h3><span class="letters">J</span> Justice — worked example</h3>
<p>Add up a player's <b>expected goal involvements</b> — xG plus xA — over
the <b>last 8 matches he actually played</b>, and compare to the position
median. It counts chances, not what they turned into: a shot that hits the
post and a shot that goes in are worth the same here. Made-up midfielders,
each with 8 appearances behind them:</p>
<div class="tablewrap"><table>
<tr><th>Player</th><th class="num">xG (8 apps)</th><th class="num">xA (8 apps)</th>
<th class="num">xGI</th><th class="num">Star?</th></tr>
<tr class="starred"><td>Player F</td><td class="num">3.10</td><td class="num">0.60</td>
<td class="num calc">3.70</td><td class="num yes">★ yes</td></tr>
<tr class="starred"><td>Player G</td><td class="num">0.90</td><td class="num">1.30</td>
<td class="num calc">2.20</td><td class="num yes">★ yes</td></tr>
<tr><td>Player H</td><td class="num">0.50</td><td class="num">0.60</td>
<td class="num calc">1.10</td><td class="num no">no</td></tr>
<tr><td>Player I</td><td class="num">0.20</td><td class="num">0.30</td>
<td class="num calc">0.50</td><td class="num no">no</td></tr>
</table></div>
<p>Median xGI is <b>1.65</b>, so F and G take the star. Note what this
factor deliberately ignores: whether any of it was <i>converted</i>. A
forward who has racked up 3.7 xGI and scored four times rates exactly the
same as one who has racked up 3.7 and scored none — the claim is only that
he keeps getting into positions, which is the part that carries into next
week. Goals themselves are already counted by Quality and Form.</p>
<p class="note">Needs 8 appearances to be scored at all — under that, no
star and no vote in the median.</p></div>"""

    crowd = f"""
<div class="ex"><h3><span class="letters">C</span> Crowd — worked example</h3>
<p>Rank the five midfielders twice — once by quality (xPts/90), once by
ownership — with 1 the lowest and 5 the highest. The star goes to anyone
whose <b>ownership rank is below his quality rank</b>: the field hasn't
caught on yet.</p>
{_ex_table(["Player", "Owned by", "Quality rank", "Ownership rank", "Star?"],
           crowd_rows, {r[0] for r in crowd_rows if r[-1]})}
<p>Player C is the best of the five (quality rank 5) but not the most
owned (ownership rank 4) — the field underrates him, star. Player B
likewise (quality 3, ownership 2). Player A is the <i>most</i>-owned
player but only second-best — the bandwagon is ahead of the quality, so
no star. When a differential comes off, it moves you up
the rank ladder past everyone who didn't own it.</p></div>"""

    gate = """
<div class="ex"><h3>The minutes gate — worked example</h3>
<p>Before any factor is scored, a player must average <b>45+ minutes over
the last 4 matches he actually played</b>. A starter whose last four
appearances were <span class="calc">90, 90, 30, 75 → avg 71</span> is
rated. A super-sub used for <span class="calc">20, 25, 15, 30 → avg 22.5</span>
is not, whatever his underlying numbers say. Crucially, the four matches
are the player's own appearances, however long ago: a starter who then
misses six weeks injured keeps his <span class="calc">avg 71</span> and
stays in the ratings — absence alone never drops anyone. While he's out
his last-5-gameweek Form fades to zero, so a long absence costs stars,
not visibility.</p></div>"""

    return (f"<section id='examples'><h2>How each factor is calculated — "
            f"worked examples</h2>"
            f"<p class='note'>Every number in this section is made up, "
            f"chosen so the sums are easy to follow. The real model runs "
            f"exactly this arithmetic over every eligible player, inside "
            f"each position (GK / DEF / MID / FWD).</p>"
            f"{quality}{value}{form}{minutes}{nailed}{justice}{crowd}"
            f"{gate}</section>")


def picks_table(block) -> str:
    rows = []
    for r in block.itertuples():
        note = ""
        if r.factors_assessed < len(model.FACTORS):
            note += (f"<br><span class='sub2'>only {r.factors_assessed} "
                     f"factors assessable — {r.appearances} appearances</span>")
        if r.gws_since_app >= 2:
            note += (f"<br><span class='stale'>last played GW"
                     f"{r.last_app_round:.0f}</span>")
        rows.append(
            f"<tr><td><span class='stars'>{'★' * r.stars}</span></td>"
            f"<td>{esc(r.name)}{note}</td><td>{esc(r.team)}</td>"
            f"<td class='num'>£{r.price:.1f}m</td>"
            f"<td><span class='letters'>{esc(r.factor_letters)}</span></td>"
            f"<td class='num'>{r.xpts90:.1f}</td>"
            f"<td class='num'>{fmt_selected(r.selected)}</td></tr>")
    head = ("<tr><th>Stars</th><th>Player</th><th>Team</th>"
            "<th class='num'>Price</th><th>Factors</th>"
            "<th class='num'>xPts/90</th><th class='num'>Owned</th></tr>")
    return f"<div class='tablewrap'><table>{head}{''.join(rows)}</table></div>"


# --- factor leaderboards -----------------------------------------------------

def _leaderboard_table(block, factor: str, cols, divider: str) -> str:
    """Sorted rows for one position; a divider row marks the star cut-off."""
    rows, cut_done = [], False
    span = 2 + len(cols)
    for r in block.itertuples():
        starred = getattr(r, factor) == 1
        if not cut_done and not starred:
            rows.append(f"<tr class='divider'><td colspan='{span}'>"
                        f"{divider}</td></tr>")
            cut_done = True
        cls = " class='starred'" if starred else ""
        cells = "".join(f"<td class='num'>{fmt(r)}</td>" for _, fmt in cols)
        rows.append(f"<tr{cls}><td>{esc(r.name)}</td>"
                    f"<td>{esc(r.team)}</td>{cells}</tr>")
    if not cut_done:
        rows.append(f"<tr class='divider'><td colspan='{span}'>{divider}</td></tr>")
    head = ("<tr><th>Player</th><th>Team</th>"
            + "".join(f"<th class='num'>{h}</th>" for h, _ in cols) + "</tr>")
    return f"<div class='tablewrap'><table>{head}{''.join(rows)}</table></div>"


def leaderboards_html(rated) -> str:
    elig = rated[rated["eligible"]].copy()
    elig["ppm"] = elig["xpts90"] / elig["price"]
    # Same percentile construction as the Crowd factor in model.rate_players.
    for pos in model.POSITIONS:
        grp = elig["position"] == pos
        q = elig.loc[grp, "xpts90"].rank(pct=True)
        o = elig.loc[grp, "selected"].rank(pct=True)
        elig.loc[grp, "crowd_gap"] = (q - o) * 100

    def med(block, col, fmt):
        return format(block[col].median(), fmt)

    specs = [
        ("quality", "Q", "Quality — sorted by model xPts/90", "xpts90",
         [("xPts/90", lambda r: f"{r.xpts90:.2f}")],
         lambda b: f"median xPts/90 = {med(b, 'xpts90', '.2f')} — "
                   "star above this line"),
        ("value", "V", "Value — sorted by xPts/90 per £million", "ppm",
         [("Price", lambda r: f"£{r.price:.1f}m"),
          ("xPts/90 per £m", lambda r: f"{r.ppm:.3f}")],
         lambda b: f"median = {med(b, 'ppm', '.3f')} per £m — "
                   "star above this line"),
        ("form", "F", "Form — sorted by last-5-gameweek points", "form_points",
         [("Last-5 pts", lambda r: f"{r.form_points:.0f}")],
         lambda b: f"median = {med(b, 'form_points', '.0f')} points — "
                   "star above this line"),
        ("minutes_factor", "M",
         "Minutes — sorted by share of the last 5 gameweeks' available minutes",
         "minutes_share",
         [("Share", lambda r: f"{r.minutes_share:.0%}"),
          ("Mins / avail", lambda r: f"{r.minutes_recent:.0f} / "
                                     f"{r.minutes_available:.0f}")],
         lambda b: f"median = {med(b, 'minutes_share', '.0%')} — "
                   "star at or above this line"),
        ("minutes_nailed", "N",
         "Nailed — the same share, against an absolute three-quarter bar",
         "minutes_share",
         [("Share", lambda r: f"{r.minutes_share:.0%}")],
         lambda b: f"{model.NAILED_SHARE:.0%} of the available minutes — "
                   "star at or above this line, the same bar for every "
                   "position"),
        ("justice", "J", "Justice — sorted by xGI over the last 8 matches played",
         "justice_xgi",
         [("xGI (last 8)", lambda r: f"{r.justice_xgi:.2f}")],
         lambda b: f"median xGI = {med(b, 'justice_xgi', '.2f')} — "
                   "star above this line"),
        ("crowd", "C", "Crowd — sorted by quality minus ownership percentile",
         "crowd_gap",
         [("Quality pct", lambda r: f"{r.xpts90_pct:.0f}"),
          ("Owned pct", lambda r: f"{r.selected_pct:.0f}"),
          ("Gap", lambda r: f"{r.crowd_gap:+.0f}")],
         lambda b: "zero gap — star above this line (quality ahead of "
                   "ownership)"),
    ]

    out = ["<section id='leaderboards'><h2>Factor leaderboards — "
           "who is above the line</h2>",
           "<p class='note'>Every eligible player, sorted from highest to "
           "lowest on each factor's yardstick, position by position. The "
           "purple line is the cut: tinted rows above it earn that factor's "
           "star. Tap a position to open it. The three appearance-window "
           "factors list only players with a full sample — the others are "
           "not considered, so they are not ranked here either.</p>"]
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
            if factor == "crowd":
                block["xpts90_pct"] = block["xpts90"].rank(pct=True) * 100
                block["selected_pct"] = block["selected"].rank(pct=True) * 100
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


def build(data_dir: Path, out: Path) -> None:
    rated = model.rate_season(data_dir)
    picks = model.recommendations(rated, min_stars=6)
    through = int(rated["through_gw"].iloc[0])
    used = int(rated["gws_used"].iloc[0])
    season = data_dir.name

    thin = ""
    if used < model.MINUTES_WINDOW:
        thin = (" Only <b>%d</b> gameweek%s of evidence is loaded, so the "
                "form and justice windows are thin — treat these ratings as "
                "provisional." % (used, "s" if used != 1 else ""))

    sections = []
    for pos in model.POSITIONS:
        block = picks[picks["position"] == pos].head(PER_POSITION)
        body = (picks_table(block) if not block.empty
                else "<p class='note'>No players at 4+ stars.</p>")
        sections.append(f"<section><h2>{POSITION_NAMES[pos]}</h2>{body}</section>")

    captains = picks[picks["position"].isin(("MID", "FWD"))].nlargest(3, "xpts90")
    cap = ", ".join(f"{esc(r.name)} ({esc(r.team)})" for r in captains.itertuples())

    factor_rows = "".join(
        f"<tr><td><span class='letters'>{l}</span></td><td><b>{n}</b></td>"
        f"<td style='white-space:normal'>{d}</td></tr>"
        for l, n, d in FACTOR_ROWS)

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FPL seven-factor picks — {esc(season)} through GW{through}</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><h1>FPL seven-factor picks</h1>
<p class="sub">An additive binary-factor model for weekly Fantasy Premier
League picks — one star per factor (two for Minutes), judged against
position peers, in the
family of <code>march_madness/</code> and <code>nfl_report/</code>.</p></header>
<div class="banner">Season <b>{esc(season)}</b>, rated through
<b>GW{through}</b>. {int(rated['eligible'].sum())} players pass the minutes
gate; 6★ and 7★ picks below (top {PER_POSITION} per position).{thin}
<br><a href="preseason.html" style="color:var(--accent2)">2026/27 pre-season
draft board — new prices, rated on this season's evidence →</a>
<br><a href="shots.html" style="color:var(--accent2)">2026/27 shots, xG and xA
by gameweek →</a></div>
<section><h2>The seven factors</h2>
<div class="tablewrap"><table>{factor_rows}</table></div>
<p class="note"><b>Eligibility gate:</b> 45+ minutes averaged over the last
{model.MINUTES_WINDOW} matches the player <i>actually played</i> — absence
alone never drops anyone from the ratings; short-cameo usage does.</p>
<p class="note"><b>Form and Justice count appearances, not gameweeks</b>, so
a spell out shifts a window back instead of filling it with zeros. The
price is a minimum sample: Form needs <b>{model.FORM_WINDOW}</b>
appearances, Justice needs <b>{model.JUSTICE_WINDOW}</b>. Short of that a
player takes no star for the factor <i>and</i> is left out of its median —
a thin record neither earns a star nor moves the bar. Rows below say so,
and flag anyone who has not played recently, since his numbers are
otherwise indistinguishable from a regular's.</p>
<p class="note"><b>Minutes and Nailed are the exception</b>: they count the
last {model.MINUTES_FACTOR_WINDOW} <i>gameweeks</i> and a match missed
counts as a zero, because there an absence is the measurement rather than a
hole in the sample. They have no minimum sample and no unassessed state —
a player who has barely featured simply has a low share.</p>
<p class="note"><a href="#leaderboards">Full sorted leaderboards ↓</a> ·
<a href="#examples">Worked examples of every factor ↓</a></p></section>
{''.join(sections)}
<section><h2>Captain shortlist</h2>
<p class="note">{cap or 'No 4★+ attackers yet.'}</p></section>
{leaderboards_html(rated)}
{examples_html()}
<section><h2>Refresh</h2>
<p class="note"><code>python fetch_data.py</code> after a gameweek finishes,
then <code>python weekly_report.py</code> for the terminal view and
<code>python build_site.py</code> to regenerate this page. The full rated
table for every player is written to <code>reports/</code>.</p></section>
<footer>Generated {date.today().isoformat()} · fantasy_premier_league ·
seven-factor model</footer>
</div></body></html>"""
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({len(picks)} picks, through GW{through})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=HERE / "data" / "2025-26")
    ap.add_argument("--out", default=HERE / "index.html")
    args = ap.parse_args()
    build(Path(args.data), Path(args.out))


if __name__ == "__main__":
    main()
