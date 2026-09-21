"""Generate ``index.html``: a self-contained, phone-friendly season report.

Reads whatever is in ``data/`` and writes one page - season tabs, the betting
record, a cumulative-profit chart, the round-by-round table and the club x round
heatmaps. Everything is inlined, so the file works from a raw URL or off disk
with no server and no assets.

Until handicaps are entered there is nothing to report, so the page leads with
what is still missing rather than rendering empty furniture.

Run: ``python build_site.py``
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd

import heatmaps
import season_report
import teams

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
JUICE = 1.1  # units lost per losing bet at full 10% juice
# Permanent home: GitHub Pages serves the repo root from the default branch.
PAGES_URL = "https://zenoonan.github.io/Research/rugby_urc/"

CSS = """
:root{color-scheme:light;
 --surface-0:#f4f3f0;--surface-1:#fcfcfb;--surface-2:#eceae5;
 --text-primary:#0b0b0b;--text-secondary:#52514e;--text-muted:#77756f;
 --line:#dcdad4;--series-1:#2a78d6;--pos:#2a78d6;--neg:#e34948;--accent:#1f3864;}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;
 --surface-0:#121211;--surface-1:#1a1a19;--surface-2:#242422;
 --text-primary:#fff;--text-secondary:#c3c2b7;--text-muted:#94928a;
 --line:#34342f;--series-1:#3987e5;--pos:#3987e5;--neg:#e66767;--accent:#9db8e8;}}
:root[data-theme="dark"]{color-scheme:dark;
 --surface-0:#121211;--surface-1:#1a1a19;--surface-2:#242422;
 --text-primary:#fff;--text-secondary:#c3c2b7;--text-muted:#94928a;
 --line:#34342f;--series-1:#3987e5;--pos:#3987e5;--neg:#e66767;--accent:#9db8e8;}
*{box-sizing:border-box}
body{margin:0;padding:0 16px 64px;background:var(--surface-0);color:var(--text-primary);
 font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
.wrap{max-width:1080px;margin:0 auto}
header{padding:28px 0 8px}
h1{font-size:1.6rem;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:1.15rem;margin:32px 0 10px;letter-spacing:-.01em}
h3{font-size:.95rem;margin:20px 0 8px;color:var(--text-secondary);font-weight:600}
.sub{color:var(--text-secondary);margin:0 0 14px}
.card{background:var(--surface-1);border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:10px;margin:14px 0}
.tile{background:var(--surface-1);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.tile .k{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted)}
.tile .v{font-size:1.5rem;font-weight:650;letter-spacing:-.02em;margin-top:2px;
 font-variant-numeric:tabular-nums}
.pos{color:var(--pos)}.neg{color:var(--neg)}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 0}
.tabs button{font:inherit;font-weight:600;padding:7px 14px;border-radius:999px;cursor:pointer;
 border:1px solid var(--line);background:var(--surface-1);color:var(--text-secondary)}
.tabs button[aria-selected="true"]{background:var(--accent);border-color:var(--accent);color:var(--surface-1)}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"]))
 .tabs button[aria-selected="true"]{color:#121211}}
:root[data-theme="dark"] .tabs button[aria-selected="true"]{color:#121211}
.panel[hidden]{display:none}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.85rem;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}
th{color:var(--text-muted);font-weight:600;font-size:.74rem;text-transform:uppercase;letter-spacing:.05em}
th:first-child,td:first-child,td.l,th.l{text-align:left}
tbody tr:hover{background:var(--surface-2)}
.bet{font-weight:650}
.res-w{color:var(--pos);font-weight:650}.res-l{color:var(--neg);font-weight:650}
.pending{color:var(--text-muted)}
.heat table{font-size:.72rem}
.heat td{padding:3px 5px;text-align:center;border:1px solid var(--surface-1);
 background:var(--lbg);color:var(--lfg)}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .heat td{background:var(--dbg);color:var(--dfg)}}
:root[data-theme="dark"] .heat td{background:var(--dbg);color:var(--dfg)}
.heat td.na{background:transparent}
.heat th{position:sticky;left:0;background:var(--surface-1)}
figcaption{font-size:.85rem;color:var(--text-secondary);margin-bottom:6px}
.empty{color:var(--text-muted);font-style:italic;margin:8px 0}
.todo li{margin:6px 0}
.todo code{background:var(--surface-2);padding:1px 5px;border-radius:4px;font-size:.85em}
.chart{position:relative;max-width:760px;margin:12px auto}
.chart svg{display:block;width:100%;height:auto;touch-action:pan-y;overflow:visible}
.tip{position:absolute;pointer-events:none;opacity:0;transition:opacity .1s;
 background:var(--text-primary);color:var(--surface-1);padding:5px 9px;border-radius:7px;
 font-size:.76rem;white-space:nowrap;transform:translate(-50%,-135%);font-variant-numeric:tabular-nums}
footer{margin-top:40px;color:var(--text-muted);font-size:.8rem}
"""

JS = """
document.querySelectorAll('.tabs').forEach(function(bar){
  bar.addEventListener('click', function(e){
    var b = e.target.closest('button'); if(!b) return;
    bar.querySelectorAll('button').forEach(function(x){ x.setAttribute('aria-selected', x===b); });
    document.querySelectorAll('.panel').forEach(function(p){ p.hidden = (p.id !== b.dataset.panel); });
  });
});
document.querySelectorAll('.chart').forEach(function(chart){
  var svg = chart.querySelector('svg'); if(!svg) return;
  var tip = chart.querySelector('.tip');
  var pts = JSON.parse(chart.dataset.points || '[]'); if(!pts.length) return;
  var dot = svg.querySelector('.cursor'), rule = svg.querySelector('.crosshair');
  function move(ev){
    var r = svg.getBoundingClientRect();
    var cx = ((ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left) / r.width * 1000;
    var best = pts[0];
    pts.forEach(function(p){ if(Math.abs(p.x-cx) < Math.abs(best.x-cx)) best = p; });
    dot.setAttribute('cx', best.x); dot.setAttribute('cy', best.y);
    dot.style.opacity = 1; rule.setAttribute('x1', best.x); rule.setAttribute('x2', best.x);
    rule.style.opacity = 1;
    tip.style.opacity = 1;
    tip.style.left = (best.x / 1000 * r.width) + 'px';
    tip.style.top = (best.y / 400 * r.height) + 'px';
    tip.textContent = best.label;
  }
  function leave(){ dot.style.opacity = 0; rule.style.opacity = 0; tip.style.opacity = 0; }
  svg.addEventListener('mousemove', move); svg.addEventListener('mouseleave', leave);
  svg.addEventListener('touchmove', move); svg.addEventListener('touchend', leave);
});
"""


def esc(x) -> str:
    return html.escape("" if pd.isna(x) else str(x))


def fmt_signed(x, dp: int = 1) -> str:
    return "" if pd.isna(x) else f"{float(x):+.{dp}f}"


def stats(df: pd.DataFrame) -> dict:
    graded = df[df["result"].notna()]
    w = int((graded["result"] == "W").sum())
    l = int((graded["result"] == "L").sum())
    return {"matches": len(df), "priced": int(df["line"].notna().sum()),
            "played": int(df["home_score"].notna().sum()),
            "bets": int(df["system_bet"].notna().sum()),
            "w": w, "l": l,
            "win_rate": w / (w + l) if (w + l) else None,
            "profit": w - JUICE * l}


def tiles(s: dict) -> str:
    rate = "—" if s["win_rate"] is None else f"{s['win_rate']:.0%}"
    cls = "pos" if s["profit"] > 0 else "neg" if s["profit"] < 0 else ""
    items = [("Matches", str(s["matches"]), ""), ("Priced", str(s["priced"]), ""),
             ("Played", str(s["played"]), ""), ("Bets", str(s["bets"]), ""),
             ("Record", f"{s['w']}–{s['l']}", ""), ("Win rate", rate, ""),
             ("Profit (units)", f"{s['profit']:+.1f}", cls)]
    return ('<div class="tiles">' + "".join(
        f'<div class="tile"><div class="k">{k}</div>'
        f'<div class="v {c}">{v}</div></div>' for k, v, c in items) + "</div>")


def profit_chart(df: pd.DataFrame) -> str:
    """Cumulative profit over settled bets: one series, so no legend box."""
    graded = df[df["result"].notna()].copy()
    if graded.empty:
        return '<p class="empty">No settled bets yet — the profit curve starts once results are in.</p>'

    running, series = 0.0, []
    for r in graded.itertuples():
        running += 1.0 if r.result == "W" else -JUICE
        series.append((r.date, r.home, r.away, r.result, running))

    W, H, PAD_L, PAD_R, PAD_T, PAD_B = 1000, 400, 52, 16, 20, 34
    lo = min(0.0, min(p[4] for p in series))
    hi = max(0.0, max(p[4] for p in series))
    span = (hi - lo) or 1.0
    lo, hi = lo - span * 0.12, hi + span * 0.12
    n = len(series)

    def X(i): return PAD_L + (W - PAD_L - PAD_R) * (i / max(n - 1, 1))
    def Y(v): return PAD_T + (H - PAD_T - PAD_B) * (1 - (v - lo) / (hi - lo))

    pts = [{"x": round(X(i), 1), "y": round(Y(p[4]), 1),
            "label": f"{p[0]} · {p[1]} v {p[2]} · {p[3]} · {p[4]:+.1f}u"}
           for i, p in enumerate(series)]
    path = " ".join(("M" if i == 0 else "L") + f"{q['x']:.1f} {q['y']:.1f}"
                    for i, q in enumerate(pts))

    ticks = []
    step = max(1.0, round(span / 4))
    v = lo - (lo % step)
    while v <= hi:
        if lo <= v <= hi:
            ticks.append(f'<line class="grid" x1="{PAD_L}" x2="{W - PAD_R}" '
                         f'y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                         f'<text class="ax" x="{PAD_L - 8}" y="{Y(v) + 4:.1f}" '
                         f'text-anchor="end">{v:+.0f}</text>')
        v += step
    last = pts[-1]
    end_colour = "var(--pos)" if series[-1][4] >= 0 else "var(--neg)"

    return f"""<figure class="chart" data-points='{html.escape(json.dumps(pts))}'>
<figcaption>Cumulative profit, units, at full juice (a loss costs {JUICE}u)</figcaption>
<svg viewBox="0 0 {W} {H}" role="img"
 aria-label="Cumulative profit across {n} settled bets, ending at {series[-1][4]:+.1f} units">
 <style>.grid{{stroke:var(--line);stroke-width:1}}.ax{{fill:var(--text-muted);font-size:24px;
 font-family:inherit}}.zero{{stroke:var(--text-muted);stroke-width:1.5;stroke-dasharray:5 5}}</style>
 {''.join(ticks)}
 <line class="zero" x1="{PAD_L}" x2="{W - PAD_R}" y1="{Y(0):.1f}" y2="{Y(0):.1f}"/>
 <line class="crosshair" y1="{PAD_T}" y2="{H - PAD_B}" x1="0" x2="0"
  stroke="var(--text-muted)" stroke-width="1.5" style="opacity:0"/>
 <path d="{path}" fill="none" stroke="var(--series-1)" stroke-width="2.5"
  stroke-linejoin="round" stroke-linecap="round"/>
 <circle cx="{last['x']:.1f}" cy="{last['y']:.1f}" r="6" fill="{end_colour}"
  stroke="var(--surface-1)" stroke-width="2"/>
 <text class="ax" x="{max(last['x'] - 10, PAD_L):.1f}" y="{last['y'] - 14:.1f}"
  text-anchor="end" fill="{end_colour}" font-weight="700">{series[-1][4]:+.1f}u</text>
 <circle class="cursor" r="5" fill="var(--series-1)" stroke="var(--surface-1)"
  stroke-width="2" style="opacity:0"/>
</svg><div class="tip"></div></figure>"""


def report_table(df: pd.DataFrame) -> str:
    rows = []
    for r in df.itertuples():
        if r.result == "W":
            res = '<td class="res-w">W</td>'
        elif r.result == "L":
            res = '<td class="res-l">L</td>'
        elif isinstance(r.system_bet, str):
            res = '<td class="pending">·</td>'
        else:
            res = "<td></td>"
        score = (f"{int(r.home_score)}–{int(r.away_score)}"
                 if pd.notna(r.home_score) else '<span class="pending">—</span>')
        # A System # of 0 with no power ratings means "not evaluated", not "the
        # factors cancelled out": show it as pending rather than as a score.
        rated = pd.notna(r.home_power) and pd.notna(r.away_power)
        system = (f"<strong>{int(r.system_num):+d}</strong>" if rated
                  else '<span class="pending" title="no power ratings yet">—</span>')
        rows.append(
            f"<tr><td class='l'>{esc(r.date)}</td><td>{int(r.round)}</td>"
            f"<td class='l'>{esc(r.home)}</td><td class='l'>{esc(r.away)}</td>"
            f"<td>{fmt_signed(r.line)}</td><td>{score}</td>"
            f"<td>{fmt_signed(r.home_lgt, 0)}</td><td>{fmt_signed(r.home_stdc, 0)}</td>"
            f"<td>{fmt_signed(r.home_power)}</td>"
            f"<td>{fmt_signed(r.away_lgt, 0)}</td><td>{fmt_signed(r.away_stdc, 0)}</td>"
            f"<td>{fmt_signed(r.away_power)}</td><td>{system}</td>"
            f"<td class='l bet'>{esc(r.system_bet)}</td>{res}</tr>")
    head = ("<tr><th class='l'>Date</th><th>Rd</th><th class='l'>Home</th>"
            "<th class='l'>Away</th><th>Line</th><th>Score</th>"
            "<th>H LGT</th><th>H STDC</th><th>H Pow</th>"
            "<th>A LGT</th><th>A STDC</th><th>A Pow</th>"
            "<th>Sys #</th><th class='l'>Bet</th><th>Res</th></tr>")
    return (f'<div class="scroll"><table><thead>{head}</thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>")


def fixtures_table(df: pd.DataFrame) -> str:
    rows = "".join(
        f"<tr><td class='l'>{esc(r.date.date() if pd.notna(r.date) else '')}</td>"
        f"<td>{int(r.round)}</td><td class='l'>{esc(r.home)}</td>"
        f"<td class='l'>{esc(r.away)}</td>"
        f"<td>{'' if pd.isna(r.line) else fmt_signed(r.line)}</td></tr>"
        for r in df.itertuples())
    return ('<div class="scroll"><table><thead><tr><th class="l">Date</th><th>Rd</th>'
            '<th class="l">Home</th><th class="l">Away</th><th>Line</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>")


FACTOR_LEGEND = """
<div class="card"><h3>The five factors</h3>
<p class="sub">Each votes +1 for the home side, −1 for the away side or 0. Their sum is the
System #; the system bets home at +3 or more and away at −3 or less, and passes otherwise.</p>
<div class="scroll"><table><thead><tr><th>#</th><th class="l">Factor</th>
<th class="l">Votes home when…</th></tr></thead><tbody>
<tr><td>1</td><td class="l">Power / over-reaction</td><td class="l">the handicap makes home a
 bigger underdog than the ratings imply</td></tr>
<tr><td>2</td><td class="l">Turnover — home</td><td class="l">home lost the turnover count last time out</td></tr>
<tr><td>3</td><td class="l">Turnover — away</td><td class="l">away won the turnover count last time out</td></tr>
<tr><td>4</td><td class="l">Hunger — home</td><td class="l">home has been failing to cover</td></tr>
<tr><td>5</td><td class="l">Hunger — away</td><td class="l">away has been covering</td></tr>
</tbody></table></div></div>"""


def status_panel(seasons: dict[int, pd.DataFrame]) -> str:
    """What the model still needs before it can pick - the page's lead item."""
    needs: list[str] = []
    cur = seasons.get(2026)
    prior = seasons.get(2025)
    if prior is None or prior.empty:
        needs.append("<strong>2025-26 seed data.</strong> The last four regular rounds' "
                     "handicaps (to fit the opening power ratings) and every club's "
                     "final-match turnover counts (to seed round 1's LGT). Without it "
                     "the model has no ratings and declines every pick. "
                     "Fill <code>entry/urc_2025_entry.xlsx</code>.")
    if cur is not None and not cur.empty:
        rounds = sorted(int(r) for r in cur["round"].dropna().unique())
        if len(rounds) < season_report.REGULAR_ROUNDS:
            have = (f"round {rounds[0]}" if len(rounds) == 1
                    else f"rounds {rounds[0]}–{rounds[-1]}")
            missing = [r for r in range(1, season_report.REGULAR_ROUNDS + 1)
                       if r not in rounds]
            needs.append(f"<strong>{len(missing)} of the 18 rounds of the 2026-27 "
                         f"fixture list.</strong> Only {have} loaded. Paste the "
                         f"published list into a text file and run "
                         f"<code>python import_fixtures.py paste.txt --season 2026</code>.")
        unpriced = int(cur["line"].isna().sum())
        if unpriced:
            needs.append(f"<strong>{unpriced} handicap{'s' if unpriced > 1 else ''}.</strong> "
                         "Enter in <code>entry/urc_2026_entry.xlsx</code>, "
                         "negative when the home side is favoured.")
    if not needs:
        return ""
    return ('<div class="card"><h3>What the model still needs</h3><ul class="todo">'
            + "".join(f"<li>{n}</li>" for n in needs) + "</ul></div>")


def build() -> Path:
    seasons = {y: season_report.load_season(y) for y in season_report.available_seasons()}
    reports: dict[int, pd.DataFrame] = {}
    for year in sorted(seasons, reverse=True):
        path = DATA_DIR / f"report_{year}.csv"
        if path.exists():
            reports[year] = pd.read_csv(path)

    tabs, panels = [], []
    listed = sorted(set(seasons) | set(reports), reverse=True)
    for i, year in enumerate(listed):
        label = season_report.season_label(year)
        tabs.append(f'<button role="tab" data-panel="s{year}" '
                    f'aria-selected="{str(i == 0).lower()}">{label}</button>')
        report = reports.get(year)
        if report is not None and len(report):
            body = (tiles(stats(report)) + profit_chart(report)
                    + f"<h3>Every match</h3>{report_table(report)}"
                    + "<h3>Season to date cover, club × round</h3>"
                    + heatmaps.heatmap_html(heatmaps.club_round_pivot(report, "stdc"),
                                            decimals=0, caption="Blue = covering (“fat”), red = hungry")
                    + "<h3>Power rating, club × round</h3>"
                    + heatmaps.heatmap_html(heatmaps.club_round_pivot(report, "power"),
                                            decimals=1, caption="Blue = stronger"))
        else:
            fixtures = seasons.get(year)
            body = ('<p class="empty">No priced matches yet, so there is nothing to '
                    'report. The fixtures loaded so far:</p>'
                    + (fixtures_table(fixtures) if fixtures is not None and len(fixtures)
                       else '<p class="empty">No fixtures loaded.</p>'))
        panels.append(f'<section class="panel" id="s{year}" '
                      f'{"" if i == 0 else "hidden"}>{body}</section>')

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>URC Report</title>
<link rel="canonical" href="{PAGES_URL}">
<style>{CSS}</style></head>
<body><div class="wrap">
<header><h1>🏉 URC Report</h1>
<p class="sub">The five-factor against-the-spread system, ported from
<code>nfl_report</code> to the United Rugby Championship. Nothing here is
validated on rugby yet — that is what the season is for.</p></header>
{status_panel(seasons)}
<div class="tabs" role="tablist">{''.join(tabs)}</div>
{''.join(panels)}
{FACTOR_LEGEND}
<footer>Built by <code>build_site.py</code> from the CSVs in <code>data/</code>.
Handicaps are from the home side's point of view: negative means home favoured.
{len(teams.TEAMS)} clubs, {season_report.REGULAR_ROUNDS} regular rounds.<br>
Permanent link: <a href="{PAGES_URL}">{PAGES_URL}</a></footer>
</div><script>{JS}</script></body></html>"""

    out = HERE / "index.html"
    out.write_text(page, encoding="utf-8")
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path.relative_to(HERE)} ({path.stat().st_size / 1024:.0f} KB)")
