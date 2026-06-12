"""Generate a self-contained, mobile-friendly HTML view of the replicated reports.

Reads data/report_2015.csv and data/report_2016.csv and writes index.html:
season summary cards, a cumulative-profit chart, the five-factor explainer and
the full game-by-game tables with the system's bets highlighted. No external
assets, so the page can be served from GitHub Pages or opened as a file.
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
SEASONS = (2025, 2016, 2015)  # display order: most recent first
JUICE = 1.1  # units lost per losing bet at full 10% juice

SEASON_LABELS = {2025: "2025–26", 2016: "2016", 2015: "2015"}
SEASON_NOTES = {
    2025: ("Generated from raw odds + results data by <code>season_report.py</code> "
           "(not a published sheet). Week 1 LGT/Power await the 2024 season file; "
           "the odds export has no lines for the 14 week-5 games, so they are "
           "shown but not bettable."),
}

CSS = """
:root {
  --bg: #f4f6f8; --card: #ffffff; --ink: #1c2733; --muted: #5f6b76;
  --accent: #134074; --win: #1e7d46; --loss: #b3372f; --push: #8a8f98;
  --bet-row: #eef4fb; --border: #dce3ea;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  -webkit-text-size-adjust: 100%;
}
.wrap { max-width: 980px; margin: 0 auto; padding: 16px; }
header h1 { font-size: 24px; margin: 8px 0 4px; }
header p.sub { color: var(--muted); margin: 0 0 16px; font-size: 14px; }
.banner {
  background: var(--accent); color: #fff; border-radius: 10px;
  padding: 12px 14px; font-size: 14px; margin-bottom: 16px;
}
.tabs { display: flex; gap: 8px; margin: 12px 0; }
.tabs button {
  flex: 1; padding: 10px; font-size: 16px; font-weight: 600; cursor: pointer;
  border: 1px solid var(--border); border-radius: 8px; background: var(--card);
  color: var(--ink);
}
.tabs button.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; }
.card {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  padding: 12px; text-align: center;
}
.card .num { font-size: 22px; font-weight: 700; }
.card .lbl { font-size: 12px; color: var(--muted); margin-top: 2px; }
.num.pos { color: var(--win); } .num.neg { color: var(--loss); }
section.panel { display: none; }
section.panel.active { display: block; }
h2 { font-size: 18px; margin: 24px 0 8px; }
.chart-card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 12px; margin-top: 12px; }
.chart-card svg { width: 100%; height: auto; display: block; }
.chart-card .cap { font-size: 12px; color: var(--muted); margin-top: 6px; }
.toggle { display: flex; align-items: center; gap: 8px; margin: 12px 0; font-size: 14px; }
.toggle input { width: 18px; height: 18px; }
.tablewrap { overflow-x: auto; background: var(--card); border: 1px solid var(--border); border-radius: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; white-space: nowrap; }
th, td { padding: 6px 8px; text-align: right; border-bottom: 1px solid var(--border); }
th { position: sticky; top: 0; background: var(--card); font-size: 11px; color: var(--muted); text-transform: uppercase; }
td.l, th.l { text-align: left; }
tr.bet { background: var(--bet-row); font-weight: 600; }
.chip { display: inline-block; min-width: 20px; padding: 1px 7px; border-radius: 10px; color: #fff; font-size: 12px; text-align: center; }
.chip.W { background: var(--win); } .chip.L { background: var(--loss); } .chip.P { background: var(--push); }
body.betsonly tr.nobet { display: none; }
.factors { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 4px 14px; margin-top: 12px; font-size: 14px; }
.factors li { margin: 8px 0; }
.factors b { color: var(--accent); }
.seasonnote { font-size: 13px; color: var(--muted); margin: 10px 2px 0; }
footer { color: var(--muted); font-size: 12px; margin: 24px 0; }
"""

JS = """
function showSeason(year) {
  document.querySelectorAll('section.panel').forEach(function (s) {
    s.classList.toggle('active', s.id === 'season-' + year);
  });
  document.querySelectorAll('.tabs button').forEach(function (b) {
    b.classList.toggle('active', b.dataset.year === String(year));
  });
}
function toggleBets(box) {
  document.body.classList.toggle('betsonly', box.checked);
  document.querySelectorAll('.toggle input').forEach(function (b) { b.checked = box.checked; });
}
"""


def fmt_signed(x: float) -> str:
    """LGT/STDC values: whole numbers, sign shown, 0 plain."""
    n = int(x)
    return str(n) if n == 0 else f"{n:+d}"


def fmt_pts(x: float) -> str:
    """Line/power values: one decimal with sign, blank cells as a dash."""
    return "—" if pd.isna(x) else f"{x:+.1f}"


def fmt_date(d: str) -> str:
    return datetime.strptime(d, "%y-%m-%d").strftime("%b %d")


def team(name) -> str:
    return html.escape(name) if isinstance(name, str) else "—"


def season_stats(df: pd.DataFrame) -> dict:
    bets = df[df.system_bet.notna()]
    w = int((bets.result == "W").sum())
    l = int((bets.result == "L").sum())
    return {
        "games": len(df),
        "bets": len(bets),
        "wins": w,
        "losses": l,
        "pushes": int(bets.result.isna().sum()),
        "winrate": w / (w + l),
        "profit": w - JUICE * l,
    }


def profit_chart(df: pd.DataFrame) -> str:
    """Inline SVG of cumulative units (full juice) over the season's graded bets."""
    series = [0.0]
    for r in df[df.result.notna()].itertuples():
        series.append(series[-1] + (1.0 if r.result == "W" else -JUICE))

    width, height, pad = 600, 150, 10
    lo, hi = min(min(series), 0), max(max(series), 0)
    span = (hi - lo) or 1.0

    def x(i: int) -> float:
        return pad + i * (width - 2 * pad) / (len(series) - 1)

    def y(v: float) -> float:
        return pad + (hi - v) * (height - 2 * pad) / span

    points = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(series))
    final = series[-1]
    color = "#1e7d46" if final >= 0 else "#b3372f"
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Cumulative profit, finishing at {final:+.1f} units">'
        f'<line x1="{pad}" y1="{y(0):.1f}" x2="{width - pad}" y2="{y(0):.1f}" '
        f'stroke="#b9c2cb" stroke-dasharray="4 3"/>'
        f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5"/>'
        f'<circle cx="{x(len(series) - 1):.1f}" cy="{y(final):.1f}" r="4" fill="{color}"/>'
        f"</svg>"
    )


def game_row(r) -> str:
    is_bet = isinstance(r.system_bet, str)
    if not is_bet:
        result = ""
    elif r.result == "W":
        result = '<span class="chip W">W</span>'
    elif r.result == "L":
        result = '<span class="chip L">L</span>'
    else:
        result = '<span class="chip P">P</span>'
    return (
        f'<tr class="{"bet" if is_bet else "nobet"}">'
        f'<td class="l">{fmt_date(r.date)}</td>'
        f'<td class="l">{team(r.home)}</td>'
        f'<td class="l">{team(r.away)}</td>'
        f"<td>{fmt_pts(r.line)}</td>"
        f"<td>{r.home_score}&ndash;{r.away_score}</td>"
        f"<td>{fmt_signed(r.home_lgt)}</td>"
        f"<td>{fmt_signed(r.home_stdc)}</td>"
        f"<td>{fmt_pts(r.home_power)}</td>"
        f"<td>{fmt_signed(r.away_lgt)}</td>"
        f"<td>{fmt_signed(r.away_stdc)}</td>"
        f"<td>{fmt_pts(r.away_power)}</td>"
        f"<td>{r.system_num:+d}</td>"
        f'<td class="l">{team(r.system_bet) if is_bet else ""}</td>'
        f"<td>{result}</td>"
        f"</tr>"
    )


def season_panel(year: int, df: pd.DataFrame, active: bool) -> str:
    s = season_stats(df)
    profit_cls = "pos" if s["profit"] >= 0 else "neg"
    cards = f"""
    <div class="cards">
      <div class="card"><div class="num">{s["games"]}</div><div class="lbl">Games</div></div>
      <div class="card"><div class="num">{s["bets"]}</div><div class="lbl">Bets</div></div>
      <div class="card"><div class="num">{s["wins"]}&ndash;{s["losses"]}</div>
        <div class="lbl">Record ({s["pushes"]} push{"es" if s["pushes"] != 1 else ""})</div></div>
      <div class="card"><div class="num">{s["winrate"]:.1%}</div><div class="lbl">Win rate</div></div>
      <div class="card"><div class="num {profit_cls}">{s["profit"]:+.1f}u</div>
        <div class="lbl">Profit at full juice</div></div>
    </div>"""

    note = SEASON_NOTES.get(year)
    note_html = f'\n    <p class="seasonnote">{note}</p>' if note else ""
    rows = "\n".join(game_row(r) for r in df.itertuples())
    return f"""
  <section class="panel{" active" if active else ""}" id="season-{year}">
    {cards}{note_html}
    <div class="chart-card">
      {profit_chart(df)}
      <div class="cap">Cumulative units over the season&rsquo;s {s["wins"] + s["losses"]} graded bets
      (win +1, loss &minus;{JUICE}). Dashed line is break-even.</div>
    </div>
    <h2>Game by game &mdash; {SEASON_LABELS.get(year, year)}</h2>
    <label class="toggle"><input type="checkbox" checked onchange="toggleBets(this)">
      Show only games the system bet</label>
    <div class="tablewrap">
      <table>
        <thead><tr>
          <th class="l">Date</th><th class="l">Home</th><th class="l">Away</th>
          <th>Line</th><th>Score</th>
          <th>H&nbsp;LGT</th><th>H&nbsp;STDC</th><th>H&nbsp;Pwr</th>
          <th>A&nbsp;LGT</th><th>A&nbsp;STDC</th><th>A&nbsp;Pwr</th>
          <th>#</th><th class="l">Bet</th><th>Res</th>
        </tr></thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </div>
  </section>"""


def build() -> Path:
    data = {year: pd.read_csv(HERE / "data" / f"report_{year}.csv") for year in SEASONS}
    stats = {year: season_stats(df) for year, df in data.items()}

    replicated = [y for y in (2015, 2016) if y in stats]
    total_bets = sum(stats[y]["bets"] for y in replicated)
    total_w = sum(stats[y]["wins"] for y in replicated)
    total_l = sum(stats[y]["losses"] for y in replicated)
    total_profit = sum(stats[y]["profit"] for y in replicated)

    s25 = stats.get(2025)
    banner_2025 = (
        f" The 2025&ndash;26 season is generated from raw data by the same engine: "
        f"{s25['bets']} bets, {s25['wins']}&ndash;{s25['losses']} "
        f"({s25['winrate']:.1%}), {s25['profit']:+.1f} units." if s25 else ""
    )

    tabs = "\n".join(
        f'<button data-year="{year}"{" class=" + chr(34) + "active" + chr(34) if i == 0 else ""} '
        f'onclick="showSeason({year})">{SEASON_LABELS.get(year, year)}</button>'
        for i, year in enumerate(SEASONS)
    )
    panels = "\n".join(
        season_panel(year, data[year], active=(i == 0)) for i, year in enumerate(SEASONS)
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NFL Report — five-factor system replication</title>
<style>{CSS}</style>
</head>
<body class="betsonly">
<div class="wrap">
  <header>
    <h1>NFL Report &mdash; five-factor system</h1>
    <p class="sub">Aaron Brown&rsquo;s demonstration NFL betting system (Wilmott magazine):
    replicated 2015 &amp; 2016 reports, plus the 2025&ndash;26 season generated from raw data.</p>
  </header>

  <div class="banner">
    Replication (2015 &amp; 2016): every published bet and result is reproduced &mdash;
    {total_bets} bets, {total_w}&ndash;{total_l} ({total_w / (total_w + total_l):.1%}),
    {total_profit:+.1f} units at full juice. System # matches 532/534 games (the 2 misses
    are rounding ties in the published power column).{banner_2025}
  </div>

  <div class="tabs">
{tabs}
  </div>
{panels}

  <h2>How the system works</h2>
  <div class="factors">
    <p>Five binary factors each vote <b>+1</b> (home), <b>&minus;1</b> (away) or 0.
    Their sum is the <b>System #</b>; the model bets home at <b>+3 or more</b>, away at
    <b>&minus;3 or less</b>, and otherwise passes.</p>
    <ol>
      <li><b>Power / over-reaction</b> &mdash; back the team the betting line has moved
        against relative to slow-moving power ratings; line moves overshoot.</li>
      <li><b>Turnover, home</b> (LGT) &mdash; back a home team that gave the ball away last
        game; turnovers are mostly luck and the line over-corrects.</li>
      <li><b>Turnover, away</b> &mdash; the same logic for the away team.</li>
      <li><b>Hunger, home</b> (STDC) &mdash; back a home team that has been failing to cover;
        bookmakers like every team to cover about half the time.</li>
      <li><b>Hunger, away</b> &mdash; the same logic for the away team.</li>
    </ol>
    <p>Column key: <b>LGT</b> last-game net giveaways &middot; <b>STDC</b> net covers season
    to date (negative = hungry) &middot; <b>Pwr</b> power rating in points &middot;
    <b>Line</b> home spread (negative = home favoured).</p>
  </div>

  <footer>
    Generated by <code>nfl_report/build_site.py</code> from the replicated report data.
    Sources and methodology: <code>nfl_report/reference/</code> in the
    <a href="https://github.com/ZeNoonan/Research">Research repository</a>.
  </footer>
</div>
<script>{JS}</script>
</body>
</html>
"""
    out = HERE / "index.html"
    out.write_text(page)
    return out


if __name__ == "__main__":
    out = build()
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
