"""Generate the gameweek boards.

Two pages, same machinery, different populations and categories:

* ``shots.html`` — **every** player, ranked on shots, penalty-adjusted
  expected goals and expected assists.
* ``defcon.html`` — **defenders and midfielders only**, on those three plus
  FPL's defensive contributions, and ranked against each other rather than
  against forwards.

::

    python build_shots.py                     # both
    python build_shots.py --board defcon      # just the one
    python build_shots.py --data data/2026-27 --out-dir .

The numbers and the ranking rules live in ``shots.py``; this file is the
page.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

import shots as S
from build_site import CSS, esc

HERE = Path(__file__).parent

POSITION_ORDER = ["GK", "DF", "MD", "FW"]

# How each category's per-gameweek cell is labelled and formatted.
# (tab label, column heading, value format)
VIEW_SPEC = {
    "shots": ("Shots", "Shots", "{:.0f}"),
    "xg": ("xG (pen-adjusted)", "xG", "{:.2f}"),
    "xa": ("xA", "xA", "{:.2f}"),
    "dc": ("Defensive contributions", "DC", "{:.0f}"),
}

POSITION_WORDS = {"GK": "goalkeepers", "DF": "defenders",
                  "MD": "midfielders", "FW": "forwards"}

# How a category is named in a sentence, as against in a column heading.
CATEGORY_PROSE = {"shots": "shots", "xg": "penalty-adjusted xG", "xa": "xA",
                  "dc": "defensive contributions"}


@dataclass(frozen=True)
class Board:
    """One page: who is on it, what it ranks them on, and what to call it."""
    key: str
    out: str
    title: str
    heading: str
    sub: str
    categories: tuple
    positions: tuple | None = None

    def views(self):
        """(key, tab label, cell heading, format) — the aggregate, then each
        category in the order they are summed."""
        return [("rank", "Aggregate ranking", None, None)] + [
            (c, *VIEW_SPEC[c]) for c in self.categories]

    @property
    def who(self) -> str:
        if not self.positions:
            return "every player who has been on the pitch"
        return " and ".join(POSITION_WORDS[p] for p in self.positions)


BOARDS = {
    "shots": Board(
        key="shots", out="shots.html",
        title="FPL — shots, xG and xA by gameweek",
        heading="Shots, xG and xA &mdash; by gameweek",
        sub="Every player who has been on the pitch, ranked each gameweek on "
            "shots, penalty-adjusted expected goals and expected assists, and "
            "on the three together.",
        categories=S.CATEGORIES),
    "defcon": Board(
        key="defcon", out="defcon.html",
        title="FPL — the defcon board",
        heading="The defcon board &mdash; by gameweek",
        sub="Defenders and midfielders only, ranked each gameweek on shots, "
            "penalty-adjusted expected goals, expected assists and defensive "
            "contributions &mdash; and on the four together.",
        categories=S.DEFCON_CATEGORIES, positions=S.DEFCON_POSITIONS),
}

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
td.pen::after { content: "p"; font-size: 9px; vertical-align: super;
  color: #b3372f; margin-left: 2px; font-weight: 700; }
/* The week's defensive count cleared FPL's 2-point bar. */
td.hit::after { content: "\\2713"; font-size: 10px; vertical-align: super;
  color: #1e7d46; margin-left: 2px; font-weight: 700; }
td.hitcount { color: #1e7d46; font-weight: 700; }
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
  td.hit::after, td.hitcount { color: #4cc38a; }
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
    the aggregate is mostly about the other categories, and pairing it with a
    shots number would say something the number does not. The aggregate has
    its own tab, and the tooltip carries both either way.

    On the defensive-contributions column the marker means something else
    again: the week's count cleared FPL's 2-point bar.
    """
    v = row.get(f"{cat}_gw{gw}")
    if pd.isna(v):
        return ('<td class="dnp" data-v="" title="No minutes played in '
                f'GW{gw}">&mdash;</td>')
    rk = row.get(f"{cat}_rank_gw{gw}")
    if cat == "xg":
        mark = " pen" if row.get(f"pen_gw{gw}") else ""
    elif cat == "dc":
        mark = " hit" if row.get(f"dc_hit_gw{gw}") else ""
    else:
        mark = ""
    tier = "" if pd.isna(rk) else (" r1" if rk <= 10 else
                                   (" r2" if rk <= 30 else ""))
    place = ("" if pd.isna(rk)
             else f' <span class="rk">({_rank(rk)})</span>')
    # Sorted on the value, not the rank: within a gameweek they are the same
    # ordering, and the value is the one the reader means by "most shots".
    return (f'<td class="gw{tier}{mark}" data-v="{v:.4f}" title="{esc(note)}">'
            f'{fmt.format(v)}{place}</td>')


def table_html(board: Board, table: pd.DataFrame, view: str,
               gameweeks: list[int], notes: dict) -> str:
    """Render one of the board's views. All share the row identity columns.

    Each view arrives already sorted the way it should open — the ranking on
    its total, a category on its own season total — and the heading carries
    the arrow to say so.
    """
    key, label, head, fmt = next(v for v in board.views() if v[0] == view)
    if view == "rank":
        table = table.sort_values(["total", "average"])
    else:
        table = table.sort_values(f"{key}_total", ascending=False)

    # The weeks a player earned the 2 defensive points are worth a column of
    # their own wherever the defensive category is in play — it is the thing
    # the board exists to find, and a rank cannot show it.
    show_dc_weeks = "dc" in board.categories

    heads = ['<th class="nosort">#</th>', '<th>Player</th>', '<th>Team</th>',
             '<th>Pos</th>']
    heads += [f'<th class="num">GW{g}</th>' for g in gameweeks]
    heads += ['<th class="num tot">Mins</th>', '<th class="num">GWs</th>']
    if show_dc_weeks:
        heads += ['<th class="num" title="Gameweeks he cleared FPL\'s '
                  'defensive-contribution bar">DC pts</th>']
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
        if show_dc_weeks:
            wk = int(r["dc_weeks"])
            cells.append(f'<td class="num{" hitcount" if wk else ""}" '
                         f'data-v="{wk}">{wk}</td>')
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


def cell_notes(board: Board, ranked: pd.DataFrame) -> dict:
    """Tooltip for every played (player, gameweek): every rank and value."""
    out = {}
    n_cats = len(board.categories)
    for r in ranked[ranked["played"]].itertuples():
        pen = (f", incl. {r.pkatt:.0f} pen "
               f"(-{S.PENALTY_XG * r.pkatt:.2f} xG)") if r.pkatt else ""
        parts = [f"{r.shots:.0f} shots (rank {r.rank_shots:g})",
                 f"{r.xg:.2f} xG (rank {r.rank_xg:g}){pen}",
                 f"{r.xa:.2f} xA (rank {r.rank_xa:g})"]
        if "dc" in board.categories:
            got = " — 2 pts" if r.dc_hit else f" — {r.dc_bar:.0f} needed"
            parts.append(f"{r.dc:.0f} def. actions (rank {r.rank_dc:g}){got}")
        out[(r.element, r.round)] = (
            f"GW{r.round}: {r.minutes:.0f} min · " + " · ".join(parts)
            + f" · ranks sum to {r.rank_sum:g} of {n_cats * r.field}")
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


def dc_section(board: Board, ranked: pd.DataFrame, table: pd.DataFrame,
               gameweeks: list[int]) -> str:
    """The defensive-contribution explainer and the leaderboard on it.

    Only on a board that ranks the category. It exists because the ranked
    quantity — the raw count of actions — is not the same thing as the two
    points, and the difference is a position-dependent threshold the count
    alone does not show.
    """
    if "dc" not in board.categories:
        return ""
    played = ranked[ranked["played"]]
    bars = "; ".join(
        f"<b>{POSITION_WORDS[p].capitalize()} {S.DC_THRESHOLD[p]}</b>"
        for p in board.positions)
    per_pos = []
    for p in board.positions:
        g = played[played["position"] == p]
        per_pos.append(f"{POSITION_WORDS[p]} {int(g['dc_hit'].sum())} of "
                       f"{len(g)} ({g['dc_hit'].mean():.0%})")

    top = table.nlargest(15, "dc_total")
    rows = "".join(
        f"<tr><td>{esc(r['name'])}</td><td>{esc(r['team'])}</td>"
        f"<td>{esc(r['position'])}</td>"
        + "".join(
            "<td class='num'>&mdash;</td>" if pd.isna(r[f"dc_gw{g}"])
            else (f"<td class='num{' hitcount' if r[f'dc_hit_gw{g}'] else ''}'>"
                  f"{r[f'dc_gw{g}']:.0f}</td>")
            for g in gameweeks)
        + f"<td class='num'><b>{r['dc_total']:.0f}</b></td>"
        f"<td class='num{' hitcount' if r['dc_weeks'] else ''}'>"
        f"{int(r['dc_weeks'])}</td></tr>"
        for r in top.to_dict("records"))
    heads = "".join(f"<th class='num'>GW{g}</th>" for g in gameweeks)

    return f"""
<section><h2>Defensive contributions, and the 2 points</h2>
<p class="note"><b>What is counted.</b> FPL's own tally of qualifying
defensive actions. For a <b>defender</b> that is clearances, blocks,
interceptions and tackles; for a <b>midfielder</b> it adds recoveries. The
board ranks that raw count &mdash; it is what "defensive contributions"
means, and it is the same treatment the other three categories get.</p>

<p class="note"><b>The 2 points are a different question.</b> FPL pays them
at a threshold, and the threshold is not the same for both: {bars}. A
midfielder's count includes recoveries and needs two more of them, so the
raw count and the reward do not line up. Rather than distort the ranking to
patch that, the threshold is shown directly: a cell that cleared it carries
a green <b style="color:#1e7d46">&#10003;</b>, and the <b>DC pts</b> column
counts the gameweeks a player has done it. So far: {esc('; '.join(per_pos))}
of player-gameweeks.</p>

<p class="note"><b>Three of the four categories are attacking</b>, so the
aggregate leans that way and midfielders fill the head of the table. Use
the position filter to read it as a defenders' board, or sort on the
<b>Defensive contributions</b> tab &mdash; which opens on the season total
&mdash; to read it as a pure defensive one.</p>

<div class='tablewrap'><table><thead><tr><th>Player</th><th>Team</th>
<th>Pos</th>{heads}<th class='num'>Total</th>
<th class='num'>DC pts</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="note">The fifteen busiest defenders and midfielders by total
qualifying actions. Green means that week cleared the bar.</p>
</section>"""


def build(board: Board, data_dir: Path, out: Path) -> None:
    week = S.weekly(data_dir)
    join = week.attrs["join"]
    audit = S.report_join(week)
    print(audit)

    # Restrict first, then rank: a defcon player is ranked against the other
    # defenders and midfielders, not against the forwards he is not competing
    # with for the same squad place.
    pool = S.restrict(week, board.positions)
    ranked = S.rank_gameweeks(pool, board.categories)
    gameweeks = [int(g) for g in week.attrs["gameweeks"]]
    table = penalty_flags(ranked, S.board(ranked), gameweeks)
    notes = cell_notes(board, ranked)

    played = ranked[ranked["played"]]
    field = played.groupby("round").size()
    quiet = played.groupby("round").apply(
        lambda g: int((sum(g[c].abs() for c in board.categories)
                       < 1e-9).sum()), include_groups=False)

    teams = sorted(table["team"].unique())
    team_opts = "".join(f'<option value="{esc(t)}">{esc(t)}</option>'
                        for t in teams)
    pos_opts = "".join(f'<option value="{p}">{p}</option>'
                       for p in POSITION_ORDER if (table["position"] == p).any())
    views = board.views()
    tabs = "".join(
        f'<button data-view="{k}" aria-selected="false">{esc(lbl)}</button>'
        for k, lbl, _, _ in views)
    tables = "".join(table_html(board, table, k, gameweeks, notes)
                     for k, _, _, _ in views)

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

    n_cats = len(board.categories)
    n_word = {3: "three", 4: "four"}[n_cats]
    cat_list = ", ".join(CATEGORY_PROSE[c] for c in board.categories[:-1]) \
        + " and " + CATEGORY_PROSE[board.categories[-1]]
    tab_names = ", ".join(
        f"<b>{esc(VIEW_SPEC[c][0])}</b>" for c in board.categories[:-1]) \
        + f" and <b>{esc(VIEW_SPEC[board.categories[-1]][0])}</b>"
    other = BOARDS["defcon" if board.key == "shots" else "shots"]
    other_link = (f'<a href="{other.out}" style="color:var(--accent2)">'
                  f'{esc("Defcon board" if other.key == "defcon" else "Shots, xG and xA board")}'
                  " &rarr;</a>")

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(board.title)}</title>
<style>{CSS}{EXTRA_CSS}</style></head><body><div class="wrap">
<header><h1>{board.heading}</h1>
<p class="sub">{board.sub}</p></header>

<div class="banner">Covering <b>{esc(gw_list)}</b> &middot;
<b>{len(table)}</b> {esc(board.who)} &middot; shots and penalties from
<b>fbref</b>, everything else from the <b>FPL API</b>. Every
penalty attempt costs its taker <b>{S.PENALTY_XG:.2f} xG</b> in the week he
took it. {other_link}
<a href="preseason.html" style="color:var(--accent2)">Pre-season
board &rarr;</a> <a href="index.html" style="color:var(--accent2)">In-season
app &rarr;</a></div>

<section><h2>Read this first</h2>
<p class="note"><b>Where the numbers come from.</b> No single source has all
of them. fbref publishes <b>shots</b> and <b>penalties attempted</b>, one
sheet per gameweek, each one cumulative to the end of that gameweek &mdash;
so a single gameweek is the sheet minus its predecessor. The FPL API
publishes <b>expected goals</b>, <b>expected assists</b>, <b>defensive
contributions</b> and <b>minutes</b>, already week by week. The two are
joined player by player; the join is audited at the foot of the page.</p>

<p class="note"><b>Penalties.</b> A penalty is worth about 0.79 xG in the
models, and it tells you who takes penalties rather than who is getting
shots away. Left in, one spot kick outranks four good chances. So each
attempt fbref records costs its taker <b>{S.PENALTY_XG:.2f} xG in that
gameweek</b>, and the ranking uses what is left. The weeks it applied are
listed below, and marked with a small red <b style="color:#b3372f">p</b> in
the tables.</p>

<p class="note"><b>How the ranking works.</b> Within a gameweek, over the
{esc(board.who)} who actually played, each of {esc(cat_list)} is ranked
with <b>1 the best</b>; ties share the mean rank, so nobody gains by sitting
in a crowd of zeros. The {n_word} ranks are added and the sum re-ranked from
1 &mdash; that number is the cell on the <b>Aggregate ranking</b> tab. The
other {n_word} tabs show the raw number with <b>its own rank in that
category</b> in brackets beside it, which is the rank that belongs with a
shots count &mdash; the aggregate is mostly about the other categories, and
has its own tab. Hover any cell for all of it: the {n_word} category ranks,
the raw numbers, and what they summed to.</p>

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
{esc(quiet_list)} of the players who played registered <b>nothing at all</b>
in any of the {n_word} categories. They are genuinely tied, they all share
the same rank, and no ordering among them means anything. The field each
week: {esc(field_list)}.</p>
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
week{' &nbsp; <b style="color:#1e7d46">&#10003;</b> cleared the 2-point '
      'defensive bar that week' if "dc" in board.categories else ''}</p>
<p class="legend">On the {tab_names} tabs a cell reads
<b>value <span class="rk">(rank)</span></b> &mdash; the rank is that
player's place <i>in that category</i> that gameweek, not the aggregate,
because the aggregate is mostly about the other categories. It shares the
mean where players tie, so <span class="rk">(82.5)</span> is a tie spanning
82nd and 83rd. The shading follows that same rank, and the columns still
sort on the value.</p>
</section>
{dc_section(board, ranked, table, gameweeks)}

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
&middot; expected goals, expected assists, defensive contributions, minutes:
the FPL API</footer>
</div><script>{SORT_JS}</script></body></html>
"""
    out.write_text(page, encoding="utf-8")
    print(f"\nwrote {out} — {len(table)} players, {len(gameweeks)} gameweeks")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=HERE / "data" / "2026-27", type=Path)
    ap.add_argument("--out-dir", default=HERE, type=Path,
                    help="where the pages are written (default: beside this file)")
    ap.add_argument("--board", choices=sorted(BOARDS), action="append",
                    help="build only this board; repeatable (default: all)")
    args = ap.parse_args()
    for key in args.board or list(BOARDS):
        board = BOARDS[key]
        print(f"\n===== {board.out}")
        build(board, args.data, args.out_dir / board.out)


if __name__ == "__main__":
    main()
