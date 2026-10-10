"""Generate a self-contained, mobile-friendly HTML view of the reports.

Reads every data/report_<year>.csv and writes index.html: season summary cards,
a cumulative-profit chart, the five-factor explainer and the full game-by-game
tables with the system's bets highlighted. No external assets, so the page can
be served from GitHub Pages or opened as a file.

2015 and 2016 are parsed from Aaron Brown's published reports (the replication
target); the other seasons are generated from raw data by season_report.py.
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import factor_analysis
import heatmaps
import ledger

HERE = Path(__file__).parent
# Display order, most recent first. 2010-2016 are Brown's published reports.
SEASONS = (2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018,
           2016, 2015, 2014, 2013, 2012, 2011, 2010)
PUBLISHED = {2010, 2011, 2012, 2013, 2014, 2015, 2016}
JUICE = 1.1  # units lost per losing bet at full 10% juice


def season_label(year: int) -> str:
    """Start year -> 'YYYY–YY' span (a season runs Sept–Feb)."""
    return f"{year}–{str(year + 1)[2:]}"


# Picks published only after their game had kicked off, keyed (week, home).
# They come from pre-game data alone, so the system's record keeps them, but
# nobody could have bet them: week 1 of 2026 was set up on the Sunday
# afternoon, and week 5's Thursday game was priced the day after because week
# 4's turnovers arrived after it was played.
LATE_PICKS = {
    2026: {(1, "Jaguars"), (1, "Chargers"), (1, "Vikings"), (1, "Eagles"), (5, "Cowboys")},
}


def is_late(year: int, r) -> bool:
    return (int(r.week), r.home) in LATE_PICKS.get(year, set())


def late_pick_note(year: int, df: pd.DataFrame) -> str:
    """How the record reads without the picks published after kick-off."""
    if year not in LATE_PICKS:
        return ""
    late = df.apply(lambda r: is_late(year, r), axis=1)
    s = season_stats(df[~late])
    n = int(late.sum())
    return (f" <b>&dagger;</b> {n} picks were published only after their game had "
            f"kicked off (from pre-game data, so they count, but could not have been "
            f"bet). Counting only picks published before kick-off: "
            f"{s['wins']}&ndash;{s['losses']}, {s['profit']:+.1f}u.")


def season_note(year: int) -> str | None:
    if year in PUBLISHED:
        return ("Parsed from Aaron Brown’s published report — the replication "
                "target. Every bet and result here is reproduced by the model.")
    base = ("Generated from raw odds + results data by <code>season_report.py</code>, "
            "not a published sheet.")
    if year == 2018:
        return base + (" The earliest season on file, so week 1 has no last-game "
                       "turnovers or power ratings to carry over.")
    if year == 2026:
        return base + (" <b>Season in progress.</b> Week 1 is seeded from 2025–26. "
                       "The table covers the weeks priced so far; a pick on a game "
                       "not yet played shows a &middot; and stays out of the record. "
                       "A week is only picked once the previous week&rsquo;s turnovers "
                       "are in, since two of the five factors depend on them.")
    return base + " Week 1 is seeded from the prior season (last-game turnovers and power)."

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
.tabs { display: flex; gap: 8px; margin: 12px 0; overflow-x: auto; }
.tabs button {
  flex: 1 0 auto; padding: 10px; font-size: 16px; font-weight: 600; cursor: pointer;
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
.chip.N { background: transparent; color: var(--muted); border: 1px dashed var(--border); }
.pending { color: var(--muted); font-style: italic; }
body.betsonly tr.nobet { display: none; }
.factors { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 4px 14px; margin-top: 12px; font-size: 14px; }
.factors li { margin: 8px 0; }
.factors b { color: var(--accent); }
.seasonnote { font-size: 13px; color: var(--muted); margin: 10px 2px 0; }
table.diag td.pos { color: var(--win); font-weight: 600; }
table.diag td.neg { color: var(--loss); font-weight: 600; }
table.diag td.prov { color: var(--muted); font-style: italic; }
table.diag td.prov small { font-size: 10px; margin-left: 2px; }
.diagnote { font-size: 13px; color: var(--muted); margin: 8px 2px 14px; }
table.heat { font-size: 11px; }
table.heat th, table.heat td { padding: 3px 5px; text-align: center; border: 1px solid #fff; }
table.heat th { background: var(--card); color: var(--muted); }
table.heat td.l, table.heat th.l { text-align: left; white-space: nowrap; font-size: 12px; }
table.heat td.hm { color: #1c2733; min-width: 26px; }
table.heat td.hm.na { background: #f4f6f8; }
table.mybets td.pos { color: var(--win); font-weight: 600; }
table.mybets td.neg { color: var(--loss); font-weight: 600; }
table.mybets td.note { color: var(--muted); font-size: 12px; }
table.mybets tfoot td { font-weight: 700; }
.seasonnote + .tablewrap { margin-top: 10px; }
h3 { font-size: 15px; margin: 18px 0 8px; }
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


def played(df: pd.DataFrame) -> pd.Series:
    """Games with a final score. False for a live season's upcoming fixtures."""
    return df.home_score.notna() & df.away_score.notna()


def season_stats(df: pd.DataFrame) -> dict:
    bets = df[df.system_bet.notna()]
    w = int((bets.result == "W").sum())
    l = int((bets.result == "L").sum())
    # An unplayed bet is pending, not a push.
    pending = int((bets.result.isna() & ~played(bets)).sum())
    return {
        "games": len(df),
        "bets": len(bets),
        "wins": w,
        "losses": l,
        "pushes": int(bets.result.isna().sum()) - pending,
        "pending": pending,
        "winrate": w / (w + l) if (w + l) else float("nan"),
        "profit": w - JUICE * l,
    }


def profit_chart(df: pd.DataFrame) -> str:
    """Inline SVG of cumulative units (full juice) over the season's graded bets."""
    series = [0.0]
    for r in df[df.result.notna()].itertuples():
        series.append(series[-1] + (1.0 if r.result == "W" else -JUICE))
    if len(series) < 2:  # a live season with no graded bets yet
        return ('<p class="pending" style="margin:0;text-align:center">'
                'No settled bets yet &mdash; the chart starts once results land.</p>')

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


PLAYOFF_ROUNDS = ["WC", "Div", "Conf", "SB"]


def week_labels(year: int, weeks: pd.Series) -> dict[int, str]:
    """Week number -> table label: regular weeks as numbers, playoff rounds by
    name. The regular season ran 17 weeks until 2020 and 18 since; the weeks
    after it are the playoff rounds in order (derived weeks for the published
    seasons skip the Super Bowl's bye week, so order, not number, names them)."""
    regular = 17 if year <= 2020 else 18
    labels = {int(w): str(int(w)) for w in weeks.unique() if w <= regular}
    playoff = sorted(int(w) for w in weeks.unique() if w > regular)
    labels.update(zip(playoff, PLAYOFF_ROUNDS))
    return labels


def game_row(r, week: str, late: bool = False) -> str:
    is_bet = isinstance(r.system_bet, str)
    is_played = not (pd.isna(r.home_score) or pd.isna(r.away_score))
    if not is_bet:
        result = ""
    elif r.result == "W":
        result = '<span class="chip W">W</span>'
    elif r.result == "L":
        result = '<span class="chip L">L</span>'
    elif not is_played:
        result = '<span class="chip N">&middot;</span>'  # pick stands, not yet played
    else:
        result = '<span class="chip P">P</span>'
    score = (f"{int(r.home_score)}&ndash;{int(r.away_score)}" if is_played
             else '<span class="pending">vs</span>')
    return (
        f'<tr class="{"bet" if is_bet else "nobet"}">'
        f"<td>{week}</td>"
        f'<td class="l">{fmt_date(r.date)}</td>'
        f'<td class="l">{team(r.home)}</td>'
        f'<td class="l">{team(r.away)}</td>'
        f"<td>{fmt_pts(r.line)}</td>"
        f"<td>{score}</td>"
        f"<td>{fmt_signed(r.home_lgt)}</td>"
        f"<td>{fmt_signed(r.home_stdc)}</td>"
        f"<td>{fmt_pts(r.home_power)}</td>"
        f"<td>{fmt_signed(r.away_lgt)}</td>"
        f"<td>{fmt_signed(r.away_stdc)}</td>"
        f"<td>{fmt_pts(r.away_power)}</td>"
        f"<td>{r.system_num:+d}</td>"
        f'<td class="l">{team(r.system_bet) if is_bet else ""}'
        f'{"&dagger;" if is_bet and late else ""}</td>'
        f"<td>{result}</td>"
        f"</tr>"
    )


def season_panel(year: int, df: pd.DataFrame, active: bool) -> str:
    s = season_stats(df)
    profit_cls = "pos" if s["profit"] >= 0 else "neg"
    graded = s["wins"] + s["losses"]
    sub = ", ".join(
        part for part in (
            f'{s["pushes"]} push{"es" if s["pushes"] != 1 else ""}' if s["pushes"] else "",
            f'{s["pending"]} pending' if s["pending"] else "",
        ) if part) or "0 pushes"
    cards = f"""
    <div class="cards">
      <div class="card"><div class="num">{s["games"]}</div><div class="lbl">Games</div></div>
      <div class="card"><div class="num">{s["bets"]}</div><div class="lbl">Bets</div></div>
      <div class="card"><div class="num">{s["wins"]}&ndash;{s["losses"]}</div>
        <div class="lbl">Record ({sub})</div></div>
      <div class="card"><div class="num">{f'{s["winrate"]:.1%}' if graded else "&mdash;"}</div>
        <div class="lbl">Win rate</div></div>
      <div class="card"><div class="num {profit_cls}">{s["profit"]:+.1f}u</div>
        <div class="lbl">Profit at full juice</div></div>
    </div>"""

    df = with_week(df)
    note = (season_note(year) or "") + late_pick_note(year, df)
    note_html = f'\n    <p class="seasonnote">{note}</p>' if note else ""
    labels = week_labels(year, df["week"])
    rows = "\n".join(game_row(r, labels[int(r.week)], is_late(year, r))
                     for r in df.itertuples())
    return f"""
  <section class="panel{" active" if active else ""}" id="season-{year}">
    {cards}{note_html}
    <div class="chart-card">
      {profit_chart(df)}
      <div class="cap">Cumulative units over the season&rsquo;s {s["wins"] + s["losses"]} graded bets
      (win +1, loss &minus;{JUICE}). Dashed line is break-even.</div>
    </div>
    {my_bets_block(year, df)}
    <h2>Game by game &mdash; {season_label(year)}</h2>
    <label class="toggle"><input type="checkbox" checked onchange="toggleBets(this)">
      Show only games the system bet</label>
    <div class="tablewrap">
      <table>
        <thead><tr>
          <th>Wk</th><th class="l">Date</th><th class="l">Home</th><th class="l">Away</th>
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
    {heatmaps_block(df)}
  </section>"""


LEDGER_URL = "https://claude.ai/artifact/VdSjxhm3iL73Db3LMdmmz6"


def money(x: float) -> str:
    c = round(x * 100)
    return "&euro;0.00" if c == 0 else f'{"+" if c > 0 else "&minus;"}&euro;{abs(c) / 100:.2f}'


def euros(x: float) -> str:
    return f"&euro;{x:.2f}" if round(x * 100) % 100 else f"&euro;{x:.0f}"


def money_cell(x) -> str:
    if x is None or pd.isna(x):
        return '<td class="pending">&mdash;</td>'
    return f'<td class="{"pos" if x > 0.005 else "neg" if x < -0.005 else ""}">{money(x)}</td>'


def tally(res: pd.Series, pnl: pd.Series, stake: pd.Series) -> dict:
    done = res.notna()
    t = {k: int((res == k).sum()) for k in ("W", "L", "P")}
    return {**t, "settled": int(done.sum()), "open": int((~done).sum()),
            "pnl": float(pnl[done].sum()), "staked": float(stake[done].sum())}


def record(t: dict) -> str:
    if not t["settled"]:
        return "&mdash;"
    return f'{t["W"]}&ndash;{t["L"]}' + (f'&ndash;{t["P"]}' if t["P"] else "")


def my_bets_block(year: int, df: pd.DataFrame) -> str:
    """The season's real bets (from the bet ledger) beside the system's record."""
    bets = ledger.load_bets(year)
    if bets is None or bets.empty:
        return ""
    bets = ledger.settle(bets, df)
    singles = bets[bets.kind == "single"]
    builders = bets[bets.kind == "builder"]
    stake = float(singles.stake.median()) if len(singles) else 25.0

    # The system: every pick at that stake, at -110. A played pick with no
    # result is a push; an unplayed one is pending.
    picks = df[df.system_bet.notna()].copy()
    done = picks.home_score.notna() & picks.away_score.notna()
    picks["res"] = np.where(picks.result.isin(["W", "L"]), picks.result,
                            np.where(done, "P", None))
    picks["pnl"] = picks.res.map({"W": stake * (ledger.STD_ODDS - 1), "L": -stake, "P": 0.0})
    picks["stake"] = stake

    sys_t = tally(picks.res, picks.pnl, picks.stake)
    mine_t = tally(singles.res, singles.pnl, singles.stake)
    bld_t = tally(builders.res, builders.pnl, builders.stake)
    roi = lambda t: (f'{t["pnl"] / t["staked"]:+.1%}'.replace("-", "&minus;")
                     if t["staked"] else "&mdash;")
    summary = f"""
    <div class="tablewrap"><table class="mybets">
      <thead><tr><th class="l"></th><th>System picks</th><th>My spread bets</th></tr></thead>
      <tbody>
        <tr><td class="l">Record</td><td>{record(sys_t)}</td><td>{record(mine_t)}</td></tr>
        <tr><td class="l">Profit</td>{money_cell(sys_t["pnl"] if sys_t["settled"] else None)}{money_cell(mine_t["pnl"] if mine_t["settled"] else None)}</tr>
        <tr><td class="l">Staked</td><td>{euros(sys_t["staked"])}</td><td>{euros(mine_t["staked"])}</td></tr>
        <tr><td class="l">Return</td><td>{roi(sys_t)}</td><td>{roi(mine_t)}</td></tr>
        <tr><td class="l">Open</td><td>{f'{sys_t["open"]} pending' if sys_t["open"] else "&mdash;"}</td><td>{f'{mine_t["open"]} open' if mine_t["open"] else "&mdash;"}</td></tr>
      </tbody>
    </table></div>"""
    builders_note = (f' Bet builders {record(bld_t)}, {money(bld_t["pnl"])} on {euros(bld_t["staked"])};'
                     f' all my NFL bets {money(mine_t["pnl"] + bld_t["pnl"])}.' if len(builders) else "")

    labels = week_labels(year, df["week"])
    weeks = sorted(set(picks.loc[picks.res.notna(), "week"]) | set(bets.loc[bets.res.notna() & (bets.kind == "single"), "week"]))
    def cells(rows: pd.DataFrame) -> str:
        t = tally(rows.res, rows.pnl, rows.stake)
        return f'<td>{record(t)}</td>{money_cell(t["pnl"] if t["settled"] else None)}'

    week_rows = "\n".join(
        f'<tr><td>{labels.get(int(w), w)}</td>{cells(picks[picks.week == w])}'
        f'{cells(singles[singles.week == w])}</tr>' for w in weeks)

    def bet_row(b) -> str:
        what = (f"Bet builder ({team(b.side)})" if b.kind == "builder"
                else f"{team(b.side)} {fmt_pts(b.line)}")
        chip = (f'<span class="chip {b.res}">{b.res}</span>' if b.res
                else '<span class="chip N">&middot;</span>')
        odds = f"{b.odds:.2f}" if not pd.isna(b.odds) else "&mdash;"
        note = html.escape(b.note) if isinstance(b.note, str) else ""
        return (f'<tr><td>{labels.get(int(b.week), b.week)}</td>'
                f'<td class="l">{team(b.away)} @ {team(b.home)}</td><td class="l">{what}</td>'
                f'<td>{odds}</td><td>{euros(b.stake)}</td><td>{chip}</td>{money_cell(b.pnl)}'
                f'<td class="l note">{note}</td></tr>')

    return f"""
    <h2>My bets &mdash; {season_label(year)}</h2>
    <p class="seasonnote">The bets I actually placed, beside the system&rsquo;s own record. The
    system column is every pick at {euros(stake)} (my usual stake) at &minus;110. Bets are logged in a
    <a href="{LEDGER_URL}">private tracker</a> and copied here with each weekly update; a spread bet
    settles from the final score at the line I got.{builders_note}</p>
    {summary}
    <h3>Week by week</h3>
    <div class="tablewrap"><table class="mybets">
      <thead><tr><th>Wk</th><th>System</th><th>Profit</th><th>Me</th><th>Profit</th></tr></thead>
      <tbody>
{week_rows}
      </tbody>
      <tfoot><tr><td>Total</td><td>{record(sys_t)}</td>{money_cell(sys_t["pnl"])}<td>{record(mine_t)}</td>{money_cell(mine_t["pnl"])}</tr></tfoot>
    </table></div>
    <h3>Every bet</h3>
    <div class="tablewrap"><table class="mybets">
      <thead><tr><th>Wk</th><th class="l">Game</th><th class="l">Bet</th><th>Odds</th><th>Stake</th>
        <th>Res</th><th>Profit</th><th class="l">Note</th></tr></thead>
      <tbody>
{"".join(bet_row(b) for b in bets.itertuples())}
      </tbody>
    </table></div>"""


def with_week(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure a ``week`` column: generated reports carry it; derive it from the
    date for the published reports (collision-free there)."""
    if "week" in df.columns:
        return df
    df = df.copy()
    d = pd.to_datetime(df["date"], format="%y-%m-%d")
    anchor = d.min() - pd.Timedelta(days=(d.min().weekday() - 1) % 7)  # Tue <= first game
    df["week"] = ((d - anchor).dt.days // 7 + 1).astype(int)
    return df


def heatmaps_block(df: pd.DataFrame) -> str:
    df = with_week(df)
    stdc = heatmaps.team_week_pivot(df, "stdc")
    power = heatmaps.team_week_pivot(df, "power")
    return f"""
    <h2>Season-to-date cover by team &amp; week</h2>
    <p class="diagnote">Each team&rsquo;s net covers entering that week &mdash;
    <span style="color:#1a9850;font-weight:600">green</span> teams have been beating the
    spread (&ldquo;fat&rdquo;), <span style="color:#d73027;font-weight:600">red</span> teams
    failing to (&ldquo;hungry&rdquo;). The hunger factor backs the red ones. Sorted by season mean.</p>
    {heatmaps.heatmap_html(stdc, decimals=0)}
    <h2>Power rating by team &amp; week</h2>
    <p class="diagnote">Each team&rsquo;s fitted power rating (points above/below average) each
    week. <span style="color:#1a9850;font-weight:600">Green</span> = strong,
    <span style="color:#d73027;font-weight:600">red</span> = weak. Sorted by season mean.</p>
    {heatmaps.heatmap_html(power, decimals=0)}"""


def diagnostics_section() -> str:
    """Brown's factor diagnostics: marginal contributions + standalone rates."""
    marginal, standalone, counts = factor_analysis.build_tables()
    years = list(marginal.columns)
    head = "".join(f"<th>{season_label(y)}</th>" for y in years)

    def cell(value: float, fmt: str, pos: bool, neg: bool) -> str:
        if pd.isna(value):  # e.g. a factor with no votes yet in a live season
            return '<td class="pending">&mdash;</td>'
        cls = ' class="pos"' if pos else ' class="neg"' if neg else ""
        return f"<td{cls}>{fmt.format(value)}</td>"

    m_rows = ""
    for key in factor_analysis.FACTORS:
        cells = "".join(
            cell(v, "{:+d}", v > 0, v < 0) for v in (int(marginal.loc[key, y]) for y in years)
        )
        m_rows += f'<tr><td class="l">{factor_analysis.FACTOR_LABELS[key]}</td>{cells}</tr>\n'
    totals = marginal.sum()
    m_rows += ('<tr><td class="l"><b>Total</b></td>'
               + "".join(cell(int(totals[y]), "{:+d}", totals[y] > 0, totals[y] < 0)
                         for y in years) + "</tr>")

    def rate_cell(v: float, n: int) -> str:
        # A small sample is shown, not hidden, but not coloured against Brown's
        # 52% bar either -- at a few dozen votes that would overstate it.
        if not pd.isna(v) and n < factor_analysis.PROVISIONAL_VOTES:
            return (f'<td class="prov" title="provisional: {n} settled votes">'
                    f'{v * 100:.0f}<small>({n})</small></td>')
        return cell(v * 100, "{:.0f}", v >= 0.52, v < 0.48)

    s_rows = ""
    for key in factor_analysis.FACTORS:
        cells = "".join(rate_cell(standalone.loc[key, y], int(counts.loc[key, y]))
                        for y in years)
        s_rows += f'<tr><td class="l">{factor_analysis.FACTOR_LABELS[key]}</td>{cells}</tr>\n'

    return f"""
  <h2>Factor diagnostics</h2>
  <p class="diagnote">Brown&rsquo;s own monitoring tools, rebuilt. <b>Marginal
  contribution</b> charges a factor only on close calls its vote alone decided:
  on a bet made at exactly &plusmn;3 every aligned factor earns the result, and on a
  near-miss at &plusmn;2 every opposing factor earns the opposite of what the blocked bet
  would have done. This accounting reproduces every value in Brown&rsquo;s published
  Table&nbsp;3 exactly &mdash; all 35, across 2010&ndash;2016.</p>
  <div class="tablewrap">
    <table class="diag">
      <thead><tr><th class="l">Net wins charged</th>{head}</tr></thead>
      <tbody>
{m_rows}
      </tbody>
    </table>
  </div>
  <p class="diagnote" style="margin-top:14px"><b>Standalone success</b> treats each factor
  as its own betting rule over all games: the share of its votes that cover the spread.
  Brown&rsquo;s bar for a useful factor was 52% (green); below 48% is red.
  <i>Italic</i> figures are provisional &mdash; a season still in progress &mdash; with
  the number of settled votes in brackets, and are left uncoloured until the sample
  is large enough to judge.</p>
  <div class="tablewrap">
    <table class="diag">
      <thead><tr><th class="l">% of votes that cover</th>{head}</tr></thead>
      <tbody>
{s_rows}
      </tbody>
    </table>
  </div>"""


def build() -> Path:
    data = {year: pd.read_csv(HERE / "data" / f"report_{year}.csv") for year in SEASONS}
    stats = {year: season_stats(df) for year, df in data.items()}

    replicated = sorted(y for y in stats if y in PUBLISHED)
    total_bets = sum(stats[y]["bets"] for y in replicated)
    total_w = sum(stats[y]["wins"] for y in replicated)
    total_l = sum(stats[y]["losses"] for y in replicated)
    total_profit = sum(stats[y]["profit"] for y in replicated)

    gen = sorted(y for y in stats if y not in PUBLISHED)
    g_bets = sum(stats[y]["bets"] for y in gen)
    g_w = sum(stats[y]["wins"] for y in gen)
    g_l = sum(stats[y]["losses"] for y in gen)
    g_profit = sum(stats[y]["profit"] for y in gen)
    banner_gen = (
        f" {len(gen)} further seasons ({season_label(gen[0])} to {season_label(gen[-1])}) are "
        f"generated from raw data by the same engine: {g_bets} bets, {g_w}&ndash;{g_l} "
        f"({g_w / (g_w + g_l):.1%}), {g_profit:+.1f} units." if gen else ""
    )

    tabs = "\n".join(
        f'<button data-year="{year}"{" class=" + chr(34) + "active" + chr(34) if i == 0 else ""} '
        f'onclick="showSeason({year})">{season_label(year)}</button>'
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
    {len(replicated)} of his published reports ({replicated[0]}&ndash;{replicated[-1]}) replicated,
    plus {len(gen)} seasons generated from raw data ({gen[0]}&ndash;{gen[-1]}).</p>
  </header>

  <div class="banner">
    Replication ({season_label(replicated[0])} to {season_label(replicated[-1])}): every
    published bet and result is reproduced &mdash; {total_bets} bets,
    {total_w}&ndash;{total_l} ({total_w / (total_w + total_l):.1%}), {total_profit:+.1f} units
    at full juice. System # matches 1846/1869 games; the rest are rounding ties in the
    published one-decimal power column. The factor diagnostics below reproduce Brown&rsquo;s
    published Table&nbsp;3 exactly for all seven years.{banner_gen}
  </div>

  <div class="tabs">
{tabs}
  </div>
{panels}
{diagnostics_section()}

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
