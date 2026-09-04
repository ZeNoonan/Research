"""Generate the shots / xG / xA board.

Writes ``shots.html``: every Premier League player's shots, penalty-adjusted
expected goals and expected assists, gameweek by gameweek, plus the
aggregate ranking across the three. A player a row, a gameweek a column.

    python build_shots.py
    python build_shots.py --data data/2026-27 --out shots.html

The numbers and the ranking rules live in ``shots.py``; this file is the
page.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

import shots as S
from build_site import CSS, esc

HERE = Path(__file__).parent

POSITION_ORDER = ["GK", "DF", "MD", "FW"]

# Views the selector switches between. (key, tab label, column heading for
# the per-gameweek cells, how to format a value.)
VIEWS = [
    ("rank", "Aggregate ranking", None, None),
    ("shots", "Shots", "Shots", "{:.0f}"),
    ("xg", "xG (pen-adjusted)", "xG", "{:.2f}"),
    ("xa", "xA", "xA", "{:.2f}"),
]

EXTRA_CSS = """
.controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  margin: 0 0 12px; }
.controls input, .controls select { font: inherit; font-size: 14px;
  padding: 6px 8px; border: 1px solid var(--border); border-radius: 8px;
  background: var(--card); color: var(--ink); }
.controls input { flex: 1 1 200px; min-width: 160px; }
.tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.tabs button { font: inherit; font-size: 13px; font-weight: 600;
  padding: 7px 12px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--border); background: var(--card); color: var(--muted); }
.tabs button[aria-selected="true"] { background: var(--accent); color: #fff;
  border-color: var(--accent); }
table.board th { cursor: pointer; user-select: none; white-space: nowrap; }
table.board th.nosort { cursor: default; }
table.board th[data-dir]::after { content: " \\2193"; }
table.board th[data-dir="asc"]::after { content: " \\2191"; }
table.board tbody tr:hover td { background: rgba(56, 0, 60, .06); }
td.gw { text-align: right; font-variant-numeric: tabular-nums; }
.rk { color: var(--muted); font-size: 11px; font-weight: 400; }
td.gw.r1 { background: rgba(0, 160, 90, .18); font-weight: 700; }
td.gw.r2 { background: rgba(0, 160, 90, .08); }
td.dnp { color: var(--border); text-align: right; }
td.pen { position: relative; }
td.pen::after { content: "p"; font-size: 9px; vertical-align: super;
  color: #b3372f; margin-left: 2px; font-weight: 700; }
td.rowno { color: var(--muted); font-size: 12px; text-align: right; }
th.tot, td.tot { border-left: 1px solid var(--border); }
pre.audit { overflow: auto; max-height: 340px; font-size: 13px;
  color: var(--muted); background: rgba(128, 128, 128, .07);
  border-radius: 8px; padding: 10px 12px; margin: 0 0 10px; }
.count { color: var(--muted); font-size: 13px; margin: 8px 0 0; }
.legend { color: var(--muted); font-size: 13px; margin: 10px 0 0; }
.legend span.key { display: inline-block; width: 14px; height: 14px;
  border-radius: 3px; vertical-align: -2px; margin-right: 4px; }
@media (prefers-color-scheme: dark) {
  table.board tbody tr:hover td { background: rgba(255, 255, 255, .05); }
  td.gw.r1 { background: rgba(76, 195, 138, .22); }
  td.gw.r2 { background: rgba(76, 195, 138, .10); }
  td.pen::after { color: #ef7a72; }
}
"""

SORT_JS = """
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

function cmp(a, b, i, dir) {
  const ta = a.children[i], tb = b.children[i];
  const va = ta.dataset.v, vb = tb.dataset.v;
  // A blank is not a value. It sinks whichever way the column is sorted,
  // so sorting by gameweek never fills the top with men who didn't play.
  const ea = va === undefined || va === '', eb = vb === undefined || vb === '';
  if (ea || eb) return ea && eb ? 0 : (ea ? 1 : -1);
  const na = parseFloat(va), nb = parseFloat(vb);
  if (!isNaN(na) && !isNaN(nb)) return dir * (na - nb);
  return dir * String(va).localeCompare(String(vb));
}

function sortBy(table, th) {
  const i = $$('th', th.parentNode).indexOf(th);
  const asc = th.dataset.dir !== 'asc';
  $$('th', th.parentNode).forEach(h => h.removeAttribute('data-dir'));
  th.dataset.dir = asc ? 'asc' : 'desc';
  const body = $('tbody', table);
  const rows = $$('tr', body);
  rows.sort((a, b) => cmp(a, b, i, asc ? 1 : -1));
  rows.forEach(r => body.appendChild(r));
  renumber(table);
}

function renumber(table) {
  let n = 0;
  $$('tbody tr', table).forEach(r => {
    if (r.style.display === 'none') { r.children[0].textContent = ''; return; }
    r.children[0].textContent = ++n;
  });
}

function filter() {
  const q = $('#q').value.trim().toLowerCase();
  const pos = $('#pos').value, team = $('#team').value;
  const table = $('table.board:not([hidden])');
  let shown = 0;
  $$('tbody tr', table).forEach(r => {
    const ok = (!q || r.dataset.name.includes(q))
      && (!pos || r.dataset.pos === pos)
      && (!team || r.dataset.team === team);
    r.style.display = ok ? '' : 'none';
    if (ok) shown++;
  });
  renumber(table);
  $('#count').textContent = shown + ' of ' + $$('tbody tr', table).length
    + ' players shown';
}

function showView(key) {
  $$('.tabs button').forEach(b =>
    b.setAttribute('aria-selected', b.dataset.view === key));
  $$('table.board').forEach(t => { t.hidden = t.dataset.view !== key; });
  filter();
}

$$('.tabs button').forEach(b =>
  b.addEventListener('click', () => showView(b.dataset.view)));
$$('table.board').forEach(t => $$('th:not(.nosort)', t).forEach(th =>
  th.addEventListener('click', () => sortBy(t, th))));
['q', 'pos', 'team'].forEach(id =>
  $('#' + id).addEventListener('input', filter));
showView('rank');
"""


def rank_cell(row, gw: int, note: str) -> str:
    """One gameweek cell of the ranking table: the rank, or a blank."""
    v = row.get(f"gw{gw}")
    if pd.isna(v):
        return ('<td class="dnp" data-v="" title="No minutes played in '
                f'GW{gw}">&mdash;</td>')
    v = int(v)
    tier = " r1" if v <= 10 else (" r2" if v <= 30 else "")
    pen = " pen" if row.get(f"pen_gw{gw}") else ""
    return (f'<td class="gw{tier}{pen}" data-v="{v}" title="{esc(note)}">'
            f'{v}</td>')


def _rank(v: float) -> str:
    """'12' for a clean rank, '82.5' for a tie sharing the mean of two."""
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


def value_cell(row, cat: str, gw: int, fmt: str, note: str) -> str:
    """The category's value that gameweek, with its rank in that category.

    The rank beside a shots count is the **shots** rank, not the aggregate:
    the aggregate is two thirds about xG and xA, and pairing it with a shots
    number would say something the number does not. The aggregate has its
    own tab, and the tooltip carries both either way.
    """
    v = row.get(f"{cat}_gw{gw}")
    if pd.isna(v):
        return ('<td class="dnp" data-v="" title="No minutes played in '
                f'GW{gw}">&mdash;</td>')
    rk = row.get(f"{cat}_rank_gw{gw}")
    pen = " pen" if cat == "xg" and row.get(f"pen_gw{gw}") else ""
    tier = "" if pd.isna(rk) else (" r1" if rk <= 10 else
                                   (" r2" if rk <= 30 else ""))
    place = ("" if pd.isna(rk)
             else f' <span class="rk">({_rank(rk)})</span>')
    # Sorted on the value, not the rank: within a gameweek they are the same
    # ordering, and the value is the one the reader means by "most shots".
    return (f'<td class="gw{tier}{pen}" data-v="{v:.4f}" title="{esc(note)}">'
            f'{fmt.format(v)}{place}</td>')


def table_html(table: pd.DataFrame, view: str, gameweeks: list[int],
               notes: dict) -> str:
    """Render one of the four views. All share the row identity columns.

    Each view arrives already sorted the way it should open — the ranking on
    its total, a category on its own season total — and the heading carries
    the arrow to say so.
    """
    key, label, head, fmt = next(v for v in VIEWS if v[0] == view)
    if view == "rank":
        table = table.sort_values(["total", "average"])
    else:
        table = table.sort_values(f"{key}_total", ascending=False)

    heads = ['<th class="nosort">#</th>', '<th>Player</th>', '<th>Team</th>',
             '<th>Pos</th>']
    heads += [f'<th class="num">GW{g}</th>' for g in gameweeks]
    heads += ['<th class="num tot">Mins</th>', '<th class="num">GWs</th>']
    if view == "rank":
        heads += ['<th class="num" data-dir="asc">Total</th>',
                  '<th class="num">Avg</th>']
    else:
        heads += [f'<th class="num" data-dir="desc">{esc(head)} total</th>']

    rows = []
    for n, r in enumerate(table.to_dict("records"), 1):
        cells = [f'<td class="rowno" data-v="{n}">{n}</td>',
                 f'<td data-v="{esc(r["name"])}">{esc(r["name"])}</td>',
                 f'<td data-v="{esc(r["team"])}">{esc(r["team"])}</td>',
                 f'<td data-v="{esc(r["position"])}">{esc(r["position"])}</td>']
        for g in gameweeks:
            note = notes.get((r["element"], g), "")
            cells.append(rank_cell(r, g, note) if view == "rank"
                         else value_cell(r, key, g, fmt, note))
        cells.append(f'<td class="num tot" data-v="{r["minutes"]}">'
                     f'{r["minutes"]:,.0f}</td>')
        cells.append(f'<td class="num" data-v="{r["played"]}">'
                     f'{r["played"]}</td>')
        if view == "rank":
            cells.append(f'<td class="num" data-v="{r["total"]:.0f}">'
                         f'{r["total"]:.0f}</td>')
            cells.append(f'<td class="num" data-v="{r["average"]:.2f}">'
                         f'{r["average"]:.1f}</td>')
        else:
            total = r[f"{key}_total"]
            cells.append(f'<td class="num" data-v="{total:.4f}">'
                         f'{fmt.format(total)}</td>')
        rows.append(
            f'<tr data-name="{esc(str(r["name"]).lower())}" '
            f'data-pos="{esc(r["position"])}" data-team="{esc(r["team"])}">'
            + "".join(cells) + "</tr>")

    return (f'<table class="board" data-view="{key}"{"" if key == "rank" else " hidden"}>'
            f'<thead><tr>{"".join(heads)}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def cell_notes(ranked: pd.DataFrame) -> dict:
    """Tooltip for every played (player, gameweek): the three ranks and values."""
    out = {}
    for r in ranked[ranked["played"]].itertuples():
        pen = (f", incl. {r.pkatt:.0f} pen "
               f"(-{S.PENALTY_XG * r.pkatt:.2f} xG)") if r.pkatt else ""
        out[(r.element, r.round)] = (
            f"GW{r.round}: {r.minutes:.0f} min · "
            f"{r.shots:.0f} shots (rank {r.rank_shots:g}) · "
            f"{r.xg:.2f} xG (rank {r.rank_xg:g}){pen} · "
            f"{r.xa:.2f} xA (rank {r.rank_xa:g}) · "
            f"ranks sum to {r.rank_sum:g} of {3 * r.field}")
    return out


def penalty_flags(ranked: pd.DataFrame, table: pd.DataFrame,
                  gameweeks: list[int]) -> pd.DataFrame:
    """Add ``pen_gw<n>`` so the board can mark the weeks a penalty was charged."""
    out = table.copy()
    pk = ranked.pivot_table(index="element", columns="round", values="pkatt",
                            aggfunc="first").reindex(
        index=out["element"], columns=gameweeks).fillna(0)
    for g in gameweeks:
        out[f"pen_gw{g}"] = pk[g].values > 0
    return out


def penalty_table(ranked: pd.DataFrame) -> str:
    pk = ranked[ranked["pkatt"] > 0].sort_values(["round", "name"])
    rows = "".join(
        f"<tr><td>{esc(r.name)}</td><td>{esc(r.team)}</td>"
        f"<td class='num'>GW{r.round}</td><td class='num'>{r.pkatt:.0f}</td>"
        f"<td class='num'>{r.xg_raw:.2f}</td>"
        f"<td class='num'>&minus;{S.PENALTY_XG * r.pkatt:.2f}</td>"
        f"<td class='num'><b>{r.xg:.2f}</b></td></tr>"
        for r in pk.itertuples())
    return ("<div class='tablewrap'><table><thead><tr><th>Player</th>"
            "<th>Team</th><th class='num'>GW</th><th class='num'>Pens</th>"
            "<th class='num'>FPL xG</th><th class='num'>Charged</th>"
            "<th class='num'>Ranked on</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")


HOW_SAID = {
    "exact": "names agree",
    "partial": "name inside name",
    "surname": "surname only",
    "token": "one token shared",
    "minutes": "minutes played",
    "none": "not matched",
}

HOW_LEGEND = (
    "<p class='note'><b>name inside name</b> — one name is a subset of the "
    "other, so <i>Bruno Fernandes</i> is <i>Bruno Borges Fernandes</i>. "
    "<b>surname only</b> — the surnames agree and the first names do not, "
    "accepted at the same club. <b>one token shared</b> — a single name in "
    "common, the weakest string match, so read these rows. "
    "<b>minutes played</b> — the names share nothing at all and the match "
    "rests entirely on both sources having counted the same minutes at the "
    "same club, with exactly one candidate close enough. Every row is shown "
    "with both minute counts so you can check it yourself.</p>")


def join_table(join: pd.DataFrame) -> str:
    """Every pair the names alone did not settle, with the minutes check.

    The exact matches need no defending. These are the ones worth being able
    to look at: the abbreviations, the nicknames, and the players whose club
    disagrees between the two sources because they moved.
    """
    shown = join[join["how"] != "exact"].copy()
    rows = "".join(
        f"<tr><td>{esc(r.Player)}</td><td>{esc(r.Squad)}</td>"
        f"<td>{esc(r.fpl_name) or '&mdash;'}</td>"
        f"<td class='num'>{r.fb_minutes:.0f}</td>"
        f"<td class='num'>{'' if pd.isna(r.fpl_minutes) else f'{r.fpl_minutes:.0f}'}</td>"
        f"<td>{esc(HOW_SAID.get(r.how, r.how))}</td></tr>"
        for r in shown.sort_values(["how", "Player"]).itertuples())
    return ("<div class='tablewrap'><table><thead><tr><th>fbref name</th>"
            "<th>fbref club</th><th>FPL name</th>"
            "<th class='num'>fbref mins</th><th class='num'>FPL mins</th>"
            "<th>How</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")


def moved_table(join: pd.DataFrame) -> str:
    """The players the two sources put at different clubs.

    Not an error: fbref records the club a player turned out for, FPL the
    club he is at now. Every row here is a transfer that happened after the
    last gameweek shown.
    """
    moved = join[join["element"].notna() & (join["Squad"] != join["fpl_team"])]
    if not len(moved):
        return "<p class='note'>The two sources agree on every player's club.</p>"
    rows = "".join(
        f"<tr><td>{esc(r.Player)}</td><td>{esc(r.Squad)}</td>"
        f"<td>{esc(r.fpl_team)}</td></tr>"
        for r in moved.sort_values("Player").itertuples())
    return ("<div class='tablewrap'><table><thead><tr><th>Player</th>"
            "<th>Played for (fbref)</th><th>Now at (FPL)</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")


def build(data_dir: Path, out: Path) -> None:
    week = S.weekly(data_dir)
    join = week.attrs["join"]
    audit = S.report_join(week)
    print(audit)

    ranked = S.rank_gameweeks(week)
    gameweeks = [int(g) for g in week.attrs["gameweeks"]]
    table = penalty_flags(ranked, S.board(ranked), gameweeks)
    notes = cell_notes(ranked)

    played = ranked[ranked["played"]]
    field = played.groupby("round").size()
    quiet = played.groupby("round").apply(
        lambda g: int(((g["shots"] == 0) & (g["xg"].abs() < 1e-9)
                       & (g["xa"].abs() < 1e-9)).sum()), include_groups=False)

    teams = sorted(table["team"].unique())
    team_opts = "".join(f'<option value="{esc(t)}">{esc(t)}</option>'
                        for t in teams)
    pos_opts = "".join(f'<option value="{p}">{p}</option>'
                       for p in POSITION_ORDER if (table["position"] == p).any())
    tabs = "".join(
        f'<button data-view="{k}" aria-selected="false">{esc(lbl)}</button>'
        for k, lbl, _, _ in VIEWS)
    tables = "".join(table_html(table, k, gameweeks, notes)
                     for k, _, _, _ in VIEWS)

    # A gameweek only one source has cannot be ranked, but the reader has to
    # be told it exists — otherwise the board silently stops a week short.
    skipped = []
    for gws, why in ((week.attrs["fbref_only"],
                      "there is no FPL data for it yet — re-run "
                      "<code>scraper_fpl.py</code>"),
                     (week.attrs["fpl_only"],
                      "there is no fbref sheet for it yet — add a "
                      "<code>GW&lt;n&gt;</code> tab to the workbook")):
        if gws:
            skipped.append(
                "<p class='note'><b>Not shown: "
                + ", ".join(f"GW{g}" for g in gws)
                + f".</b> {why}, and ranking a gameweek on one source alone "
                  "would read as nobody having done anything.</p>")
    skipped_html = "".join(skipped)

    gw_list = ", ".join(f"GW{g}" for g in gameweeks)
    field_list = "; ".join(f"GW{g} {field[g]}" for g in gameweeks)
    quiet_list = "; ".join(
        f"GW{g} {quiet[g]} ({quiet[g] / field[g]:.0%})" for g in gameweeks)

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FPL — shots, xG and xA by gameweek</title>
<style>{CSS}{EXTRA_CSS}</style></head><body><div class="wrap">
<header><h1>Shots, xG and xA &mdash; by gameweek</h1>
<p class="sub">Every player who has been on the pitch, ranked each gameweek
on shots, penalty-adjusted expected goals and expected assists, and on the
three together.</p></header>

<div class="banner">Covering <b>{esc(gw_list)}</b> &middot;
<b>{len(table)}</b> players who have played &middot; shots and penalties from
<b>fbref</b>, expected goals and assists from the <b>FPL API</b>. Every
penalty attempt costs its taker <b>{S.PENALTY_XG:.2f} xG</b> in the week he
took it. <a href="preseason.html" style="color:var(--accent2)">Pre-season
board &rarr;</a> <a href="index.html" style="color:var(--accent2)">In-season
app &rarr;</a></div>

<section><h2>Read this first</h2>
<p class="note"><b>Where the numbers come from.</b> No single source has all
three. fbref publishes <b>shots</b> and <b>penalties attempted</b>, one
sheet per gameweek, each one cumulative to the end of that gameweek &mdash;
so a single gameweek is the sheet minus its predecessor. The FPL API
publishes <b>expected goals</b>, <b>expected assists</b> and <b>minutes</b>,
already week by week. The two are joined player by player; the join is
audited at the foot of the page.</p>

<p class="note"><b>Penalties.</b> A penalty is worth about 0.79 xG in the
models, and it tells you who takes penalties rather than who is getting
shots away. Left in, one spot kick outranks four good chances. So each
attempt fbref records costs its taker <b>{S.PENALTY_XG:.2f} xG in that
gameweek</b>, and the ranking uses what is left. The weeks it applied are
listed below, and marked with a small red <b style="color:#b3372f">p</b> in
the tables.</p>

<p class="note"><b>How the ranking works.</b> Within a gameweek, over the
players who actually played, each of shots, adjusted xG and xA is ranked
with <b>1 the best</b>; ties share the mean rank, so nobody gains by sitting
in a crowd of zeros. The three ranks are added and the sum re-ranked from 1
&mdash; that number is the cell on the <b>Aggregate ranking</b> tab. The
other three tabs show the raw number with <b>its own rank in that
category</b> in brackets beside it, which is the rank that belongs with a
shots count &mdash; the aggregate is two thirds about the other two, and has
its own tab. Hover any cell for all of it: the three category ranks, the raw
numbers, and what they summed to.</p>

<p class="note"><b>A player who did not play is blank</b> (&mdash;), not
zero and not last: he was injured, rested, suspended or an unused
substitute, and the data does not say which. But a column of blanks cannot
be summed honestly, because missing a gameweek would then <i>improve</i> a
player's total. So <b>Total</b> charges a missed gameweek that week's last
place, and <b>Avg</b> is the mean over the gameweeks he actually played.
They answer different questions &mdash; Total asks who has been most useful
so far, Avg asks who is best when he plays &mdash; and <b>GWs</b> sits
between them so you can always see which is which. Sorting is on any
column; blanks always sink.</p>

<p class="note"><b>Totals, not rates.</b> A substitute who plays ten minutes
is ranked against a man who played ninety, on the same raw numbers. That is
the honest way to answer "who did most this gameweek", but it is not
"who is best per minute" &mdash; a cameo with one shot in it will outrank a
quiet full ninety. <b>Mins</b> is on every row so you can see which you are
looking at.</p>

<p class="note"><b>What the bottom of the table means.</b>
{esc(quiet_list)} of the players who played took no shot, made no chance and
were credited with no expected goals at all. They are genuinely tied, they
all share the same rank, and no ordering among them means anything. The
field each week: {esc(field_list)}.</p>
{skipped_html}
<p class="note"><b>Adding a gameweek.</b> Drop a new <code>GW&lt;n&gt;</code>
sheet into <code>data/2026-27/fbref_shots.xlsx</code> — cumulative, like the
others — re-run <code>scraper_fpl.py</code> for the FPL side, then
<code>python build_shots.py</code>. The sheet names are the gameweek
numbers; the workbook's own <code>Week</code> column is a row rank and is
ignored.</p>
</section>

<section><h2>The board</h2>
<div class="tabs">{tabs}</div>
<div class="controls">
<input id="q" type="search" placeholder="Search player…" autocomplete="off">
<select id="pos"><option value="">All positions</option>{pos_opts}</select>
<select id="team"><option value="">All clubs</option>{team_opts}</select>
</div>
<div class="tablewrap">{tables}</div>
<p class="count" id="count"></p>
<p class="legend"><span class="key" style="background:rgba(0,160,90,.18)">
</span>top 10 that gameweek &nbsp;
<span class="key" style="background:rgba(0,160,90,.08)"></span>top 30 &nbsp;
&mdash; no minutes &nbsp; <b style="color:#b3372f">p</b> penalty charged that
week</p>
<p class="legend">On the <b>Shots</b>, <b>xG</b> and <b>xA</b> tabs a cell
reads <b>value <span class="rk">(rank)</span></b> &mdash; the rank is that
player's place <i>in that category</i> that gameweek, not the aggregate,
because the aggregate is two thirds about the other two. It shares the mean
where players tie, so <span class="rk">(82.5)</span> is a tie spanning 82nd
and 83rd. The shading follows that same rank, and the columns still sort on
the value.</p>
</section>

<section><h2>The penalties charged</h2>
<p class="note">Every attempt fbref recorded, and what it cost the taker's
expected goals for that gameweek. FPL's raw number is shown beside it: the
gap between the two is the open-play xG the ranking actually uses.</p>
{penalty_table(ranked)}</section>

<section><h2>How the two sources were joined</h2>
<p class="note">fbref writes display names (<code>Bruno Fernandes</code>);
FPL writes <code>first_second</code> lowercased
(<code>bruno_borges fernandes</code>). Names are normalised and assigned
one-to-one, best match first. A club agreeing helps but is not required
&mdash; FPL reports a player's <b>current</b> club, so a deadline-day move
disagrees with the club he actually played for. Whatever is left over is
settled on minutes, which is what catches the nicknames no string match
will: fbref's <i>Beto</i> is FPL's <i>norberto bercique gomes betuncal</i>,
its <i>Costinha</i> is <i>joão pedro loureiro da costa</i>.</p>
<p class="note">Minutes then <b>audit</b> every pair. Two sources that
counted the same man's minutes independently are the check on whether the
join is right, and anything they disagree on by more than
{S.MINUTES_TOL} minutes is named here rather than quietly shipped. So is
anyone FPL says was on the pitch that fbref does not list, because he would
otherwise be ranked as having taken no shot when the truth is that nobody
counted them.</p>
<pre class="audit">{esc(audit)}</pre>

<details><summary>Every match the names alone did not settle
({int((join["how"] != "exact").sum())} of {len(join)})</summary>
{HOW_LEGEND}
{join_table(join)}</details>

<details><summary>Players the two sources put at different clubs
({int((join["element"].notna() & (join["Squad"] != join["fpl_team"])).sum())})
</summary>
<p class="note">Not an error. fbref records the club a player turned out
for; FPL records the club he is at now. Each row is a transfer since the
last gameweek shown, and the shots still belong to the man, not the shirt.</p>
{moved_table(join)}</details>
</section>

<footer>Built {date.today().isoformat()} &middot; shots and penalties: fbref
&middot; expected goals, expected assists, minutes: the FPL API</footer>
</div><script>{SORT_JS}</script></body></html>
"""
    out.write_text(page, encoding="utf-8")
    print(f"\nwrote {out} — {len(table)} players, {len(gameweeks)} gameweeks")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=HERE / "data" / "2026-27", type=Path)
    ap.add_argument("--out", default=HERE / "shots.html", type=Path)
    args = ap.parse_args()
    build(args.data, args.out)


if __name__ == "__main__":
    main()
