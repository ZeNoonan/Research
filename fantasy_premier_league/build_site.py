"""Generate a self-contained, mobile-friendly HTML view of the weekly picks.

Rates the season in ``data/<season>/`` and writes ``index.html``: the factor
explainer, the 4/5-star pick lists by position and the captain shortlist.
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
@media (prefers-color-scheme: dark) {
  :root { --bg: #14181c; --card: #1d232a; --ink: #e6ebf0; --muted: #98a4af;
    --border: #313a44; --star: #e0b64a; }
  .letters { background: #26303a; }
  code { background: #26303a; }
  .yes { color: #4cc38a; }
  tr.starred td { background: rgba(224, 182, 74, .12); }
}
"""

FACTOR_ROWS = [
    ("Q", "Quality", "Model expected points per 90 — rebuilt from the FPL "
     "scoring rules and the player's underlying per-90 numbers (xG, xA, xGC, "
     "defensive contributions, saves) — above the position median."),
    ("V", "Value", "Expected points per 90 per £million above the position "
     "median. Points per pound funds the rest of the squad."),
    ("F", "Form", "Points over the last 5 gameweeks above the position "
     "median. Momentum."),
    ("J", "Justice", "Under-rewarded over the last 6 gameweeks: attackers "
     "whose xGI beats their actual returns, defenders/keepers who conceded "
     "more than their xGC. Luck mean-reverts; the unlucky are cheap."),
    ("C", "Crowd", "Ownership percentile below quality percentile within the "
     "position — the field underweights the player (bet against beta)."),
]


def esc(x) -> str:
    return html.escape(str(x))


# --- worked examples ---------------------------------------------------------
# Five made-up midfielders, reused across the Quality/Value/Form/Crowd
# examples so the arithmetic stays easy to follow. (price £m, model xPts/90,
# points over the last 5 GWs, ownership in managers.)
TOY = [
    # name    price  xpts90  last5   owned
    ("Player A", 8.0, 3.6, 24, 5_000_000),
    ("Player B", 5.0, 2.6, 18, 300_000),
    ("Player C", 14.0, 4.1, 28, 1_200_000),
    ("Player D", 4.5, 1.8, 12, 100_000),
    ("Player E", 5.5, 2.2, 15, 900_000),
]


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
    q_rank = {n: r + 1 for r, (n, *_) in
              enumerate(sorted(TOY, key=lambda p: p[2]))}
    o_rank = {n: r + 1 for r, (n, *_) in
              enumerate(sorted(TOY, key=lambda p: p[4]))}

    quality_rows = [(n, f"{x:.1f}", x > med_q) for n, _, x, _, _ in TOY]
    value_rows = [(n, f"£{pr:.1f}m", f"{x:.1f}", f"{ppm[n]:.2f}",
                   ppm[n] > med_ppm) for n, pr, x, _, _ in TOY]
    form_rows = [(n, f5, f5 > med_form) for n, _, _, f5, _ in TOY]
    crowd_rows = [(n, f"{o / 1e6:.1f}m", q_rank[n], o_rank[n],
                   o_rank[n] < q_rank[n]) for n, _, _, _, o in TOY]

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
goals in, luck out.</p></div>"""

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

    justice = """
<div class="ex"><h3><span class="letters">J</span> Justice — worked example</h3>
<p>Over the <b>last 6 gameweeks</b>, compare what the underlying numbers say
a player <i>should</i> have returned with what he actually got. Made-up
numbers:</p>
<div class="tablewrap"><table>
<tr><th>Player</th><th class="num">xG + xA (6 GWs)</th><th class="num">Actual G + A</th>
<th class="num">Conceded − xGC</th><th class="num">Justice margin</th><th class="num">Star?</th></tr>
<tr class="starred"><td>Player F (FWD)</td><td class="num">3.1 + 0.6 = 3.7</td>
<td class="num">1 + 1 = 2</td><td class="num">—</td>
<td class="num calc">3.7 − 2 = +1.7</td><td class="num yes">★ yes</td></tr>
<tr><td>Player G (MID)</td><td class="num">0.9 + 0.3 = 1.2</td>
<td class="num">3 + 1 = 4</td><td class="num">—</td>
<td class="num calc">1.2 − 4 = −2.8</td><td class="num no">no</td></tr>
<tr class="starred"><td>Player H (DEF)</td><td class="num">0.5 + 0.1 = 0.6</td>
<td class="num">0 + 0 = 0</td><td class="num">9 − 7.0 = +2.0</td>
<td class="num calc">0.6 + 2.0 = +2.6</td><td class="num yes">★ yes</td></tr>
</table></div>
<p>Player F has banked 3.7 expected goal involvements but cashed only 2 —
he is <b>due</b>, so he gets the star. Player G has scored far above his
numbers — that usually washes out, so no star. Defenders add a second
ledger: Player H's team conceded 9 against an xGC of 7.0, so his side has
been unlucky at the back too (goalkeepers use only that second ledger).
Any margin above zero earns the star.</p></div>"""

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
<p>Before any factor is scored, a player must average <b>45+ minutes per
gameweek over the last 4 gameweeks</b> (180 in total). Minutes of
<span class="calc">90, 90, 30, 75 = 285</span> → rated. Minutes of
<span class="calc">60, 0, 90, 20 = 170</span> → not rated at all, whatever
the underlying numbers say. No factor can rescue a player who doesn't
play.</p></div>"""

    return (f"<section id='examples'><h2>How each factor is calculated — "
            f"worked examples</h2>"
            f"<p class='note'>Every number in this section is made up, "
            f"chosen so the sums are easy to follow. The real model runs "
            f"exactly this arithmetic over every eligible player, inside "
            f"each position (GK / DEF / MID / FWD).</p>"
            f"{quality}{value}{form}{justice}{crowd}{gate}</section>")


def picks_table(block) -> str:
    rows = []
    for r in block.itertuples():
        rows.append(
            f"<tr><td><span class='stars'>{'★' * r.stars}</span></td>"
            f"<td>{esc(r.name)}</td><td>{esc(r.team)}</td>"
            f"<td class='num'>£{r.price:.1f}m</td>"
            f"<td><span class='letters'>{esc(r.factor_letters)}</span></td>"
            f"<td class='num'>{r.xpts90:.1f}</td>"
            f"<td class='num'>{fmt_selected(r.selected)}</td></tr>")
    head = ("<tr><th>Stars</th><th>Player</th><th>Team</th>"
            "<th class='num'>Price</th><th>Factors</th>"
            "<th class='num'>xPts/90</th><th class='num'>Owned</th></tr>")
    return f"<div class='tablewrap'><table>{head}{''.join(rows)}</table></div>"


def build(data_dir: Path, out: Path) -> None:
    rated = model.rate_season(data_dir)
    picks = model.recommendations(rated, min_stars=4)
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
<title>FPL five-factor picks — {esc(season)} through GW{through}</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><h1>FPL five-factor picks</h1>
<p class="sub">An additive binary-factor model for weekly Fantasy Premier
League picks — one star per factor, judged against position peers, in the
family of <code>march_madness/</code> and <code>nfl_report/</code>.</p></header>
<div class="banner">Season <b>{esc(season)}</b>, rated through
<b>GW{through}</b>. {int(rated['eligible'].sum())} players pass the minutes
gate; 4★ and 5★ picks below (top {PER_POSITION} per position).{thin}</div>
<section><h2>The five factors</h2>
<div class="tablewrap"><table>{factor_rows}</table></div>
<p class="note">Eligibility gate: 45+ minutes per gameweek averaged over the
last {model.MINUTES_WINDOW} gameweeks — no factor can rescue a player who
doesn't play. <a href="#examples">Worked examples of every factor below
↓</a></p></section>
{''.join(sections)}
<section><h2>Captain shortlist</h2>
<p class="note">{cap or 'No 4★+ attackers yet.'}</p></section>
{examples_html()}
<section><h2>Refresh</h2>
<p class="note"><code>python fetch_data.py</code> after a gameweek finishes,
then <code>python weekly_report.py</code> for the terminal view and
<code>python build_site.py</code> to regenerate this page. The full rated
table for every player is written to <code>reports/</code>.</p></section>
<footer>Generated {date.today().isoformat()} · fantasy_premier_league ·
five-factor model</footer>
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
